"""
Optional LiteLLM success_callback → TokenRunway /v1/usage.

Users keep their own keys; we only receive usage events.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx


def make_runway_callback(
    *,
    base_url: str = "http://localhost:8000",
    budget_id: str,
    project_id: str | None = "litellm",
    flight_id: str | None = None,
    timeout: float = 10.0,
) -> Callable[..., Any]:
    """
    Usage:

        import litellm
        from runway_adapters.litellm_callback import make_runway_callback
        litellm.success_callback = [
            make_runway_callback(budget_id="...", base_url="http://localhost:8000")
        ]
    """

    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def _callback(kwargs, completion_response, start_time, end_time):  # noqa: ANN001
        try:
            usage = getattr(completion_response, "usage", None) or {}
            if isinstance(usage, dict):
                prompt = int(usage.get("prompt_tokens") or 0)
                completion = int(usage.get("completion_tokens") or 0)
            else:
                prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion = int(getattr(usage, "completion_tokens", 0) or 0)

            model = kwargs.get("model") or getattr(completion_response, "model", None) or "unknown"
            resp = client.post(
                "/v1/usage",
                json={
                    "budget_id": budget_id,
                    "model": model,
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "project_id": project_id,
                    "flight_id": flight_id,
                    "metadata": {"source": "litellm_callback"},
                },
            )
            if resp.status_code >= 400:
                # Never break the user's LLM call — log via print for local demos
                print(f"[tokenrunway] usage ingest failed: {resp.status_code} {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[tokenrunway] usage callback error: {exc}")
            return

    return _callback
