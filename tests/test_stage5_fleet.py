from runway_core.fleet import build_notam, evaluate_ground_stop, weight_and_balance


def test_weight_and_balance_wake():
    budgets = [
        {"budget_id": "a", "name": "A", "limit_usd": 100},
        {"budget_id": "b", "name": "B", "limit_usd": 100},
    ]
    spends = {"a": 60.0, "b": 5.0}
    result = weight_and_balance(budgets=budgets, spends=spends, warn_share=0.5)
    assert result["total_limit_usd"] == 200
    assert result["wake_turbulence_alert"] is True
    assert result["wake_turbulence"][0]["budget_id"] == "a"


def test_ground_stop_messages():
    open_air = evaluate_ground_stop({"ground_stop": False})
    assert open_air["ground_stop"] is False
    closed = evaluate_ground_stop({"ground_stop": True, "ground_stop_reason": "freeze"})
    assert closed["ground_stop"] is True
    assert "Ground Stop" in closed["message"]


def test_notam_shape():
    note = build_notam(code="PRICE_CHANGE", message="rates up", severity="WARN")
    assert note["code"] == "PRICE_CHANGE"
    assert note["severity"] == "WARN"
    assert "issued_at" in note
