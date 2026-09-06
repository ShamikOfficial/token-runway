from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runway_core.burn import total_spend
from runway_core.fleet import build_notam, evaluate_ground_stop, now_iso, weight_and_balance
from runway_core.settings import get_settings
from runway_core.store import FuelStore

router = APIRouter(tags=["fleet"])

# In-memory org flags for Stage 5 demo (persisted enough for a running process)
_ORG: dict = {"ground_stop": False, "notams": []}


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
        events = store.list_usage(b["budget_id"], limit=1000)
        spends[b["budget_id"]] = total_spend(events)
    return weight_and_balance(budgets=budgets, spends=spends)


@router.get("/fleet/ground-stop")
def get_ground_stop():
    return evaluate_ground_stop(_ORG)


@router.post("/fleet/ground-stop")
def set_ground_stop(body: GroundStopBody):
    _ORG["ground_stop"] = body.active
    _ORG["ground_stop_reason"] = body.reason if body.active else None
    _ORG["ground_stop_since"] = now_iso() if body.active else None
    store = _store()
    # Audit against a synthetic org budget id channel
    if budgets := store.list_budgets(limit=1):
        store.append_audit(
            budget_id=budgets[0]["budget_id"],
            action="GROUND_STOP_ON" if body.active else "GROUND_STOP_OFF",
            detail={"reason": body.reason},
        )
    return evaluate_ground_stop(_ORG)


@router.get("/fleet/notams")
def list_notams():
    return {"notams": list(_ORG.get("notams") or [])}


@router.post("/fleet/notams")
def add_notam(body: NotamBody):
    note = build_notam(code=body.code, message=body.message, severity=body.severity)
    _ORG.setdefault("notams", []).insert(0, note)
    _ORG["notams"] = _ORG["notams"][:50]
    return note


def assert_takeoffs_allowed() -> None:
    state = evaluate_ground_stop(_ORG)
    if state["ground_stop"]:
        raise HTTPException(status_code=423, detail=state["message"])
