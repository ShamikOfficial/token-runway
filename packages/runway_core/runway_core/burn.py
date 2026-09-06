"""Daily burn + EWMA — the 'how fast are we burning fuel' math."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable


def as_utc_date(value: str | datetime | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    # ISO string
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def spend_by_day(events: Iterable[dict]) -> dict[date, float]:
    """Sum cost_usd per calendar day (UTC)."""
    buckets: dict[date, float] = defaultdict(float)
    for event in events:
        day = as_utc_date(event["occurred_at"])
        buckets[day] += float(event["cost_usd"])
    return dict(sorted(buckets.items()))


def ewma_daily_burn(daily_spend: dict[date, float], alpha: float = 0.3) -> float | None:
    """
    Exponentially weighted moving average of daily spend.
    Needs at least one day of data. Alpha closer to 1 = react faster to recent days.
    """
    if not daily_spend:
        return None
    if not 0 < alpha <= 1:
        raise ValueError("alpha should be between 0 and 1")

    days = sorted(daily_spend)
    estimate = float(daily_spend[days[0]])
    for day in days[1:]:
        estimate = alpha * float(daily_spend[day]) + (1 - alpha) * estimate
    return estimate


def total_spend(events: Iterable[dict]) -> float:
    return round(sum(float(e["cost_usd"]) for e in events), 8)
