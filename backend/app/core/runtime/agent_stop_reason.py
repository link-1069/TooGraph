from __future__ import annotations

from typing import Any


STANDARD_AGENT_STOP_REASONS = {
    "completed",
    "needs_user_clarification",
    "max_iterations_reached",
    "capability_budget_exhausted",
    "permission_required",
    "provider_failed",
    "tool_failed",
    "graph_validation_failed",
    "context_budget_exhausted",
}

_CYCLE_STOP_REASON_MAP = {
    "completed": "completed",
    "max_iterations_exceeded": "max_iterations_reached",
    "no_state_change": "max_iterations_reached",
}


def resolve_agent_stop_reason(run_state: dict[str, Any]) -> str:
    state_values = _record(run_state.get("state_values"))
    explicit = _normalize_stop_reason(state_values.get("agent_loop_stop_reason"))
    if explicit:
        return explicit

    metadata = _record(run_state.get("metadata"))
    if _record(metadata.get("pending_permission_approval")):
        return "permission_required"
    pending_subgraph = _record(metadata.get("pending_subgraph_breakpoint"))
    pending_subgraph_metadata = _record(pending_subgraph.get("metadata"))
    if _record(pending_subgraph_metadata.get("pending_permission_approval")):
        return "permission_required"

    cycle_summary = _record(run_state.get("cycle_summary"))
    cycle_reason = _CYCLE_STOP_REASON_MAP.get(_text(cycle_summary.get("stop_reason")))
    if cycle_reason:
        return cycle_reason

    status = _text(run_state.get("status"))
    errors = " ".join(_text(error) for error in run_state.get("errors", []) if _text(error)).lower()
    if status == "failed":
        if any(token in errors for token in ("provider", "model", "openai", "rate limit", "timeout")):
            return "provider_failed"
        if any(token in errors for token in ("validation", "missing node", "graph")):
            return "graph_validation_failed"
        return "tool_failed"
    if status == "awaiting_human":
        return "permission_required"
    if status == "completed":
        return "completed"
    return ""


def set_agent_stop_reason(run_state: dict[str, Any]) -> None:
    stop_reason = resolve_agent_stop_reason(run_state)
    if stop_reason:
        run_state["stop_reason"] = stop_reason


def _normalize_stop_reason(value: Any) -> str:
    text = _text(value)
    return text if text in STANDARD_AGENT_STOP_REASONS else ""


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
