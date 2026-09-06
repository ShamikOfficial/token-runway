from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["budgets"])


class CreateBudgetBody(BaseModel):
    name: str = Field(..., examples=["Weekend hackathon fuel"])
    limit_usd: float = Field(..., gt=0, examples=[50.0])
    currency: str = "USD"
    window_days: int | None = 30
    budget_id: str | None = None


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.post("/budgets")
def create_budget(body: CreateBudgetBody):
    store = _store()
    budget = store.create_budget(
        name=body.name,
        limit_usd=body.limit_usd,
        currency=body.currency,
        window_days=body.window_days,
        budget_id=body.budget_id,
    )
    return budget


@router.get("/budgets")
def list_budgets():
    return {"budgets": _store().list_budgets()}


@router.get("/budgets/{budget_id}")
def get_budget(budget_id: str):
    budget = _store().get_budget(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/budgets/{budget_id}/runway")
def get_runway(budget_id: str):
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
    return {
        "budget": budget,
        "runway": runway,
    }
