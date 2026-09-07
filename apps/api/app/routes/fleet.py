from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.fleet import build_notam, evaluate_ground_stop, now_iso
from runway_core.burn import total_spend
from runway_core.fleet import weight_and_balance
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["fleet"])


class GroundStopBody(BaseModel):
    active: bool
    reason: str | None = "Manual ground stop"


class NotamBody(BaseModel):
    code: str = Field(..., examples=["PRICE_CHANGE"])
    message: str
    severity: str = "INFO"


def _store() -> FuelStore:
    return FuelStore(get_settings())


@router.get("/fleet/weight-balance")
def fleet_weight_balance():
    store = _store()
    budgets = store.list_budgets(limit=100)
    spends = {}
    for b in budgets:
        events = store.list_usage(b["budget_id"], limit=5000)
        spends[b["budget_id"]] = total_spend(events)
    return weight_and_balance(budgets=budgets, spends=spends)


@router.get("/fleet/ground-stop")
def get_ground_stop():
    return evaluate_ground_stop(_store().get_org_state())


@router.post("/fleet/ground-stop")
def set_ground_stop(body: GroundStopBody):
    store = _store()
    state = store.get_org_state()
    state["ground_stop"] = body.active
    state["ground_stop_reason"] = body.reason if body.active else None
    state["ground_stop_since"] = now_iso() if body.active else None
    saved = store.save_org_state(state)
    if budgets := store.list_budgets(limit=1):
        store.append_audit(
            budget_id=budgets[0]["budget_id"],
            action="GROUND_STOP_ON" if body.active else "GROUND_STOP_OFF",
            detail={"reason": body.reason},
        )
    return evaluate_ground_stop(saved)


@router.get("/fleet/notams")
def list_notams():
    return {"notams": list(_store().get_org_state().get("notams") or [])}


@router.post("/fleet/notams")
def add_notam(body: NotamBody):
    store = _store()
    state = store.get_org_state()
    note = build_notam(code=body.code, message=body.message, severity=body.severity)
    notams = list(state.get("notams") or [])
    notams.insert(0, note)
    state["notams"] = notams[:50]
    store.save_org_state(state)
    return note


def assert_takeoffs_allowed() -> None:
    state = evaluate_ground_stop(_store().get_org_state())
    if state["ground_stop"]:
        raise HTTPException(status_code=423, detail=state["message"])
