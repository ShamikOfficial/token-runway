"""Runway = how many days of fuel you have left at the current burn rate."""

from __future__ import annotations

from typing import Any

from runway_core.burn import ewma_daily_burn, spend_by_day, total_spend


def compute_runway(
    *,
    limit_usd: float,
    events: list[dict],
    ewma_alpha: float = 0.3,
    bingo_reserve_pct: float = 0.10,
) -> dict[str, Any]:
    """
    Plain English:
    - spent so far from events
    - remaining = limit - spent
    - usable = remaining after bingo reserve (we keep a slice for emergencies later)
    - daily_burn = EWMA of per-day spend
    - days_remaining = usable / daily_burn
    """
    spent = total_spend(events)
    remaining = max(limit_usd - spent, 0.0)
    bingo_reserve = max(limit_usd * bingo_reserve_pct, 0.0)
    usable = max(remaining - bingo_reserve, 0.0)

    daily = spend_by_day(events)
    daily_burn = ewma_daily_burn(daily, alpha=ewma_alpha)

    days_remaining: float | None
    status: str
    note: str

    if spent <= 0 or daily_burn is None:
        days_remaining = None
        status = "NO_BURN_YET"
        note = "No usage yet — post some /v1/usage events to estimate runway."
    elif daily_burn <= 0:
        days_remaining = None
        status = "ZERO_BURN"
        note = "Burn math came out zero — check that costs are pricing correctly."
    elif usable <= 0:
        days_remaining = 0.0
        status = "BINGO_OR_EMPTY"
        note = "You're at or below bingo fuel. Top up or stop burning."
    else:
        days_remaining = round(usable / daily_burn, 2)
        if days_remaining < 3:
            status = "CRITICAL"
            note = "Less than ~3 days of usable fuel at current burn."
        elif days_remaining < 14:
            status = "WARNING"
            note = "Under two weeks of usable fuel — plan a top-up or cut burn."
        else:
            status = "HEALTHY"
            note = "Runway looks comfortable at the current burn rate."

    return {
        "limit_usd": round(limit_usd, 6),
        "spent_usd": round(spent, 6),
        "remaining_usd": round(remaining, 6),
        "bingo_reserve_usd": round(bingo_reserve, 6),
        "usable_usd": round(usable, 6),
        "daily_burn_usd": None if daily_burn is None else round(daily_burn, 6),
        "days_remaining": days_remaining,
        "days_with_usage": len(daily),
        "event_count": len(events),
        "status": status,
        "note": note,
        "daily_spend": {d.isoformat(): round(v, 6) for d, v in daily.items()},
    }
