"""Flight lifecycle — start, hold, emergency land, resume, black box."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.flight_ops import (
    build_checkpoint,
    detect_turbulence,
    now_iso,
    should_emergency_land,
)
from runway_core.runway import compute_runway
from runway_core.settings import get_settings
from runway_core.store import FuelStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["flight-ops"])


class ProgressBody(BaseModel):
    note: str | None = None
    step: str | None = None
    artifacts: dict | None = None


class ResumeBody(BaseModel):
    note: str | None = Field(default="Resuming after refuel")


def _store() -> FuelStore:
    return FuelStore(get_settings())


def _runway_for(store: FuelStore, budget_id: str) -> dict:
    settings = get_settings()
    budget = store.get_budget(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    events = store.list_usage(budget_id, limit=5000)
    return compute_runway(
        limit_usd=float(budget["limit_usd"]),
        events=events,
        ewma_alpha=settings.runway_ewma_alpha,
        bingo_reserve_pct=settings.runway_bingo_reserve_pct,
    )


@router.post("/flights/{flight_id}/start")
def start_flight(flight_id: str):
    store = _store()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    status = flight.get("status")
    if status == "IN_FLIGHT":
        return flight
    if status == "LANDED_EMERGENCY":
        raise HTTPException(status_code=400, detail="Use /resume after Emergency Landing.")
    if status == "ABANDON":
        raise HTTPException(status_code=400, detail="Cannot start an abandoned flight — replan first.")
    if status not in {"CLEAR", "REPLAN", "HOLDING"}:
        raise HTTPException(status_code=400, detail=f"Cannot start from status {status}")

    flight["status"] = "IN_FLIGHT"
    flight["started_at"] = now_iso()
    flight["progress"] = flight.get("progress") or {"steps": []}
    store.save_flight_plan(flight)
    store.append_audit(
        budget_id=flight["budget_id"],
        flight_id=flight_id,
        action="FLIGHT_STARTED",
        detail={"name": flight.get("name")},
    )
    return flight


@router.post("/flights/{flight_id}/hold")
def hold_flight(flight_id: str, body: ProgressBody | None = None):
    store = _store()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    if flight.get("status") not in {"IN_FLIGHT", "HOLDING"}:
        raise HTTPException(status_code=400, detail=f"Cannot hold from status {flight.get('status')}")

    runway = _runway_for(store, flight["budget_id"])
    progress = dict(flight.get("progress") or {})
    if body:
        if body.note:
            progress["last_note"] = body.note
        if body.step:
            progress.setdefault("steps", []).append({"step": body.step, "at": now_iso()})
        if body.artifacts:
            progress["artifacts"] = {**(progress.get("artifacts") or {}), **body.artifacts}

    checkpoint = build_checkpoint(
        flight={**flight, "progress": progress},
        runway=runway,
        reason="HOLDING_PATTERN",
        progress=progress,
    )
    key = store.write_checkpoint(checkpoint)
    flight["status"] = "HOLDING"
    flight["progress"] = progress
    flight["checkpoint_key"] = key
    flight["held_at"] = now_iso()
    store.save_flight_plan(flight)
    store.append_audit(
        budget_id=flight["budget_id"],
        flight_id=flight_id,
        action="HOLDING_PATTERN",
        detail={"checkpoint_key": key, "note": body.note if body else None},
    )
    return {"flight": flight, "checkpoint_key": key, "checkpoint": checkpoint}


@router.post("/flights/{flight_id}/emergency-landing")
def emergency_landing(flight_id: str, body: ProgressBody | None = None):
    store = _store()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    if flight.get("status") in {"LANDED_EMERGENCY", "ABANDON", "COMPLETED"}:
        raise HTTPException(status_code=400, detail=f"Already finished: {flight.get('status')}")
    if flight.get("status") not in {"IN_FLIGHT", "HOLDING"}:
        raise HTTPException(
            status_code=400,
            detail="Emergency landing only from IN_FLIGHT or HOLDING — start the flight first.",
        )

    runway = _runway_for(store, flight["budget_id"])
    progress = dict(flight.get("progress") or {})
    if body:
        if body.note:
            progress["last_note"] = body.note
        if body.step:
            progress.setdefault("steps", []).append({"step": body.step, "at": now_iso()})
        if body.artifacts:
            progress["artifacts"] = {**(progress.get("artifacts") or {}), **body.artifacts}

    reason = "EMERGENCY_LANDING"
    if should_emergency_land(
        remaining_usd=float(runway["remaining_usd"]),
        bingo_reserve_usd=float(runway["bingo_reserve_usd"]),
    ):
        reason = "EMERGENCY_LANDING_BINGO"

    checkpoint = build_checkpoint(
        flight={**flight, "progress": progress, "status": "LANDED_EMERGENCY"},
        runway=runway,
        reason=reason,
        progress=progress,
    )
    key = store.write_checkpoint(checkpoint)
    flight["status"] = "LANDED_EMERGENCY"
    flight["progress"] = progress
    flight["checkpoint_key"] = key
    flight["landed_at"] = now_iso()
    flight["landing_reason"] = reason
    store.save_flight_plan(flight)

    alert = {
        "squawk": "7700",
        "severity": "CRITICAL",
        "code": "EMERGENCY_LANDING",
        "message": f"Emergency landing for flight {flight_id}. Progress saved to S3.",
    }
    sns = store.publish_tower_alert(alert, flight["budget_id"])
    store.append_audit(
        budget_id=flight["budget_id"],
        flight_id=flight_id,
        action="EMERGENCY_LANDING",
        detail={"checkpoint_key": key, "reason": reason, "sns": sns},
    )
    return {
        "flight": flight,
        "checkpoint_key": key,
        "checkpoint": checkpoint,
        "alert": alert,
        "sns": sns,
    }


@router.post("/flights/{flight_id}/resume")
def resume_flight(flight_id: str, body: ResumeBody | None = None):
    store = _store()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    if flight.get("status") not in {"HOLDING", "LANDED_EMERGENCY"}:
        raise HTTPException(
            status_code=400,
            detail=f"Resume only from HOLDING or LANDED_EMERGENCY (now {flight.get('status')})",
        )

    runway = _runway_for(store, flight["budget_id"])
    if float(runway["usable_usd"]) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Still at bingo/empty — top up the budget before resume.",
        )

    prev = flight.get("status")
    flight["status"] = "IN_FLIGHT"
    flight["resumed_at"] = now_iso()
    store.save_flight_plan(flight)
    store.append_audit(
        budget_id=flight["budget_id"],
        flight_id=flight_id,
        action="FLIGHT_RESUMED",
        detail={"from": prev, "note": body.note if body else None, "checkpoint_key": flight.get("checkpoint_key")},
    )
    checkpoint = None
    if flight.get("checkpoint_key"):
        try:
            checkpoint = store.read_checkpoint(flight["checkpoint_key"])
        except Exception as exc:
            logger.warning("Could not read checkpoint %s: %s", flight["checkpoint_key"], exc)
            checkpoint = None
    return {"flight": flight, "checkpoint": checkpoint, "runway": runway}


@router.get("/flights/{flight_id}/checkpoint")
def get_checkpoint(flight_id: str):
    store = _store()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    key = flight.get("checkpoint_key")
    if not key:
        raise HTTPException(status_code=404, detail="No checkpoint saved yet")
    return {"checkpoint_key": key, "checkpoint": store.read_checkpoint(key)}


@router.get("/budgets/{budget_id}/blackbox")
def blackbox(budget_id: str, limit: int = 50):
    store = _store()
    if not store.get_budget(budget_id):
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"budget_id": budget_id, "events": store.list_audit(budget_id, limit=limit)}


@router.post("/flights/{flight_id}/check-turbulence")
def check_turbulence(flight_id: str):
    store = _store()
    settings = get_settings()
    flight = store.get_flight(flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    runway = _runway_for(store, flight["budget_id"])
    events = store.list_usage(flight["budget_id"], limit=200)
    flight_events = [e for e in events if e.get("flight_id") == flight_id]
    recent = sum(float(e["cost_usd"]) for e in flight_events[-10:])
    # Treat last chunk as ~1 hour of burn for demo purposes
    alert = detect_turbulence(
        recent_hourly_burn=recent,
        baseline_daily_burn=runway.get("daily_burn_usd"),
    )
    if alert:
        store.append_audit(
            budget_id=flight["budget_id"],
            flight_id=flight_id,
            action="TURBULENCE",
            detail=alert,
        )
        store.publish_tower_alert(alert, flight["budget_id"])
    return {"flight_id": flight_id, "turbulence": alert, "recent_spend_usd": round(recent, 6)}
