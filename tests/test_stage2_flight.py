"""Unit tests for Stage 2 flight planning math."""

import pytest

from runway_core.flight_plan import estimate_flight_fuel, growing_token_total
from runway_core.forecast import forecast_horizon
from runway_core.preflight import abandon_takeoff_decision, preflight_checklist
from runway_core.tower import evaluate_tower_alerts


def test_agent_growth_burns_more_than_flat_chat():
    chat = growing_token_total(1500, turns=10, growth=1.0, agent_depth=1)
    agent = growing_token_total(8000, turns=10, growth=1.15, agent_depth=2)
    assert agent > chat * 5


def test_estimate_returns_p50_below_p90():
    est = estimate_flight_fuel(
        model="gpt-4o-mini",
        task_type="agent",
        estimated_turns=8,
        agent_depth=2,
    )
    assert est["p50"]["cost_usd"] < est["p90"]["cost_usd"]
    assert est["p50"]["tokens"] < est["p90"]["tokens"]


def test_abandon_when_p50_exceeds_usable():
    estimate = {
        "p50": {"cost_usd": 12.0},
        "p90": {"cost_usd": 20.0},
    }
    decision = abandon_takeoff_decision(
        remaining_usd=10.0,
        bingo_reserve_usd=1.0,
        estimate=estimate,
    )
    assert decision["decision"] == "ABANDON"
    assert decision["fuel_gap_usd"] > 0


def test_clear_when_p90_fits():
    estimate = {
        "p50": {"cost_usd": 1.0},
        "p90": {"cost_usd": 2.0},
    }
    decision = abandon_takeoff_decision(
        remaining_usd=50.0,
        bingo_reserve_usd=5.0,
        estimate=estimate,
    )
    assert decision["decision"] == "CLEAR"


def test_replan_when_tight():
    estimate = {
        "p50": {"cost_usd": 8.0},
        "p90": {"cost_usd": 15.0},
    }
    decision = abandon_takeoff_decision(
        remaining_usd=12.0,
        bingo_reserve_usd=1.0,
        estimate=estimate,
    )
    assert decision["decision"] == "REPLAN"


def test_preflight_fails_without_budget():
    estimate = {"p50": {"cost_usd": 1.0, "price_source": "litellm"}}
    result = preflight_checklist(
        budget=None,
        model="gpt-4o-mini",
        estimate=estimate,
        bingo_reserve_pct=0.1,
    )
    assert result["passed"] is False


def test_forecast_cold_start_uses_planned_only():
    fc = forecast_horizon(events=[], days=30, planned_extra_usd=5.0, planned_extra_tokens=10000)
    assert fc["p50_spend_usd"] == pytest.approx(5.0)
    assert fc["p50_tokens"] == 10000
    assert len(fc["series"]) == 30


def test_tower_critical_squawk():
    alerts = evaluate_tower_alerts(
        {"days_remaining": 1.5, "status": "CRITICAL", "note": "low fuel"}
    )
    assert alerts and alerts[0]["squawk"] == "7700"
