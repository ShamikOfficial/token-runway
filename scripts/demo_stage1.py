#!/usr/bin/env python3
"""
Stage 1 exit-criteria demo:
  create budget → post 20 usage events across several days → print runway.

Point AWS_ENDPOINT_URL at Floci (compose network or localhost:4566).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="TokenRunway Stage 1 demo")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Demo against {base}")
    with httpx.Client(base_url=base, timeout=30.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        budget = client.post(
            "/v1/budgets",
            json={"name": "Stage1 demo tank", "limit_usd": 20.0},
        )
        budget.raise_for_status()
        budget_id = budget.json()["budget_id"]
        print("budget:", budget_id)

        start = datetime.now(timezone.utc) - timedelta(days=9)
        models = ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"]
        for i in range(20):
            when = start + timedelta(days=i // 2, hours=i)
            # Keep burn realistic so days_remaining is in the "weeks" ballpark, not millennia.
            body = {
                "budget_id": budget_id,
                "model": models[i % len(models)],
                "prompt_tokens": 80_000 + i * 4_000,
                "completion_tokens": 20_000 + i * 1_000,
                "project_id": "stage1-demo",
                "occurred_at": when.isoformat(),
            }
            resp = client.post("/v1/usage", json=body)
            resp.raise_for_status()
            priced = resp.json()["priced"]
            print(
                f"  event {i+1:02d}  {body['model']:<28}  "
                f"${priced['cost_usd']:.6f}  via {priced['price_source']}"
            )

        runway = client.get(f"/v1/budgets/{budget_id}/runway")
        runway.raise_for_status()
        data = runway.json()["runway"]
        print("\n--- RUNWAY ---")
        for key in (
            "limit_usd",
            "spent_usd",
            "remaining_usd",
            "usable_usd",
            "daily_burn_usd",
            "days_remaining",
            "status",
            "note",
            "event_count",
            "days_with_usage",
        ):
            print(f"  {key}: {data[key]}")

        if data["event_count"] != 20:
            print("FAIL: expected 20 events", file=sys.stderr)
            return 1
        if data["days_remaining"] is None:
            print("FAIL: days_remaining should be a number", file=sys.stderr)
            return 1
        if data["spent_usd"] <= 0:
            print("FAIL: spent should be > 0", file=sys.stderr)
            return 1
        days = data["days_remaining"]
        if days is None or not (0 < float(days) < 3650):
            print(f"FAIL: days_remaining out of sane range: {days}", file=sys.stderr)
            return 1
        if data["status"] not in {"HEALTHY", "WARNING", "CRITICAL"}:
            print(f"FAIL: unexpected status {data['status']}", file=sys.stderr)
            return 1

        print("\nStage 1 demo OK — runway looks sane.")
        print(f"Dashboard: {base}/")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
