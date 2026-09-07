"""
Fleet controls — Weight & Balance, Ground Stop, NOTAMs (Stage 5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def weight_and_balance(
    *,
    budgets: list[dict],
    spends: dict[str, float],
    warn_share: float = 0.5,
) -> dict[str, Any]:
    """
    How fuel is distributed across projects/budgets.
    Wake turbulence: one budget eating > warn_share of total remaining.
    """
    rows = []
    total_limit = 0.0
    total_remaining = 0.0
    for b in budgets:
        bid = b["budget_id"]
        limit = float(b["limit_usd"])
        spent = float(spends.get(bid, 0.0))
        remaining = max(limit - spent, 0.0)
        total_limit += limit
        total_remaining += remaining
        rows.append(
            {
                "budget_id": bid,
                "name": b.get("name"),
                "limit_usd": limit,
                "spent_usd": round(spent, 6),
                "remaining_usd": round(remaining, 6),
            }
        )

    total_spent = sum(float(r["spent_usd"]) for r in rows)
    for row in rows:
        row["share_of_remaining"] = (
            round(row["remaining_usd"] / total_remaining, 4) if total_remaining > 0 else 0.0
        )
        row["share_of_spend"] = (
            round(row["spent_usd"] / total_spent, 4) if total_spent > 0 else 0.0
        )

    # Wake turbulence: one tank burned a disproportionate share of fleet spend
    wake = [r for r in rows if r["share_of_spend"] >= warn_share]

    return {
        "total_limit_usd": round(total_limit, 6),
        "total_remaining_usd": round(total_remaining, 6),
        "budgets": rows,
        "wake_turbulence": wake,
        "wake_turbulence_alert": bool(wake),
    }


def evaluate_ground_stop(org_flags: dict | None) -> dict[str, Any]:
    flags = org_flags or {}
    active = bool(flags.get("ground_stop"))
    return {
        "ground_stop": active,
        "reason": flags.get("ground_stop_reason"),
        "since": flags.get("ground_stop_since"),
        "message": "Ground Stop active — no new takeoffs."
        if active
        else "Airspace open — takeoffs allowed.",
    }


def build_notam(
    *,
    code: str,
    message: str,
    severity: str = "INFO",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "issued_at": now_iso(),
    }
