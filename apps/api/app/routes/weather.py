from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.routes.fleet import assert_takeoffs_allowed
from runway_core.flight_plan import estimate_flight_fuel
from runway_core.preflight import abandon_takeoff_decision
from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore
from runway_core.weather import (
    apply_weather_to_estimate,
    diversion_suggestion,
    jettison_suggestion,
    load_headwind,
    load_tailwind,
)

router = APIRouter(tags=["weather"])


class WeatherPlanBody(BaseModel):
    budget_id: str
    name: str = "Weathered flight"
    model: str
    task_type: str
    estimated_turns: int = Field(..., gt=0, le=500)
    agent_depth: int = Field(default=1, ge=1, le=20)
    tailwind_ids: list[str] | None = None
    risk_tags: list[str] | None = None
    suggest_diversion: bool = True


@router.get("/weather/playbooks")
def playbooks():
    return {"tailwind": load_tailwind(), "headwind": load_headwind()}


@router.post("/weather/plan")
def weather_plan(body: WeatherPlanBody):
    assert_takeoffs_allowed()
    settings = get_settings()
    store = FuelStore(settings)
    budget = store.get_budget(body.budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    try:
        base = estimate_flight_fuel(
            model=body.model,
            task_type=body.task_type,
            estimated_turns=body.estimated_turns,
            agent_depth=body.agent_depth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    weathered = apply_weather_to_estimate(
        base,
        task_type=body.task_type,
        tailwind_ids=body.tailwind_ids,
        risk_tags=body.risk_tags,
    )

    events = store.list_usage(body.budget_id, limit=1000)
    runway = compute_runway(
        limit_usd=float(budget["limit_usd"]),
        events=events,
        ewma_alpha=settings.runway_ewma_alpha,
        bingo_reserve_pct=settings.runway_bingo_reserve_pct,
    )
    takeoff = abandon_takeoff_decision(
        remaining_usd=float(runway["remaining_usd"]),
        bingo_reserve_usd=float(runway["bingo_reserve_usd"]),
        estimate=weathered,
    )

    extras: dict = {"jettison": jettison_suggestion(weathered)}
    if body.suggest_diversion and body.model != "gpt-4o-mini":
        extras["diversion"] = diversion_suggestion(base)

    flight_id = str(uuid.uuid4())
    plan = {
        "flight_id": flight_id,
        "budget_id": body.budget_id,
        "name": body.name,
        "model": body.model,
        "task_type": body.task_type,
        "estimated_turns": body.estimated_turns,
        "agent_depth": body.agent_depth,
        "risk_tags": body.risk_tags or [],
        "tailwind_ids": body.tailwind_ids,
        "status": takeoff["decision"],
        "estimate": weathered,
        "takeoff": takeoff,
        "weather": weathered.get("weather"),
        "suggestions": extras,
    }
    store.save_flight_plan(plan)
    store.append_audit(
        budget_id=body.budget_id,
        flight_id=flight_id,
        action="WEATHER_PLAN",
        detail={
            "decision": takeoff["decision"],
            "save_pct": weathered["weather"]["save_pct"],
            "surcharge_pct": weathered["weather"]["surcharge_pct"],
        },
    )
    return plan
