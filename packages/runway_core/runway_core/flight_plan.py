"""
Flight plan fuel estimates — task priors + growth curves.

Agent / RAG work often grows each turn (context piles up). We model that
as tokens_t ≈ base * growth^(turn) so p90 isn't wildly optimistic.
"""

from __future__ import annotations

from typing import Any, Literal

TaskType = Literal["chat", "batch", "rag", "agent", "codegen"]

# Rough priors: tokens per turn at p50/p90, and per-turn growth factor.
TASK_PRIORS: dict[str, dict[str, float]] = {
    "chat": {"tokens_per_turn_p50": 1_500, "tokens_per_turn_p90": 3_000, "growth": 1.00},
    "batch": {"tokens_per_turn_p50": 4_000, "tokens_per_turn_p90": 8_000, "growth": 1.00},
    "rag": {"tokens_per_turn_p50": 5_000, "tokens_per_turn_p90": 12_000, "growth": 1.05},
    "agent": {"tokens_per_turn_p50": 8_000, "tokens_per_turn_p90": 20_000, "growth": 1.15},
    "codegen": {"tokens_per_turn_p50": 6_000, "tokens_per_turn_p90": 15_000, "growth": 1.08},
}

# How we split a turn into prompt vs completion for pricing
PROMPT_SHARE = 0.70


def growing_token_total(base_per_turn: float, turns: int, growth: float, agent_depth: int = 1) -> float:
    """Sum base * growth^i across turns, then multiply by agent depth (tool loops)."""
    turns = max(int(turns), 1)
    depth = max(int(agent_depth), 1)
    growth = max(float(growth), 1.0)
    total = 0.0
    for i in range(turns):
        total += base_per_turn * (growth**i)
    return total * depth


def estimate_flight_fuel(
    *,
    model: str,
    task_type: TaskType | str,
    estimated_turns: int,
    agent_depth: int = 1,
) -> dict[str, Any]:
    """Return p50/p90 tokens + $ for a planned flight."""
    from runway_core.pricing import price_usage

    prior = TASK_PRIORS.get(task_type)
    if not prior:
        raise ValueError(
            f"Unknown task_type '{task_type}'. Use one of: {', '.join(sorted(TASK_PRIORS))}."
        )

    tokens_p50 = growing_token_total(
        prior["tokens_per_turn_p50"], estimated_turns, prior["growth"], agent_depth
    )
    tokens_p90 = growing_token_total(
        prior["tokens_per_turn_p90"], estimated_turns, prior["growth"], agent_depth
    )

    def _cost_for_tokens(total_tokens: float) -> dict[str, Any]:
        prompt = int(total_tokens * PROMPT_SHARE)
        completion = max(int(total_tokens - prompt), 0)
        priced = price_usage(model, prompt, completion)
        return {
            "tokens": int(round(total_tokens)),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cost_usd": priced["cost_usd"],
            "price_source": priced["price_source"],
            "priced_as": priced.get("priced_as", model),
        }

    p50 = _cost_for_tokens(tokens_p50)
    p90 = _cost_for_tokens(tokens_p90)

    return {
        "task_type": task_type,
        "model": model,
        "estimated_turns": int(estimated_turns),
        "agent_depth": int(agent_depth),
        "growth_factor": prior["growth"],
        "p50": p50,
        "p90": p90,
    }
