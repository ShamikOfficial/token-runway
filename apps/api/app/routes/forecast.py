from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from runway_core.forecast import forecast_horizon
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["forecast"])


@router.get("/budgets/{budget_id}/forecast")
def get_forecast(
    budget_id: str,
    days: int = Query(default=30, ge=1, le=90),
    flight_id: str | None = None,
):
    settings = get_settings()
    store = FuelStore(settings)
    budget = store.get_budget(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    planned_usd = 0.0
    planned_tokens = 0
    flight = None
    if flight_id:
        flight = store.get_flight(flight_id)
        if not flight or flight.get("budget_id") != budget_id:
            raise HTTPException(status_code=404, detail="Flight not found for this budget")
        planned_usd = float(flight["estimate"]["p50"]["cost_usd"])
        planned_tokens = int(flight["estimate"]["p50"]["tokens"])

    events = store.list_usage(budget_id, limit=1000)
    forecast = forecast_horizon(
        events=events,
        days=days,
        ewma_alpha=settings.runway_ewma_alpha,
        planned_extra_usd=planned_usd,
        planned_extra_tokens=planned_tokens,
    )

    limit = float(budget["limit_usd"])
    remaining = max(limit - float(forecast["spent_to_date_usd"]), 0.0)
    overspend_p50 = max(float(forecast["p50_spend_usd"]) - remaining, 0.0)
    overspend_p90 = max(float(forecast["p90_spend_usd"]) - remaining, 0.0)

    return {
        "budget": budget,
        "flight_id": flight_id,
        "forecast": forecast,
        "budget_check": {
            "limit_usd": limit,
            "remaining_before_forecast_usd": round(remaining, 6),
            "overspend_p50_usd": round(overspend_p50, 6),
            "overspend_p90_usd": round(overspend_p90, 6),
            "fits_p50": overspend_p50 <= 0,
            "fits_p90": overspend_p90 <= 0,
        },
    }
