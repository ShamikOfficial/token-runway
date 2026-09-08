"""Pre-flight checklist + Abandon Takeoff decision."""

from __future__ import annotations

from typing import Any


def preflight_checklist(
    *,
    budget: dict | None,
    model: str,
    estimate: dict[str, Any],
    bingo_reserve_pct: float,
) -> dict[str, Any]:
    """Simple gates we want green before Clear for Takeoff."""
    checks = []

    budget_ok = budget is not None
    checks.append(
        {
            "id": "budget_exists",
            "ok": budget_ok,
            "detail": "Budget found" if budget_ok else "Budget missing — create one first",
        }
    )

    price_ok = estimate.get("p50", {}).get("cost_usd", 0) >= 0 and bool(
        estimate.get("p50", {}).get("price_source")
    )
    checks.append(
        {
            "id": "price_known",
            "ok": price_ok,
            "detail": f"Model priced via {estimate.get('p50', {}).get('price_source', '?')}"
            if price_ok
            else f"Cannot price model '{model}'",
        }
    )

    bingo_ok = 0 <= bingo_reserve_pct < 1
    checks.append(
        {
            "id": "bingo_reserve_set",
            "ok": bingo_ok,
            "detail": f"Bingo reserve {bingo_reserve_pct:.0%} of tank"
            if bingo_ok
            else "Bingo reserve misconfigured",
        }
    )

    return {
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
    }


def abandon_takeoff_decision(
    *,
    remaining_usd: float,
    bingo_reserve_usd: float,
    estimate: dict[str, Any],
) -> dict[str, Any]:
    """
    CLEAR  — p90 fits in usable fuel with room
    REPLAN — p50 fits but p90 is tight / over
    ABANDON — even p50 blows past usable fuel
    """
    usable = max(remaining_usd - bingo_reserve_usd, 0.0)
    p50 = float(estimate["p50"]["cost_usd"])
    p90 = float(estimate["p90"]["cost_usd"])

    suggestions: list[str] = []

    if p50 > usable:
        decision = "ABANDON"
        reason = (
            f"p50 fuel ${p50:.4f} needs more than usable ${usable:.4f} "
            f"(remaining ${remaining_usd:.4f} minus bingo ${bingo_reserve_usd:.4f})."
        )
        suggestions = [
            "Top up the budget before starting",
            "Cut estimated_turns or agent_depth",
            "Switch to a cheaper model",
            "Change task_type from agent → chat/batch if the work allows",
        ]
    elif p90 > usable or p50 > usable * 0.8:
        decision = "REPLAN"
        reason = (
            f"p50 ${p50:.4f} might fit in usable ${usable:.4f}, "
            f"but p90 ${p90:.4f} is too close / over — tighten the plan."
        )
        suggestions = [
            "Reduce turns or agent depth",
            "Use a cheaper model for exploratory passes",
            "Top up so p90 fits with margin",
        ]
    else:
        decision = "CLEAR"
        reason = (
            f"p90 ${p90:.4f} fits in usable ${usable:.4f}. "
            "Clear for takeoff — still watch burn in flight."
        )
        suggestions = ["Log usage against this flight once it is IN_FLIGHT"]

    return {
        "decision": decision,
        "reason": reason,
        "usable_usd": round(usable, 6),
        "remaining_usd": round(remaining_usd, 6),
        "bingo_reserve_usd": round(bingo_reserve_usd, 6),
        "p50_cost_usd": round(p50, 6),
        "p90_cost_usd": round(p90, 6),
        "fuel_gap_usd": round(max(p90 - usable, 0.0), 6),
        "suggestions": suggestions,
    }
