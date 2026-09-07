from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

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


class PatchBudgetBody(BaseModel):
    """Refuel after Emergency Landing with add_limit_usd, or set an absolute limit."""

    name: str | None = None
    limit_usd: float | None = Field(default=None, gt=0)
    add_limit_usd: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def at_least_one_change(self):
        if self.name is None and self.limit_usd is None and self.add_limit_usd is None:
            raise ValueError("Provide name, limit_usd, and/or add_limit_usd")
        return self


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.post("/budgets")
def create_budget(body: CreateBudgetBody):
    store = _store()
    try:
        budget = store.create_budget(
            name=body.name,
            limit_usd=body.limit_usd,
            currency=body.currency,
            window_days=body.window_days,
            budget_id=body.budget_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return budget


@router.patch("/budgets/{budget_id}")
def patch_budget(budget_id: str, body: PatchBudgetBody):
    store = _store()
    try:
        budget = store.update_budget(
            budget_id,
            name=body.name,
            limit_usd=body.limit_usd,
            add_limit_usd=body.add_limit_usd,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Budget not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store.append_audit(
        budget_id=budget_id,
        action="BUDGET_TOP_UP" if body.add_limit_usd else "BUDGET_UPDATED",
        detail={
            "add_limit_usd": body.add_limit_usd,
            "limit_usd": body.limit_usd,
            "name": body.name,
            "new_limit_usd": budget["limit_usd"],
        },
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

    events = store.list_usage(budget_id, limit=5000)
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
