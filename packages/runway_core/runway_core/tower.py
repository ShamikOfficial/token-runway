"""Tower alerts — squawk when runway gets short."""

from __future__ import annotations

from typing import Any


def evaluate_tower_alerts(runway: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Squawk codes (aviation-ish):
      7700 — mayday / critical fuel
      7600 — warning / getting tight
      7000 — advisory / healthy (usually silent)
    """
    days = runway.get("days_remaining")
    status = runway.get("status")
    alerts: list[dict[str, Any]] = []

    if status in {"BINGO_OR_EMPTY", "CRITICAL"} or (days is not None and days < 3):
        alerts.append(
            {
                "squawk": "7700",
                "severity": "CRITICAL",
                "code": "RUNWAY_CRITICAL",
                "message": runway.get("note")
                or "Less than ~3 days of usable fuel — top up or Emergency Landing soon.",
            }
        )
    elif status == "WARNING" or (days is not None and days < 7):
        alerts.append(
            {
                "squawk": "7600",
                "severity": "WARNING",
                "code": "RUNWAY_WARNING",
                "message": runway.get("note")
                or "Under a week of usable fuel — plan a top-up or cut burn.",
            }
        )

    return alerts
