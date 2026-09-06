from runway_core.flight_ops import (
    build_checkpoint,
    can_accept_usage,
    detect_turbulence,
    should_emergency_land,
)


def test_bingo_triggers_landing():
    assert should_emergency_land(remaining_usd=1.0, bingo_reserve_usd=1.0) is True
    assert should_emergency_land(remaining_usd=10.0, bingo_reserve_usd=1.0, next_call_cost_usd=0.5) is False
    assert should_emergency_land(remaining_usd=10.0, bingo_reserve_usd=1.0, next_call_cost_usd=20.0) is True


def test_turbulence_spike():
    alert = detect_turbulence(recent_hourly_burn=2.0, baseline_daily_burn=5.0, spike_factor=3.0)
    # 2*24=48 vs baseline 5 → spike
    assert alert is not None
    assert alert["code"] == "TURBULENCE"


def test_usage_gate_states():
    assert can_accept_usage({"status": "IN_FLIGHT"})[0] is True
    assert can_accept_usage({"status": "CLEAR"})[0] is False
    assert can_accept_usage({"status": "HOLDING"})[0] is False
    assert can_accept_usage({"status": "LANDED_EMERGENCY"})[0] is False


def test_checkpoint_shape():
    ck = build_checkpoint(
        flight={"flight_id": "f1", "budget_id": "b1", "status": "IN_FLIGHT", "name": "x"},
        runway={"remaining_usd": 1.0, "usable_usd": 0.5, "spent_usd": 2.0, "days_remaining": 1, "status": "CRITICAL"},
        reason="EMERGENCY_LANDING",
        progress={"step": "saved"},
    )
    assert ck["flight_id"] == "f1"
    assert ck["reason"] == "EMERGENCY_LANDING"
    assert ck["progress"]["step"] == "saved"
