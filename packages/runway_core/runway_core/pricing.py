"""
Price a token pair.

Public models → LiteLLM's maintained price map.
Your licenses → samples/pricing_overrides.json (wins when the model key matches).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from runway_core.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Friendly names people type in demos → LiteLLM-known keys
_MODEL_ALIASES = {
    "claude-3-5-sonnet-20241022": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022",
    "claude-sonnet-4": "anthropic/claude-sonnet-4-20250514",
}


def resolve_model_name(model: str) -> str:
    return _MODEL_ALIASES.get(model, model)


def _load_overrides(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        logger.warning("No pricing overrides at %s — using LiteLLM only", path)
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models") or {}
    cleaned: dict[str, dict[str, float]] = {}
    for name, row in models.items():
        if name.startswith("_"):
            continue
        cleaned[name] = {
            "input_cost_per_million": float(row["input_cost_per_million"]),
            "output_cost_per_million": float(row["output_cost_per_million"]),
        }
    return cleaned


def cost_from_override(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    overrides: dict[str, dict[str, float]],
) -> float | None:
    row = overrides.get(model)
    if not row:
        return None
    input_cost = (prompt_tokens / 1_000_000) * row["input_cost_per_million"]
    output_cost = (completion_tokens / 1_000_000) * row["output_cost_per_million"]
    return input_cost + output_cost


def cost_from_litellm(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Delegate to LiteLLM — we do not maintain a parallel price DB."""
    from litellm import cost_per_token

    prompt_cost, completion_cost = cost_per_token(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return float(prompt_cost) + float(completion_cost)


def _litellm_candidates(model: str) -> list[str]:
    """Try the name as-given, then aliases / common provider prefixes."""
    resolved = resolve_model_name(model)
    candidates = [model, resolved]
    if not model.startswith(("anthropic/", "openai/", "bedrock/", "openrouter/")):
        candidates.extend(
            [
                f"anthropic/{model}",
                f"openai/{model}",
                f"bedrock/{model}",
            ]
        )
    # de-dupe, keep order
    seen: set[str] = set()
    ordered: list[str] = []
    for name in candidates:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def price_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    settings: Settings | None = None,
    overrides: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """
    Return cost_usd plus where the price came from.
    Override file always wins for matching model names.
    """
    settings = settings or get_settings()
    if overrides is None:
        overrides = _load_overrides(settings.pricing_overrides_path)

    for key in (model, resolve_model_name(model)):
        override_cost = cost_from_override(key, prompt_tokens, completion_tokens, overrides)
        if override_cost is not None:
            return {
                "cost_usd": round(override_cost, 8),
                "price_source": "override",
                "model": model,
                "priced_as": key,
            }

    last_error: Exception | None = None
    for candidate in _litellm_candidates(model):
        try:
            litellm_cost = cost_from_litellm(candidate, prompt_tokens, completion_tokens)
            return {
                "cost_usd": round(litellm_cost, 8),
                "price_source": "litellm",
                "model": model,
                "priced_as": candidate,
            }
        except Exception as exc:  # LiteLLM raises on unknown models
            last_error = exc
            continue

    raise ValueError(
        f"Don't know how to price model '{model}'. "
        f"Add it to samples/pricing_overrides.json or use a LiteLLM-known name. ({last_error})"
    ) from last_error