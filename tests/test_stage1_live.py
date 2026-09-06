"""
Live Floci integration checks (API must already be up on :8000).

  python -m pytest tests/test_stage1_live.py -q
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


def test_health_reports_floci():
    data = httpx.get(f"{BASE}/health", timeout=10.0).json()
    assert data["ok"] is True
    assert data["stage"] == 1
    assert data["floci"] is True


def test_override_pricing_and_runway_flow():
    client = httpx.Client(base_url=BASE, timeout=30.0)
    budget = client.post("/v1/budgets", json={"name": "override tank", "limit_usd": 100}).json()
    bid = budget["budget_id"]

    usage = client.post(
        "/v1/usage",
        json={
            "budget_id": bid,
            "model": "my-company/gpt-4o-license",
            "prompt_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
            "project_id": "license-demo",
        },
    )
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["priced"]["price_source"] == "override"
    assert body["priced"]["cost_usd"] == pytest.approx(12.5)

    runway = client.get(f"/v1/budgets/{bid}/runway").json()["runway"]
    assert runway["spent_usd"] == pytest.approx(12.5)
    assert runway["event_count"] == 1
    assert runway["days_remaining"] is not None


def test_dashboard_html_served():
    r = httpx.get(f"{BASE}/", timeout=10.0)
    assert r.status_code == 200
    assert "TokenRunway" in r.text
