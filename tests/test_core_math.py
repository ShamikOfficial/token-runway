"""Pure math tests — no Docker needed."""

from datetime import date, datetime, timezone

import pytest

from runway_core.burn import ewma_daily_burn, spend_by_day, total_spend
from runway_core.pricing import cost_from_override, price_usage
from runway_core.runway import compute_runway


def test_ewma_reacts_to_recent_days():
    daily = {
        date(2026, 9, 1): 1.0,
        date(2026, 9, 2): 1.0,
        date(2026, 9, 3): 10.0,
    }
    slow = ewma_daily_burn(daily, alpha=0.2)
    fast = ewma_daily_burn(daily, alpha=0.8)
    assert fast > slow
    assert slow is not None


def test_spend_by_day_groups_utc():
    events = [
        {"occurred_at": "2026-09-01T10:00:00+00:00", "cost_usd": 1.5},
        {"occurred_at": "2026-09-01T22:00:00+00:00", "cost_usd": 0.5},
        {"occurred_at": datetime(2026, 9, 2, 1, 0, tzinfo=timezone.utc), "cost_usd": 2.0},
    ]
    by_day = spend_by_day(events)
    assert by_day[date(2026, 9, 1)] == pytest.approx(2.0)
    assert by_day[date(2026, 9, 2)] == pytest.approx(2.0)
    assert total_spend(events) == pytest.approx(4.0)


def test_runway_healthy_with_steady_burn():
    # $100 limit, spent $20 over 4 days at $5/day → usable after 10% bingo
    events = [
        {"occurred_at": f"2026-09-0{d}T12:00:00+00:00", "cost_usd": 5.0}
        for d in range(1, 5)
    ]
    result = compute_runway(limit_usd=100.0, events=events, ewma_alpha=0.5, bingo_reserve_pct=0.1)
    assert result["spent_usd"] == pytest.approx(20.0)
    assert result["remaining_usd"] == pytest.approx(80.0)
    assert result["bingo_reserve_usd"] == pytest.approx(10.0)
    assert result["usable_usd"] == pytest.approx(70.0)
    assert result["daily_burn_usd"] == pytest.approx(5.0)
    assert result["days_remaining"] == pytest.approx(14.0)
    assert result["status"] == "HEALTHY"


def test_runway_warning_under_two_weeks():
    events = [
        {"occurred_at": f"2026-09-0{d}T12:00:00+00:00", "cost_usd": 5.0}
        for d in range(1, 5)
    ]
    # usable 70 / burn 5 = 14 exactly was HEALTHY; nudge spent up so usable < 70
    events.append({"occurred_at": "2026-09-05T12:00:00+00:00", "cost_usd": 20.0})
    result = compute_runway(limit_usd=100.0, events=events, ewma_alpha=1.0, bingo_reserve_pct=0.1)
    assert result["days_remaining"] is not None
    assert result["days_remaining"] < 14
    assert result["status"] in {"WARNING", "CRITICAL"}


def test_runway_no_usage():
    result = compute_runway(limit_usd=50.0, events=[])
    assert result["status"] == "NO_BURN_YET"
    assert result["days_remaining"] is None


def test_runway_critical_when_almost_empty():
    events = [{"occurred_at": "2026-09-01T12:00:00+00:00", "cost_usd": 45.0}]
    result = compute_runway(limit_usd=50.0, events=events, bingo_reserve_pct=0.1)
    # remaining 5, bingo 5, usable 0
    assert result["status"] == "BINGO_OR_EMPTY"
    assert result["days_remaining"] == 0.0


def test_override_pricing():
    overrides = {
        "my-company/gpt-4o-license": {
            "input_cost_per_million": 2.5,
            "output_cost_per_million": 10.0,
        }
    }
    cost = cost_from_override("my-company/gpt-4o-license", 1_000_000, 1_000_000, overrides)
    assert cost == pytest.approx(12.5)


def test_litellm_prices_known_model():
    priced = price_usage("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500, overrides={})
    assert priced["price_source"] == "litellm"
    assert priced["cost_usd"] > 0
