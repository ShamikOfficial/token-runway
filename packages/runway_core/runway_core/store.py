"""DynamoDB + S3 persistence against Floci (or real AWS)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from runway_core.aws_clients import dynamodb_resource, s3_client, sns_client
from runway_core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(value: Any) -> Any:
    """DynamoDB wants Decimal for floats."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        # keep ints looking like ints when we can
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


class FuelStore:
    """Budgets + usage + flight plans."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._db = dynamodb_resource(self.settings)
        self._s3 = s3_client(self.settings)
        self._sns = sns_client(self.settings)
        self.budgets = self._db.Table(self.settings.runway_budgets_table)
        self.usage = self._db.Table(self.settings.runway_usage_table)
        self.flights = self._db.Table(self.settings.runway_flights_table)
        self.audit = self._db.Table(self.settings.runway_audit_table)
        self.meta = self._db.Table(self.settings.runway_meta_table)
        self._tower_topic_arn: str | None = None

    def create_budget(
        self,
        *,
        name: str,
        limit_usd: float,
        budget_id: str | None = None,
        currency: str = "USD",
        window_days: int | None = 30,
    ) -> dict:
        budget_id = budget_id or str(uuid.uuid4())
        item = {
            "budget_id": budget_id,
            "name": name,
            "limit_usd": float(limit_usd),
            "currency": currency,
            "window_days": window_days,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        try:
            self.budgets.put_item(
                Item=_to_dynamo(item),
                ConditionExpression="attribute_not_exists(budget_id)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError(f"Budget already exists: {budget_id}") from exc
            raise
        return item

    def update_budget(
        self,
        budget_id: str,
        *,
        limit_usd: float | None = None,
        name: str | None = None,
        add_limit_usd: float | None = None,
    ) -> dict:
        """Top up or rename a fuel tank. Prefer add_limit_usd for refuel after landing."""
        current = self.get_budget(budget_id)
        if not current:
            raise KeyError(f"Unknown budget_id: {budget_id}")

        if add_limit_usd is not None:
            if add_limit_usd <= 0:
                raise ValueError("add_limit_usd must be positive")
            current["limit_usd"] = float(current["limit_usd"]) + float(add_limit_usd)
        if limit_usd is not None:
            if limit_usd <= 0:
                raise ValueError("limit_usd must be positive")
            current["limit_usd"] = float(limit_usd)
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("name cannot be empty")
            current["name"] = name

        current["updated_at"] = _now_iso()
        self.budgets.put_item(Item=_to_dynamo(current))
        return current

    def get_budget(self, budget_id: str) -> dict | None:
        resp = self.budgets.get_item(Key={"budget_id": budget_id})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def list_budgets(self, limit: int = 50) -> list[dict]:
        return self._scan_all(self.budgets, limit=limit)

    def record_usage(
        self,
        *,
        budget_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        price_source: str,
        project_id: str | None = None,
        occurred_at: str | None = None,
        metadata: dict | None = None,
        flight_id: str | None = None,
    ) -> dict:
        if not self.get_budget(budget_id):
            raise KeyError(f"Unknown budget_id: {budget_id}")

        event_id = str(uuid.uuid4())
        occurred_at = occurred_at or _now_iso()
        # SK sorts chronologically then by id
        sort_key = f"{occurred_at}#{event_id}"

        event = {
            "budget_id": budget_id,
            "sk": sort_key,
            "event_id": event_id,
            "model": model,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(prompt_tokens) + int(completion_tokens),
            "cost_usd": float(cost_usd),
            "price_source": price_source,
            "project_id": project_id,
            "flight_id": flight_id,
            "occurred_at": occurred_at,
            "metadata": metadata or {},
        }
        self.usage.put_item(Item=_to_dynamo(event))
        self._archive_raw_event(event)
        return event

    def list_usage(self, budget_id: str, limit: int = 5000) -> list[dict]:
        """Return usage events oldest→newest, paginating past DynamoDB page limits."""
        return self._query_all(
            self.usage,
            key_condition="budget_id = :b",
            values={":b": budget_id},
            limit=limit,
            forward=True,
        )

    def _archive_raw_event(self, event: dict) -> None:
        """Drop a copy on S3 so we can prove Floci S3 works (and for later audits)."""
        key = f"usage/{event['budget_id']}/{event['event_id']}.json"
        try:
            self._s3.put_object(
                Bucket=self.settings.runway_raw_bucket,
                Key=key,
                Body=json.dumps(event, default=str).encode("utf-8"),
                ContentType="application/json",
            )
        except ClientError as exc:
            # Don't fail the user request if archive hiccups — log and move on.
            logger.warning("Could not archive usage to S3 (%s): %s", key, exc)

    def save_flight_plan(self, plan: dict) -> dict:
        item = dict(plan)
        item.setdefault("created_at", _now_iso())
        item["updated_at"] = _now_iso()
        self.flights.put_item(Item=_to_dynamo(item))
        return item

    def get_flight(self, flight_id: str) -> dict | None:
        resp = self.flights.get_item(Key={"flight_id": flight_id})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def list_flights(self, budget_id: str | None = None, limit: int = 50) -> list[dict]:
        # DynamoDB applies Limit before FilterExpression — page until we fill `limit`.
        if budget_id:
            return self._scan_filtered(
                self.flights,
                filter_expression="budget_id = :b",
                values={":b": budget_id},
                limit=limit,
            )
        return self._scan_all(self.flights, limit=limit)

    def ensure_tower_topic(self) -> str:
        if self._tower_topic_arn:
            return self._tower_topic_arn
        resp = self._sns.create_topic(Name=self.settings.runway_tower_topic)
        self._tower_topic_arn = resp["TopicArn"]
        return self._tower_topic_arn

    def publish_tower_alert(self, alert: dict, budget_id: str) -> dict | None:
        """Best-effort SNS publish — Floci should accept create_topic + publish."""
        try:
            arn = self.ensure_tower_topic()
            payload = {"budget_id": budget_id, **alert}
            resp = self._sns.publish(
                TopicArn=arn,
                Subject=f"TokenRunway {alert.get('code', 'ALERT')}",
                Message=json.dumps(payload, default=str),
            )
            return {"topic_arn": arn, "message_id": resp.get("MessageId")}
        except ClientError as exc:
            logger.warning("Tower SNS publish failed: %s", exc)
            return None

    def append_audit(
        self,
        *,
        budget_id: str,
        action: str,
        detail: dict | None = None,
        flight_id: str | None = None,
    ) -> dict:
        event_id = str(uuid.uuid4())
        occurred_at = _now_iso()
        item = {
            "budget_id": budget_id,
            "sk": f"{occurred_at}#{event_id}",
            "event_id": event_id,
            "action": action,
            "flight_id": flight_id,
            "occurred_at": occurred_at,
            "detail": detail or {},
        }
        self.audit.put_item(Item=_to_dynamo(item))
        return item

    def list_audit(self, budget_id: str, limit: int = 100) -> list[dict]:
        return self._query_all(
            self.audit,
            key_condition="budget_id = :b",
            values={":b": budget_id},
            limit=limit,
            forward=False,
        )

    # --- org / fleet state (persists across API restarts) ---

    def get_org_state(self) -> dict:
        resp = self.meta.get_item(Key={"pk": "ORG"})
        item = resp.get("Item")
        if not item:
            return {"ground_stop": False, "notams": []}
        data = _from_dynamo(item)
        return {
            "ground_stop": bool(data.get("ground_stop")),
            "ground_stop_reason": data.get("ground_stop_reason"),
            "ground_stop_since": data.get("ground_stop_since"),
            "notams": list(data.get("notams") or []),
        }

    def save_org_state(self, state: dict) -> dict:
        item = {
            "pk": "ORG",
            "ground_stop": bool(state.get("ground_stop")),
            "ground_stop_reason": state.get("ground_stop_reason"),
            "ground_stop_since": state.get("ground_stop_since"),
            "notams": list(state.get("notams") or [])[:50],
            "updated_at": _now_iso(),
        }
        self.meta.put_item(Item=_to_dynamo(item))
        return self.get_org_state()

    def _query_all(
        self,
        table,
        *,
        key_condition: str,
        values: dict,
        limit: int,
        forward: bool,
    ) -> list[dict]:
        items: list[dict] = []
        start_key = None
        while len(items) < limit:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": key_condition,
                "ExpressionAttributeValues": values,
                "Limit": min(1000, limit - len(items)),
                "ScanIndexForward": forward,
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = table.query(**kwargs)
            items.extend(_from_dynamo(i) for i in resp.get("Items", []))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return items

    def _scan_all(self, table, *, limit: int) -> list[dict]:
        items: list[dict] = []
        start_key = None
        while len(items) < limit:
            kwargs: dict[str, Any] = {"Limit": min(100, limit - len(items))}
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = table.scan(**kwargs)
            items.extend(_from_dynamo(i) for i in resp.get("Items", []))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return items

    def _scan_filtered(
        self,
        table,
        *,
        filter_expression: str,
        values: dict,
        limit: int,
        max_pages: int = 25,
    ) -> list[dict]:
        matched: list[dict] = []
        start_key = None
        pages = 0
        while len(matched) < limit and pages < max_pages:
            kwargs: dict[str, Any] = {
                "FilterExpression": filter_expression,
                "ExpressionAttributeValues": values,
                "Limit": 100,
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = table.scan(**kwargs)
            pages += 1
            for raw in resp.get("Items", []):
                matched.append(_from_dynamo(raw))
                if len(matched) >= limit:
                    break
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return matched

    def write_checkpoint(self, checkpoint: dict) -> str:
        flight_id = checkpoint["flight_id"]
        key = f"checkpoints/{flight_id}/{checkpoint['saved_at'].replace(':', '-')}.json"
        self._s3.put_object(
            Bucket=self.settings.runway_raw_bucket,
            Key=key,
            Body=json.dumps(checkpoint, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        return key

    def read_checkpoint(self, key: str) -> dict:
        obj = self._s3.get_object(Bucket=self.settings.runway_raw_bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
