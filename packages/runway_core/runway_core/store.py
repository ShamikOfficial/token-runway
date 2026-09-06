"""DynamoDB + S3 persistence against Floci (or real AWS)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from runway_core.aws_clients import dynamodb_resource, s3_client
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
    """Budgets + usage events. Named FuelStore because Stage 1 is about fuel."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._db = dynamodb_resource(self.settings)
        self._s3 = s3_client(self.settings)
        self.budgets = self._db.Table(self.settings.runway_budgets_table)
        self.usage = self._db.Table(self.settings.runway_usage_table)

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
        self.budgets.put_item(Item=_to_dynamo(item))
        return item

    def get_budget(self, budget_id: str) -> dict | None:
        resp = self.budgets.get_item(Key={"budget_id": budget_id})
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def list_budgets(self, limit: int = 50) -> list[dict]:
        resp = self.budgets.scan(Limit=limit)
        return [_from_dynamo(i) for i in resp.get("Items", [])]

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
            "occurred_at": occurred_at,
            "metadata": metadata or {},
        }
        self.usage.put_item(Item=_to_dynamo(event))
        self._archive_raw_event(event)
        return event

    def list_usage(self, budget_id: str, limit: int = 500) -> list[dict]:
        resp = self.usage.query(
            KeyConditionExpression="budget_id = :b",
            ExpressionAttributeValues={":b": budget_id},
            Limit=limit,
            ScanIndexForward=True,
        )
        return [_from_dynamo(i) for i in resp.get("Items", [])]

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
