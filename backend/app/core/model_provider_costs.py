from __future__ import annotations

import math
from typing import Any


def normalize_provider_model_pricing(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    input_price = _positive_float(
        value.get("input_per_million_usd")
        or value.get("inputPerMillionUsd")
        or value.get("prompt_per_million_usd")
        or value.get("promptPerMillionUsd")
    )
    output_price = _positive_float(
        value.get("output_per_million_usd")
        or value.get("outputPerMillionUsd")
        or value.get("completion_per_million_usd")
        or value.get("completionPerMillionUsd")
    )
    pricing: dict[str, float] = {}
    if input_price is not None:
        pricing["input_per_million_usd"] = input_price
    if output_price is not None:
        pricing["output_per_million_usd"] = output_price
    return pricing


def provider_model_pricing(provider_config: dict[str, Any], model_name: str) -> dict[str, float]:
    models = provider_config.get("models")
    if not isinstance(models, list):
        return {}
    normalized_model_name = str(model_name or "").strip().lower()
    for item in models:
        if not isinstance(item, dict):
            continue
        if str(item.get("model") or "").strip().lower() != normalized_model_name:
            continue
        return normalize_provider_model_pricing(item.get("pricing"))
    return {}


def build_provider_cost_estimate(
    usage: Any,
    pricing: Any,
    cost_budget: Any,
) -> dict[str, Any]:
    normalized_usage = usage if isinstance(usage, dict) else {}
    normalized_pricing = normalize_provider_model_pricing(pricing)
    budget = cost_budget if isinstance(cost_budget, dict) else {}
    if not normalized_pricing and not budget:
        return {}
    input_tokens = _token_count(
        normalized_usage,
        ("input_tokens", "prompt_tokens", "inputTokens", "promptTokens", "promptTokenCount"),
    )
    output_tokens = _token_count(
        normalized_usage,
        ("output_tokens", "completion_tokens", "outputTokens", "completionTokens", "candidatesTokenCount"),
    )
    total_tokens = _token_count(
        normalized_usage,
        ("total_tokens", "totalTokens", "total_token_count", "totalTokenCount"),
    )
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = int(input_tokens or 0) + int(output_tokens or 0)

    result: dict[str, Any] = {
        "kind": "provider_cost_estimate",
        "version": 1,
        "currency": "USD",
    }
    if input_tokens is not None:
        result["input_tokens"] = input_tokens
    if output_tokens is not None:
        result["output_tokens"] = output_tokens
    if total_tokens is not None:
        result["total_tokens"] = total_tokens

    limit_usd = _non_negative_float(budget.get("limit_usd") or budget.get("limitUsd"))
    budget_window = str(budget.get("window") or "run").strip() or "run"
    if limit_usd is not None:
        result["budget_limit_usd"] = limit_usd
        result["budget_window"] = budget_window

    if input_tokens is None and output_tokens is None and total_tokens is None:
        result["status"] = "usage_unavailable"
        result["budget_status"] = "not_estimated"
        return result
    if not normalized_pricing:
        result["status"] = "pricing_unavailable"
        result["budget_status"] = "not_estimated"
        return result

    input_cost = _round_usd((input_tokens or 0) * normalized_pricing.get("input_per_million_usd", 0.0) / 1_000_000)
    output_cost = _round_usd((output_tokens or 0) * normalized_pricing.get("output_per_million_usd", 0.0) / 1_000_000)
    estimated_cost = _round_usd(input_cost + output_cost)
    result.update(
        {
            "status": "estimated",
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
            "estimated_cost_usd": estimated_cost,
            "pricing": normalized_pricing,
            "budget_status": "not_configured",
        }
    )
    if limit_usd is not None:
        result["budget_status"] = "over_budget" if estimated_cost > limit_usd else "within_budget"
    return result


def _token_count(usage: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _non_negative_float(usage.get(key))
        if value is not None:
            return int(value)
    return None


def _positive_float(value: Any) -> float | None:
    number = _non_negative_float(value)
    if number is None or number <= 0:
        return None
    return number


def _non_negative_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _round_usd(value: float) -> float:
    return round(float(value), 12)
