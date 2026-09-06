"""30-day spend / token forecast from observed burn (+ optional planned flight)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from runway_core.burn import ewma_daily_burn, spend_by_day, total_spend


def forecast_horizon(
    *,
    events: list[dict],
    days: int = 30,
    ewma_alpha: float = 0.3,
    planned_extra_usd: float = 0.0,
    planned_extra_tokens: int = 0,
) -> dict[str, Any]:
    """
    p50 ≈ EWMA daily burn * days (+ any planned flight fuel)
    p90 ≈ p50 * uplift based on day-to-day volatility (capped)
    """
    days = max(int(days), 1)
    daily = spend_by_day(events)
    burn = ewma_daily_burn(daily, alpha=ewma_alpha)

    if burn is None or burn <= 0:
        # Cold start — only planned flight shows up
        p50_spend = float(planned_extra_usd)
        p90_spend = float(planned_extra_usd) * 1.4
        note = "Not enough usage history — forecast leans on the planned flight only."
        daily_burn = 0.0
        uplift = 1.4
    else:
        daily_burn = float(burn)
        values = list(daily.values())
        if len(values) >= 2:
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            std = var**0.5
            # More jitter → higher p90 uplift, keep it sane
            uplift = min(2.0, max(1.25, 1.0 + (std / mean if mean > 0 else 0.5)))
        else:
            uplift = 1.35

        p50_spend = daily_burn * days + float(planned_extra_usd)
        p90_spend = daily_burn * uplift * days + float(planned_extra_usd) * uplift
        note = f"Projected from EWMA daily burn ${daily_burn:.4f}/day over {days} days."

    # Token forecast: rough from historical avg tokens/day if present
    token_days: dict[date, int] = {}
    for event in events:
        from runway_core.burn import as_utc_date

        day = as_utc_date(event["occurred_at"])
        token_days[day] = token_days.get(day, 0) + int(event.get("total_tokens") or 0)

    if token_days:
        avg_tokens = sum(token_days.values()) / len(token_days)
    else:
        avg_tokens = 0.0

    p50_tokens = int(round(avg_tokens * days + planned_extra_tokens))
    p90_tokens = int(round(avg_tokens * days * uplift + planned_extra_tokens * uplift))

    start = date.today()
    series = []
    for i in range(1, days + 1):
        series.append(
            {
                "day": (start + timedelta(days=i)).isoformat(),
                "p50_spend_usd": round(daily_burn * i + float(planned_extra_usd) * (i / days), 6)
                if burn
                else round(float(planned_extra_usd) * (i / days), 6),
                "p90_spend_usd": round(
                    daily_burn * uplift * i + float(planned_extra_usd) * uplift * (i / days), 6
                )
                if burn
                else round(float(planned_extra_usd) * uplift * (i / days), 6),
            }
        )

    return {
        "horizon_days": days,
        "daily_burn_usd": round(daily_burn, 6),
        "p90_uplift": round(uplift, 3),
        "spent_to_date_usd": round(total_spend(events), 6),
        "p50_spend_usd": round(p50_spend, 6),
        "p90_spend_usd": round(p90_spend, 6),
        "p50_tokens": p50_tokens,
        "p90_tokens": p90_tokens,
        "planned_extra_usd": round(float(planned_extra_usd), 6),
        "planned_extra_tokens": int(planned_extra_tokens),
        "note": note,
        "series": series,
    }
