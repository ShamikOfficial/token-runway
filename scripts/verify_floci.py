"""Confirm S3 archive + DynamoDB really landed in Floci."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Host machine talks to published Floci port
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("RUNWAY_ENV", "local")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "runway_core"))

import httpx

from runway_core.aws_clients import dynamodb_client, s3_client
from runway_core.settings import get_settings


def main() -> int:
    base = os.environ.get("RUNWAY_API_BASE", "http://localhost:8000")
    get_settings.cache_clear()
    settings = get_settings()

    with httpx.Client(base_url=base, timeout=30.0) as client:
        budget = client.post("/v1/budgets", json={"name": "floci proof", "limit_usd": 10}).json()
        bid = budget["budget_id"]
        usage = client.post(
            "/v1/usage",
            json={
                "budget_id": bid,
                "model": "gpt-4o-mini",
                "prompt_tokens": 5000,
                "completion_tokens": 1000,
            },
        )
        usage.raise_for_status()
        event_id = usage.json()["event"]["event_id"]

    ddb = dynamodb_client(settings)
    tables = ddb.list_tables()["TableNames"]
    assert settings.runway_budgets_table in tables, tables
    assert settings.runway_usage_table in tables, tables

    s3 = s3_client(settings)
    key = f"usage/{bid}/{event_id}.json"
    obj = s3.get_object(Bucket=settings.runway_raw_bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    assert event_id in body
    print(
        f"Floci proof OK — DynamoDB tables present, "
        f"S3 object s3://{settings.runway_raw_bucket}/{key}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
