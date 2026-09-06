from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.flight_ops import can_accept_usage, should_emergency_land
from runway_core.pricing import price_usage
from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["usage"])


class UsageBody(BaseModel):
    budget_id: str
    model: str = Field(..., examples=["gpt-4o-mini"])
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    project_id: str | None = None
    flight_id: str | None = None
    occurred_at: str | None = Field(
        default=None,
        description="ISO timestamp. Defaults to now (UTC).",
        examples=["2026-09-01T12:00:00+00:00"],
    )
    metadata: dict | None = None
    auto_emergency_land: bool = Field(
        default=True,
        description="If bound to a flight and usable fuel is gone, trigger Emergency Landing.",
    )


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.post("/usage")
def ingest_usage(body: UsageBody):
    if body.occurred_at:
        try:
            datetime.fromisoformat(body.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Bad occurred_at: {exc}") from exc

    store = _store()
    settings = get_settings()
    flight = None
    if body.flight_id:
        flight = store.get_flight(body.flight_id)
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
        if flight.get("budget_id") != body.budget_id:
            raise HTTPException(status_code=400, detail="flight_id does not belong to budget_id")
        ok, reason = can_accept_usage(flight)
        if not ok:
            raise HTTPException(status_code=409, detail=reason)

    try:
        priced = price_usage(
            model=body.model,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Soft gate: refuse the call if it would pierce bingo while in-flight
    if flight and flight.get("status") == "IN_FLIGHT":
        budget = store.get_budget(body.budget_id)
        events = store.list_usage(body.budget_id, limit=1000)
        runway = compute_runway(
            limit_usd=float(budget["limit_usd"]),
            events=events,
            ewma_alpha=settings.runway_ewma_alpha,
            bingo_reserve_pct=settings.runway_bingo_reserve_pct,
        )
        if should_emergency_land(
            remaining_usd=float(runway["remaining_usd"]),
            bingo_reserve_usd=float(runway["bingo_reserve_usd"]),
            next_call_cost_usd=float(priced["cost_usd"]),
        ):
            if body.auto_emergency_land:
                from app.routes.flight_ops import emergency_landing

                landing = emergency_landing(body.flight_id, None)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Emergency Landing triggered — call not charged.",
                        "landing": {
                            "flight_id": body.flight_id,
                            "checkpoint_key": landing.get("checkpoint_key"),
                            "status": landing["flight"]["status"],
                        },
                    },
                )
            raise HTTPException(status_code=409, detail="Would burn past bingo — land or top up.")

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
            flight_id=body.flight_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"event": event, "priced": priced}
