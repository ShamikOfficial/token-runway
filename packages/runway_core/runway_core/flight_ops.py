"""
In-flight ops — turbulence, Emergency Landing, Holding Pattern, resume.

Keep work recoverable when fuel dies mid-flight.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ACTIVE_STATUSES = {"IN_FLIGHT", "HOLDING"}
BLOCKED_STATUSES = {"LANDED_EMERGENCY", "ABANDON", "COMPLETED"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_turbulence(
    *,
    recent_hourly_burn: float,
    baseline_daily_burn: float | None,
    spike_factor: float = 3.0,
) -> dict[str, Any] | None:
    """
    If recent burn (scaled to a day) is spike_factor × baseline, call turbulence.
    recent_hourly_burn is $ spent in the last ~hour of the flight.
    """
    if baseline_daily_burn is None or baseline_daily_burn <= 0:
        return None
    projected_daily = recent_hourly_burn * 24.0
    if projected_daily >= baseline_daily_burn * spike_factor:
        return {
            "code": "TURBULENCE",
            "severity": "WARNING",
            "squawk": "7600",
            "message": (
                f"Burn accelerating — recent pace ~${projected_daily:.4f}/day "
                f"vs baseline ${baseline_daily_burn:.4f}/day."
            ),
            "projected_daily_usd": round(projected_daily, 6),
            "baseline_daily_usd": round(baseline_daily_burn, 6),
        }
    return None


def should_emergency_land(
    *,
    remaining_usd: float,
    bingo_reserve_usd: float,
    next_call_cost_usd: float = 0.0,
) -> bool:
    """Land if usable fuel can't cover the next call (or is already empty)."""
    usable = remaining_usd - bingo_reserve_usd
    return usable <= 0 or usable < next_call_cost_usd


def build_checkpoint(
    *,
    flight: dict,
    runway: dict,
    reason: str,
    progress: dict | None = None,
) -> dict[str, Any]:
    return {
        "flight_id": flight["flight_id"],
        "budget_id": flight["budget_id"],
        "saved_at": now_iso(),
        "reason": reason,
        "flight_status": flight.get("status"),
        "name": flight.get("name"),
        "model": flight.get("model"),
        "task_type": flight.get("task_type"),
        "progress": progress or flight.get("progress") or {},
        "runway_snapshot": {
            "remaining_usd": runway.get("remaining_usd"),
            "usable_usd": runway.get("usable_usd"),
            "spent_usd": runway.get("spent_usd"),
            "days_remaining": runway.get("days_remaining"),
            "status": runway.get("status"),
        },
        "estimate": flight.get("estimate"),
    }


def can_accept_usage(flight: dict | None) -> tuple[bool, str]:
    if flight is None:
        return True, "no flight binding"
    status = flight.get("status")
    if status == "IN_FLIGHT":
        return True, "ok"
    if status in {"CLEAR", "REPLAN"}:
        return False, "Start the flight before logging usage against it."
    if status == "HOLDING":
        return False, "Flight is in Holding Pattern — resume before burning more fuel."
    if status == "LANDED_EMERGENCY":
        return False, "Flight already Emergency Landed — resume with more budget first."
    if status == "ABANDON":
        return False, "Flight was abandoned at takeoff — replan instead."
    return False, f"Flight status '{status}' cannot accept usage."
