from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.flight_plan import TASK_PRIORS, estimate_flight_fuel
from runway_core.preflight import abandon_takeoff_decision, preflight_checklist
from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["flights"])


class FlightPlanBody(BaseModel):
    budget_id: str
    name: str = Field(default="Untitled flight", examples=["Weekend agent build"])
    model: str = Field(..., examples=["gpt-4o-mini"])
    task_type: str = Field(..., examples=["agent"])
    estimated_turns: int = Field(..., gt=0, le=500, examples=[12])
    agent_depth: int = Field(default=1, ge=1, le=20, examples=[3])
    project_id: str | None = None


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.get("/flights/task-types")
def list_task_types():
    return {"task_types": TASK_PRIORS}


@router.post("/flights/plan")
def plan_flight(body: FlightPlanBody):
    settings = get_settings()
    store = FuelStore(settings)
    budget = store.get_budget(body.budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    try:
        estimate = estimate_flight_fuel(
            model=body.model,
            task_type=body.task_type,
            estimated_turns=body.estimated_turns,
            agent_depth=body.agent_depth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    events = store.list_usage(body.budget_id, limit=1000)
    runway = compute_runway(
        limit_usd=float(budget["limit_usd"]),
        events=events,
        ewma_alpha=settings.runway_ewma_alpha,
        bingo_reserve_pct=settings.runway_bingo_reserve_pct,
    )

    checklist = preflight_checklist(
        budget=budget,
        model=body.model,
        estimate=estimate,
        bingo_reserve_pct=settings.runway_bingo_reserve_pct,
    )
    decision = abandon_takeoff_decision(
        remaining_usd=float(runway["remaining_usd"]),
        bingo_reserve_usd=float(runway["bingo_reserve_usd"]),
        estimate=estimate,
    )

    if not checklist["passed"]:
        decision = {
            **decision,
            "decision": "ABANDON",
            "reason": "Pre-flight checklist failed — fix the red items before takeoff.",
            "suggestions": [c["detail"] for c in checklist["checks"] if not c["ok"]]
            + decision.get("suggestions", []),
        }

    flight_id = str(uuid.uuid4())
    plan = {
        "flight_id": flight_id,
        "budget_id": body.budget_id,
        "name": body.name,
        "model": body.model,
        "task_type": body.task_type,
        "estimated_turns": body.estimated_turns,
        "agent_depth": body.agent_depth,
        "project_id": body.project_id,
        "status": decision["decision"],
        "estimate": estimate,
        "preflight": checklist,
        "takeoff": decision,
        "runway_snapshot": {
            "remaining_usd": runway["remaining_usd"],
            "usable_usd": runway["usable_usd"],
            "days_remaining": runway["days_remaining"],
            "status": runway["status"],
        },
    }
    store.save_flight_plan(plan)
    return plan


@router.get("/flights/{flight_id}")
def get_flight(flight_id: str):
    flight = _store().get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    return flight


@router.get("/budgets/{budget_id}/flights")
def list_budget_flights(budget_id: str):
    store = _store()
    if not store.get_budget(budget_id):
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"budget_id": budget_id, "flights": store.list_flights(budget_id=budget_id)}
