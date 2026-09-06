from __future__ import annotations

from fastapi import APIRouter, HTTPException

from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore
from runway_core.tower import evaluate_tower_alerts

router = APIRouter(tags=["tower"])


@router.post("/budgets/{budget_id}/tower/scan")
def scan_tower(budget_id: str, publish: bool = True):
    """Check runway and optionally publish SNS alerts (Floci / AWS)."""
    settings = get_settings()
    store = FuelStore(settings)
    budget = store.get_budget(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    events = store.list_usage(budget_id, limit=1000)
    runway = compute_runway(
        limit_usd=float(budget["limit_usd"]),
        events=events,
        ewma_alpha=settings.runway_ewma_alpha,
        bingo_reserve_pct=settings.runway_bingo_reserve_pct,
    )
    alerts = evaluate_tower_alerts(runway)

    publishes = []
    if publish:
        for alert in alerts:
            result = store.publish_tower_alert(alert, budget_id)
            publishes.append({"alert": alert, "sns": result})

    return {
        "budget_id": budget_id,
        "runway": runway,
        "alerts": alerts,
        "publishes": publishes if publish else [],
        "all_clear": len(alerts) == 0,
    }
