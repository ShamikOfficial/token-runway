"""
Weather — Tailwind (save) vs Headwind (spend for safety).

Make the cost ↔ safety tradeoff visible before takeoff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from runway_core.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _playbook_dir() -> Path:
    settings = get_settings()
    # Prefer samples next to overrides path
    overrides = settings.pricing_overrides_path
    candidate = overrides.parent / "playbooks"
    if candidate.exists():
        return candidate
    return _REPO_ROOT / "samples" / "playbooks"


def load_tailwind() -> list[dict[str, Any]]:
    path = _playbook_dir() / "tailwind.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("rules") or [])


def load_headwind() -> list[dict[str, Any]]:
    path = _playbook_dir() / "headwind.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(data.get("profiles") or [])


def applicable_tailwind(task_type: str, rule_ids: list[str] | None = None) -> list[dict[str, Any]]:
    rules = load_tailwind()
    picked = []
    for rule in rules:
        # None → all rules; [] → none; list → only those ids
        if rule_ids is not None and rule["id"] not in rule_ids:
            continue
        applies = rule.get("applies_to")
        if applies and task_type not in applies:
            continue
        picked.append(rule)
    return picked


def applicable_headwind(risk_tags: list[str]) -> list[dict[str, Any]]:
    tags = set(risk_tags or [])
    return [p for p in load_headwind() if tags.intersection(set(p.get("risk_tags") or []))]


def combined_save_pct(rules: list[dict[str, Any]]) -> float:
    """Diminishing returns: 1 - Π(1 - save_i). Cap at 80%."""
    remain = 1.0
    for rule in rules:
        remain *= 1.0 - min(float(rule.get("estimated_save_pct", 0)) / 100.0, 0.9)
    return round(min(0.80, 1.0 - remain) * 100.0, 2)


def combined_surcharge_pct(profiles: list[dict[str, Any]]) -> float:
    remain = 1.0
    for profile in profiles:
        remain *= 1.0 - min(float(profile.get("surcharge_pct", 0)) / 100.0, 0.9)
    return round(min(1.50, 1.0 - remain) * 100.0, 2)  # allow >100% stack display via formula cap


def apply_weather_to_estimate(
    estimate: dict[str, Any],
    *,
    task_type: str,
    tailwind_ids: list[str] | None = None,
    risk_tags: list[str] | None = None,
) -> dict[str, Any]:
    tw = applicable_tailwind(task_type, tailwind_ids)
    hw = applicable_headwind(risk_tags or [])
    save_pct = combined_save_pct(tw) if tw else 0.0
    surcharge_pct = combined_surcharge_pct(hw) if hw else 0.0

    # Net multiplier: save then surcharge on the saved amount
    mult = (1.0 - save_pct / 100.0) * (1.0 + surcharge_pct / 100.0)

    def _adjust(leg: dict[str, Any]) -> dict[str, Any]:
        return {
            **leg,
            "cost_usd_original": leg["cost_usd"],
            "cost_usd": round(float(leg["cost_usd"]) * mult, 8),
            "tokens_original": leg["tokens"],
            "tokens": int(round(leg["tokens"] * mult)),
        }

    adjusted = {
        **estimate,
        "p50": _adjust(estimate["p50"]),
        "p90": _adjust(estimate["p90"]),
        "weather": {
            "tailwind_rules": tw,
            "headwind_profiles": hw,
            "save_pct": save_pct,
            "surcharge_pct": surcharge_pct,
            "net_multiplier": round(mult, 4),
            "crosswind": bool(tw and hw),
            "crosswind_note": (
                f"Tailwind saves ~{save_pct}% but Headwind adds ~{surcharge_pct}% for safety."
                if tw and hw
                else None
            ),
        },
    }
    return adjusted


def diversion_suggestion(estimate: dict[str, Any], cheaper_model: str = "gpt-4o-mini") -> dict[str, Any]:
    from runway_core.flight_plan import estimate_flight_fuel

    alt = estimate_flight_fuel(
        model=cheaper_model,
        task_type=estimate["task_type"],
        estimated_turns=estimate["estimated_turns"],
        agent_depth=estimate["agent_depth"],
    )
    return {
        "action": "DIVERSION",
        "to_model": cheaper_model,
        "from_model": estimate["model"],
        "p90_before_usd": estimate["p90"]["cost_usd"],
        "p90_after_usd": alt["p90"]["cost_usd"],
        "save_usd": round(float(estimate["p90"]["cost_usd"]) - float(alt["p90"]["cost_usd"]), 6),
        "alternate_estimate": alt,
    }


def jettison_suggestion(estimate: dict[str, Any], trim_pct: float = 20.0) -> dict[str, Any]:
    mult = 1.0 - trim_pct / 100.0
    return {
        "action": "JETTISON",
        "trim_pct": trim_pct,
        "message": "Drop non-essential context / history to cut fuel.",
        "p90_before_usd": estimate["p90"]["cost_usd"],
        "p90_after_usd": round(float(estimate["p90"]["cost_usd"]) * mult, 6),
    }
