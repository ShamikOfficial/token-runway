#!/usr/bin/env python3
"""
Stage 2 E2E:
  tiny budget + heavy agent plan → ABANDON
  shrink plan → CLEAR
  30-day forecast + tower scan
"""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Stage 2 demo against {base}")
    with httpx.Client(base_url=base, timeout=60.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health:", health.json())
        budget = client.post(
            "/v1/budgets",
            json={"name": "Stage2 tiny tank", "limit_usd": 2.0},
        )
        budget.raise_for_status()
        bid = budget.json()["budget_id"]
        print("budget:", bid)

        heavy = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "Heavy agent weekend",
                "model": "gpt-4o",
                "task_type": "agent",
                "estimated_turns": 20,
                "agent_depth": 4,
            },
        )
        heavy.raise_for_status()
        heavy_body = heavy.json()
        print(
            "heavy takeoff:",
            heavy_body["takeoff"]["decision"],
            "| p90 $",
            heavy_body["estimate"]["p90"]["cost_usd"],
        )
        if heavy_body["takeoff"]["decision"] != "ABANDON":
            print("FAIL: expected ABANDON on heavy plan", file=sys.stderr)
            return 1

        light = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "Light chat pass",
                "model": "gpt-4o-mini",
                "task_type": "chat",
                "estimated_turns": 3,
                "agent_depth": 1,
            },
        )
        light.raise_for_status()
        light_body = light.json()
        print(
            "light takeoff:",
            light_body["takeoff"]["decision"],
            "| p90 $",
            light_body["estimate"]["p90"]["cost_usd"],
        )
        if light_body["takeoff"]["decision"] not in {"CLEAR", "REPLAN"}:
            print("FAIL: expected CLEAR or REPLAN after shrink", file=sys.stderr)
            return 1

        # Seed a bit of usage so forecast has burn history
        for i in range(5):
            client.post(
                "/v1/usage",
                json={
                    "budget_id": bid,
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 2000,
                    "completion_tokens": 500,
                    "occurred_at": f"2026-09-0{i+1}T12:00:00+00:00",
                },
            ).raise_for_status()

        # Top up style: create a healthier budget for forecast/tower story
        rich = client.post(
            "/v1/budgets",
            json={"name": "Stage2 forecast tank", "limit_usd": 50.0},
        ).json()
        rid = rich["budget_id"]
        for i in range(8):
            client.post(
                "/v1/usage",
                json={
                    "budget_id": rid,
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 50_000,
                    "completion_tokens": 10_000,
                    "occurred_at": f"2026-09-0{(i % 9) + 1}T15:00:00+00:00",
                },
            ).raise_for_status()

        planned = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": rid,
                "name": "Planned agent leg",
                "model": "gpt-4o-mini",
                "task_type": "agent",
                "estimated_turns": 6,
                "agent_depth": 2,
            },
        )
        planned.raise_for_status()
        flight_id = planned.json()["flight_id"]

        forecast = client.get(
            f"/v1/budgets/{rid}/forecast",
            params={"days": 30, "flight_id": flight_id},
        )
        forecast.raise_for_status()
        fc = forecast.json()["forecast"]
        print(
            "forecast 30d p50/p90 $",
            fc["p50_spend_usd"],
            "/",
            fc["p90_spend_usd"],
            "| tokens",
            fc["p50_tokens"],
            "/",
            fc["p90_tokens"],
        )
        if fc["p50_spend_usd"] <= 0:
            print("FAIL: forecast p50 should be > 0", file=sys.stderr)
            return 1

        tower = client.post(f"/v1/budgets/{rid}/tower/scan")
        tower.raise_for_status()
        tower_body = tower.json()
        print(
            "tower:",
            "all_clear=" + str(tower_body["all_clear"]),
            "| alerts=",
            len(tower_body["alerts"]),
        )

        print("\nStage 2 E2E OK — Abandon Takeoff, forecast, tower scan.")
        print(f"Dashboard: {base}/")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
