#!/usr/bin/env python3
"""Stage 5: weight & balance, ground stop, NOTAMs."""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Stage 5 demo against {base}")
    with httpx.Client(base_url=base, timeout=60.0) as client:
        for name, limit in [("alpha", 10), ("bravo", 30)]:
            client.post("/v1/budgets", json={"name": name, "limit_usd": limit}).raise_for_status()

        wb = client.get("/v1/fleet/weight-balance")
        wb.raise_for_status()
        print("weight-balance budgets:", len(wb.json()["budgets"]))

        client.post(
            "/v1/fleet/notams",
            json={
                "code": "PRICE_CHANGE",
                "message": "gpt-4o public rates changed — refresh overrides if licensed.",
                "severity": "INFO",
            },
        ).raise_for_status()
        notams = client.get("/v1/fleet/notams").json()["notams"]
        print("notams:", notams[0]["code"] if notams else None)

        client.post(
            "/v1/fleet/ground-stop",
            json={"active": True, "reason": "Incident drill"},
        ).raise_for_status()
        bid = client.post("/v1/budgets", json={"name": "blocked", "limit_usd": 5}).json()[
            "budget_id"
        ]
        blocked = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "should fail",
                "model": "gpt-4o-mini",
                "task_type": "chat",
                "estimated_turns": 1,
                "agent_depth": 1,
            },
        )
        if blocked.status_code != 423:
            print("FAIL: expected ground stop 423", blocked.status_code, blocked.text, file=sys.stderr)
            return 1
        print("ground stop blocked takeoff: 423 OK")

        client.post("/v1/fleet/ground-stop", json={"active": False}).raise_for_status()
        ok = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "after reopen",
                "model": "gpt-4o-mini",
                "task_type": "chat",
                "estimated_turns": 1,
                "agent_depth": 1,
            },
        )
        ok.raise_for_status()
        print("airspace reopened:", ok.json()["takeoff"]["decision"])

        print("\nStage 5 E2E OK — fleet controls.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
