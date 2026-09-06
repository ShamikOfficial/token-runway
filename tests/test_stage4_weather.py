from runway_core.weather import apply_weather_to_estimate, combined_save_pct


def test_tailwind_reduces_cost():
    estimate = {
        "model": "gpt-4o",
        "task_type": "agent",
        "estimated_turns": 5,
        "agent_depth": 2,
        "p50": {"cost_usd": 10.0, "tokens": 10000, "prompt_tokens": 7000, "completion_tokens": 3000, "price_source": "x"},
        "p90": {"cost_usd": 20.0, "tokens": 20000, "prompt_tokens": 14000, "completion_tokens": 6000, "price_source": "x"},
    }
    out = apply_weather_to_estimate(
        estimate,
        task_type="agent",
        tailwind_ids=["cap_turns"],
        risk_tags=[],
    )
    assert out["p90"]["cost_usd"] < 20.0
    assert out["weather"]["save_pct"] > 0


def test_headwind_increases_cost():
    estimate = {
        "model": "gpt-4o",
        "task_type": "agent",
        "estimated_turns": 5,
        "agent_depth": 2,
        "p50": {"cost_usd": 10.0, "tokens": 10000, "prompt_tokens": 7000, "completion_tokens": 3000, "price_source": "x"},
        "p90": {"cost_usd": 20.0, "tokens": 20000, "prompt_tokens": 14000, "completion_tokens": 6000, "price_source": "x"},
    }
    out = apply_weather_to_estimate(
        estimate,
        task_type="agent",
        tailwind_ids=[],
        risk_tags=["full_fs"],
    )
    assert out["p90"]["cost_usd"] > 20.0
    assert out["weather"]["surcharge_pct"] > 0


def test_diminishing_saves():
    rules = [
        {"estimated_save_pct": 50},
        {"estimated_save_pct": 50},
    ]
    # Not 100% — diminishing
    assert combined_save_pct(rules) < 100
    assert combined_save_pct(rules) > 50
