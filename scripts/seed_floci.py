#!/usr/bin/env python3
"""
Create the DynamoDB tables + S3 bucket + SNS topic TokenRunway expects on Floci.

Safe to re-run — skips things that already exist.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "runway_core"))

from botocore.exceptions import ClientError

from runway_core.aws_clients import dynamodb_client, s3_client, sns_client
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


def ensure_flights_table(client, table_name: str) -> None:
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"  flights table already there: {table_name}")
        return

    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "flight_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "flight_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_a_sec(f"  created flights table: {table_name}")


def ensure_bucket(client, bucket: str, region: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        print(f"  bucket already there: {bucket}")
        return
    except ClientError:
        pass

    if region == "us-east-1":
        client.create_bucket(Bucket=bucket)
    else:
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    print(f"  created bucket: {bucket}")


def ensure_audit_table(client, table_name: str) -> None:
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"  audit table already there: {table_name}")
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
    wait_a_sec(f"  created audit table: {table_name}")


def ensure_meta_table(client, table_name: str) -> None:
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"  meta table already there: {table_name}")
        return

    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_a_sec(f"  created meta table: {table_name}")


def ensure_tower_topic(client, topic_name: str) -> None:
    resp = client.create_topic(Name=topic_name)
    print(f"  tower SNS topic ready: {resp['TopicArn']}")


def main() -> int:
    settings = get_settings()
    print("Seeding Floci / AWS for TokenRunway")
    print(f"  endpoint: {settings.aws_endpoint_url or '(real AWS)'}")
    print(f"  region:   {settings.aws_default_region}")

    ddb = dynamodb_client(settings)
    s3 = s3_client(settings)
    sns = sns_client(settings)

    ensure_budgets_table(ddb, settings.runway_budgets_table)
    ensure_usage_table(ddb, settings.runway_usage_table)
    ensure_flights_table(ddb, settings.runway_flights_table)
    ensure_audit_table(ddb, settings.runway_audit_table)
    ensure_meta_table(ddb, settings.runway_meta_table)
    ensure_bucket(s3, settings.runway_raw_bucket, settings.aws_default_region)
    ensure_tower_topic(sns, settings.runway_tower_topic)

    print("Done. Fuel tanks, tower, black box, and fleet meta are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
