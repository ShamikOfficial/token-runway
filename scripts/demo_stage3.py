#!/usr/bin/env python3
"""Stage 3 E2E: start → burn → emergency land → top-up → resume same flight."""

from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"Stage 3 demo against {base}")
    with httpx.Client(base_url=base, timeout=60.0) as client:
        health = client.get("/health").json()
        print("health:", health)
        assert health.get("stage") >= 3

        budget = client.post(
            "/v1/budgets",
            json={"name": "Stage3 landing tank", "limit_usd": 3.0},
        ).json()
        bid = budget["budget_id"]

        plan = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "Fragile agent hop",
                "model": "gpt-4o-mini",
                "task_type": "chat",
                "estimated_turns": 2,
                "agent_depth": 1,
            },
        ).json()
        fid = plan["flight_id"]
        print("planned:", plan["takeoff"]["decision"], fid)

        started = client.post(f"/v1/flights/{fid}/start")
        started.raise_for_status()
        print("started:", started.json()["status"])

        for i in range(6):
            r = client.post(
                "/v1/usage",
                json={
                    "budget_id": bid,
                    "flight_id": fid,
                    "model": "gpt-4o",
                    "prompt_tokens": 80_000,
                    "completion_tokens": 20_000,
                },
            )
            if r.status_code == 409:
                print("auto/soft stop:", r.json().get("detail"))
                break
            r.raise_for_status()
            print(f"  burn {i+1}: ${r.json()['priced']['cost_usd']:.4f}")

        flight = client.get(f"/v1/flights/{fid}").json()
        if flight.get("status") != "LANDED_EMERGENCY":
            land = client.post(
                f"/v1/flights/{fid}/emergency-landing",
                json={"note": "Manual mayday — saving progress", "step": "draft-summary"},
            )
            land.raise_for_status()
            print("landed:", land.json()["flight"]["status"], land.json()["checkpoint_key"])
            ck = land.json()["checkpoint_key"]
        else:
            print("already landed:", flight.get("checkpoint_key"))
            ck = flight.get("checkpoint_key")

        assert ck, "expected checkpoint_key"
        cp = client.get(f"/v1/flights/{fid}/checkpoint")
        cp.raise_for_status()
        print("checkpoint reason:", cp.json()["checkpoint"]["reason"])

        blocked = client.post(
            "/v1/usage",
            json={
                "budget_id": bid,
                "flight_id": fid,
                "model": "gpt-4o-mini",
                "prompt_tokens": 100,
                "completion_tokens": 50,
            },
        )
        if blocked.status_code != 409:
            print("FAIL: expected 409 while landed", file=sys.stderr)
            return 1

        # Cap the tank at current spend so usable fuel is gone (bingo gate for resume)
        runway = client.get(f"/v1/budgets/{bid}/runway").json()["runway"]
        if float(runway["usable_usd"]) > 0:
            cap = client.patch(
                f"/v1/budgets/{bid}",
                json={"limit_usd": max(float(runway["spent_usd"]), 0.01)},
            )
            cap.raise_for_status()
            print("capped tank to spent so resume needs refuel")

        dry = client.post(f"/v1/flights/{fid}/resume")
        if dry.status_code != 400:
            print("FAIL: expected 400 resume before top-up", dry.status_code, dry.text, file=sys.stderr)
            return 1
        print("resume blocked until refuel:", dry.json().get("detail"))

        topped = client.patch(f"/v1/budgets/{bid}", json={"add_limit_usd": 20.0})
        topped.raise_for_status()
        print("topped limit_usd:", topped.json()["limit_usd"])

        resumed = client.post(f"/v1/flights/{fid}/resume", json={"note": "Refueled — continuing"})
        resumed.raise_for_status()
        assert resumed.json()["flight"]["flight_id"] == fid
        print("resumed same flight:", resumed.json()["flight"]["status"])

        hold = client.post(
            f"/v1/flights/{fid}/hold",
            json={"note": "Waiting on human", "step": "paused"},
        )
        hold.raise_for_status()
        print("holding:", hold.json()["flight"]["status"])
        from_hold = client.post(f"/v1/flights/{fid}/resume")
        from_hold.raise_for_status()
        print("resumed from hold:", from_hold.json()["flight"]["status"])

        box = client.get(f"/v1/budgets/{bid}/blackbox").json()
        print("blackbox events:", len(box["events"]))
        actions = {e["action"] for e in box["events"]}
        if "EMERGENCY_LANDING" not in actions or "BUDGET_TOP_UP" not in actions:
            print("FAIL: expected EMERGENCY_LANDING + BUDGET_TOP_UP in black box", actions, file=sys.stderr)
            return 1

        print("\nStage 3 E2E OK — Emergency Landing + top-up + same-flight resume + Holding.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
