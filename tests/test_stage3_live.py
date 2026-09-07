"""Live API: budget top-up + Stage 3 resume story (skipped if API down)."""

from __future__ import annotations

import httpx
import pytest

BASE = "http://localhost:8000"


def _api_up() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not running on :8000")


def test_top_up_then_resume_same_flight():
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        budget = client.post("/v1/budgets", json={"name": "live-topup", "limit_usd": 2.5}).json()
        bid = budget["budget_id"]
        plan = client.post(
            "/v1/flights/plan",
            json={
                "budget_id": bid,
                "name": "live hop",
                "model": "gpt-4o-mini",
                "task_type": "chat",
                "estimated_turns": 2,
                "agent_depth": 1,
            },
        ).json()
        fid = plan["flight_id"]
        client.post(f"/v1/flights/{fid}/start").raise_for_status()
        for _ in range(8):
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
                break
            r.raise_for_status()
        flight = client.get(f"/v1/flights/{fid}").json()
        if flight["status"] != "LANDED_EMERGENCY":
            client.post(f"/v1/flights/{fid}/emergency-landing").raise_for_status()
        runway = client.get(f"/v1/budgets/{bid}/runway").json()["runway"]
        if float(runway["usable_usd"]) > 0:
            client.patch(
                f"/v1/budgets/{bid}",
                json={"limit_usd": max(float(runway["spent_usd"]), 0.01)},
            ).raise_for_status()
        assert client.post(f"/v1/flights/{fid}/resume").status_code == 400
        topped = client.patch(f"/v1/budgets/{bid}", json={"add_limit_usd": 25.0})
        topped.raise_for_status()
        resumed = client.post(f"/v1/flights/{fid}/resume")
        resumed.raise_for_status()
        assert resumed.json()["flight"]["status"] == "IN_FLIGHT"
        assert resumed.json()["flight"]["flight_id"] == fid
