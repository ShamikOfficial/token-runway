#!/usr/bin/env python3
"""
Create the DynamoDB tables + S3 bucket TokenRunway expects on Floci.

Safe to re-run — skips things that already exist.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running without install: repo root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "runway_core"))

from botocore.exceptions import ClientError

from runway_core.aws_clients import dynamodb_client, s3_client
from runway_core.settings import get_settings


def wait_a_sec(msg: str) -> None:
    print(msg)
    time.sleep(0.4)


def ensure_budgets_table(client, table_name: str) -> None:
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"  budgets table already there: {table_name}")
        return

    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "budget_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "budget_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_a_sec(f"  created budgets table: {table_name}")


def ensure_usage_table(client, table_name: str) -> None:
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"  usage table already there: {table_name}")
        return

    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "budget_id", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "budget_id", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_a_sec(f"  created usage table: {table_name}")


def ensure_bucket(client, bucket: str, region: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        print(f"  bucket already there: {bucket}")
        return
    except ClientError:
        pass

    # us-east-1 hates LocationConstraint; everywhere else needs it
    if region == "us-east-1":
        client.create_bucket(Bucket=bucket)
    else:
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    print(f"  created bucket: {bucket}")


def main() -> int:
    settings = get_settings()
    print("Seeding Floci / AWS for TokenRunway Stage 1")
    print(f"  endpoint: {settings.aws_endpoint_url or '(real AWS)'}")
    print(f"  region:   {settings.aws_default_region}")

    ddb = dynamodb_client(settings)
    s3 = s3_client(settings)

    ensure_budgets_table(ddb, settings.runway_budgets_table)
    ensure_usage_table(ddb, settings.runway_usage_table)
    ensure_bucket(s3, settings.runway_raw_bucket, settings.aws_default_region)

    print("Done. Fuel tanks are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
