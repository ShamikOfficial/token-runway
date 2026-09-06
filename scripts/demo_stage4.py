#!/usr/bin/env python3
"""Stage 4: Tailwind saves fuel; Headwind adds safety surcharge; Crosswind shows both."""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Stage 4 demo against {base}")
    with httpx.Client(base_url=base, timeout=60.0) as client:
        books = client.get("/v1/weather/playbooks")
        books.raise_for_status()
        print("playbooks:", len(books.json()["tailwind"]), "tailwind /", len(books.json()["headwind"]), "headwind")

        bid = client.post("/v1/budgets", json={"name": "weather tank", "limit_usd": 40}).json()[
            "budget_id"
        ]

        base_plan = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "No weather",
                "model": "gpt-4o",
                "task_type": "agent",
                "estimated_turns": 10,
                "agent_depth": 2,
            },
        ).json()
        base_p90 = base_plan["estimate"]["p90"]["cost_usd"]

        tw = client.post(
            "/v1/weather/plan",
            json={
                "budget_id": bid,
                "name": "Tailwind only",
                "model": "gpt-4o",
                "task_type": "agent",
                "estimated_turns": 10,
                "agent_depth": 2,
                "tailwind_ids": ["cheaper_model", "cap_turns", "summarize_history"],
                "risk_tags": [],
            },
        ).json()
        tw_p90 = tw["estimate"]["p90"]["cost_usd"]
        print("tailwind p90", tw_p90, "vs base", base_p90, "save%", tw["weather"]["save_pct"])
        if tw_p90 >= base_p90:
            print("FAIL: Tailwind should reduce p90", file=sys.stderr)
            return 1

        hw = client.post(
            "/v1/weather/plan",
            json={
                "budget_id": bid,
                "name": "Headwind full_fs",
                "model": "gpt-4o",
                "task_type": "agent",
                "estimated_turns": 10,
                "agent_depth": 2,
                "tailwind_ids": [],
                "risk_tags": ["full_fs"],
            },
        ).json()
        hw_p90 = hw["estimate"]["p90"]["cost_usd"]
        print("headwind p90", hw_p90, "surcharge%", hw["weather"]["surcharge_pct"])
        if hw_p90 <= base_p90:
            print("FAIL: Headwind should increase p90", file=sys.stderr)
            return 1

        cx = client.post(
            "/v1/weather/plan",
            json={
                "budget_id": bid,
                "name": "Crosswind",
                "model": "gpt-4o",
                "task_type": "agent",
                "estimated_turns": 10,
                "agent_depth": 2,
                "tailwind_ids": ["cap_turns"],
                "risk_tags": ["full_fs", "code_exec"],
            },
        ).json()
        print("crosswind:", cx["weather"]["crosswind_note"])
        assert cx["weather"]["crosswind"] is True
        assert "diversion" in cx["suggestions"]

        print("\nStage 4 E2E OK — Tailwind / Headwind / Crosswind.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
