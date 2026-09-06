from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.pricing import price_usage
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["usage"])


class UsageBody(BaseModel):
    budget_id: str
    model: str = Field(..., examples=["gpt-4o-mini"])
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    project_id: str | None = None
    occurred_at: str | None = Field(
        default=None,
        description="ISO timestamp. Defaults to now (UTC).",
        examples=["2026-09-01T12:00:00+00:00"],
    )
    metadata: dict | None = None


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.post("/usage")
def ingest_usage(body: UsageBody):
    if body.occurred_at:
        try:
            datetime.fromisoformat(body.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Bad occurred_at: {exc}") from exc

    try:
        priced = price_usage(
            model=body.model,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store = _store()
    try:
        event = store.record_usage(
            budget_id=body.budget_id,
            model=body.model,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
            cost_usd=priced["cost_usd"],
            price_source=priced["price_source"],
            project_id=body.project_id,
            occurred_at=body.occurred_at,
            metadata=body.metadata,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"event": event, "priced": priced}


@router.get("/budgets/{budget_id}/usage")
def list_usage(budget_id: str, limit: int = 100):
    store = _store()
    if not store.get_budget(budget_id):
        raise HTTPException(status_code=404, detail="Budget not found")
    events = store.list_usage(budget_id, limit=min(limit, 1000))
    return {"budget_id": budget_id, "count": len(events), "events": events}
