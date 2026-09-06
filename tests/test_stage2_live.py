"""
Live Stage 2 checks (API on :8000).
"""

from __future__ import annotations

import os

import httpx
import pytest

BASE = os.environ.get("RUNWAY_API_BASE", "http://localhost:8000")


def _api_up() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not running on :8000")


def test_abandon_then_clear_flow():
    client = httpx.Client(base_url=BASE, timeout=60.0)
    bid = client.post("/v1/budgets", json={"name": "live stage2", "limit_usd": 1.5}).json()[
        "budget_id"
    ]

    heavy = client.post(
        "/v1/flights/plan",
        json={
            "budget_id": bid,
            "name": "too heavy",
            "model": "gpt-4o",
            "task_type": "agent",
            "estimated_turns": 25,
            "agent_depth": 5,
        },
    )
    assert heavy.status_code == 200, heavy.text
    assert heavy.json()["takeoff"]["decision"] == "ABANDON"

    light = client.post(
        "/v1/flights/plan",
        json={
            "budget_id": bid,
            "name": "light",
            "model": "gpt-4o-mini",
            "task_type": "chat",
            "estimated_turns": 2,
            "agent_depth": 1,
        },
    )
    assert light.status_code == 200, light.text
    assert light.json()["takeoff"]["decision"] in {"CLEAR", "REPLAN"}

    forecast = client.get(f"/v1/budgets/{bid}/forecast", params={"days": 30})
    assert forecast.status_code == 200
    assert "forecast" in forecast.json()

    tower = client.post(f"/v1/budgets/{bid}/tower/scan")
    assert tower.status_code == 200
    assert "alerts" in tower.json()
