from __future__ import annotations

import json
import sys
from typing import Any


DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_CAPABILITY_CALLS = 4
DEFAULT_RETRY_BUDGET = 1

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


def agent_loop_guard(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    selected_capability = _record(inputs.get("selected_capability"))
    capability_result = _record(inputs.get("capability_result"))
    context_budget_report = _record(inputs.get("context_budget_report"))
    control = _normalize_control(_record(inputs.get("agent_loop_control")))

    control["iteration_index"] += 1
    control["capability_call_count"] += 1

    capability_kind = _normalize_text(selected_capability.get("kind")) or "none"
    capability_ref = _capability_ref(selected_capability, capability_kind)
    result_status = _result_status(capability_result)
    result_stop_reason = _classify_result_stop_reason(capability_result, capability_kind)
    context_stop_reason = _classify_context_stop_reason(context_budget_report)
    stop_reason = context_stop_reason or result_stop_reason
    should_retry = False
    decision = "continue"
    warnings = list(control.get("warnings") if isinstance(control.get("warnings"), list) else [])

    if result_stop_reason in {"provider_failed", "tool_failed"}:
        failure_count_by_key = _record(control.get("failure_count_by_key"))
        failure_count = _non_negative_int(failure_count_by_key.get(capability_ref), 0) + 1
        failure_count_by_key[capability_ref] = failure_count
        control["failure_count_by_key"] = failure_count_by_key
        should_retry = failure_count <= control["retry_budget"]
        decision = "retry" if should_retry else "stop"
        stop_reason = "" if should_retry else result_stop_reason
    elif capability_ref != "none:none":
        control["failure_count_by_key"] = _record(control.get("failure_count_by_key"))

    if not stop_reason and control["iteration_index"] >= control["max_iterations"]:
        stop_reason = "max_iterations_reached"
        decision = "stop"
        should_retry = False
    if not stop_reason and control["capability_call_count"] >= control["max_capability_calls"]:
        stop_reason = "capability_budget_exhausted"
        decision = "stop"
        should_retry = False
    if stop_reason in {"permission_required", "context_budget_exhausted"}:
        decision = "stop"
        should_retry = False

    if stop_reason and stop_reason not in STANDARD_AGENT_STOP_REASONS:
        warnings.append(f"Unknown stop reason normalized to tool_failed: {stop_reason}")
        stop_reason = "tool_failed"

    control["last_stop_reason"] = stop_reason
    control["warnings"] = _dedupe_texts(warnings)
    should_continue = not bool(stop_reason)
    capability_key = capability_ref.split(":", 1)[1] if ":" in capability_ref else capability_ref

    report = {
        "version": 1,
        "decision": decision,
        "stop_reason": stop_reason,
        "iteration_index": control["iteration_index"],
        "max_iterations": control["max_iterations"],
        "capability_call_count": control["capability_call_count"],
        "max_capability_calls": control["max_capability_calls"],
        "selected_capability_kind": capability_kind,
        "selected_capability_key": capability_key,
        "selected_capability_ref": capability_ref,
        "last_result_status": result_status,
        "last_result_stop_reason": result_stop_reason,
        "context_stop_reason": context_stop_reason,
        "retry_budget": control["retry_budget"],
        "warnings": control["warnings"],
    }
    return {
        "status": "succeeded",
        "agent_loop_control": control,
        "agent_loop_report": report,
        "agent_loop_stop_reason": stop_reason,
        "agent_loop_should_continue": should_continue,
        "agent_loop_should_retry": should_retry,
        "reason": decision,
    }


def _normalize_control(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "iteration_index": _non_negative_int(value.get("iteration_index"), 0),
        "max_iterations": _positive_int(value.get("max_iterations"), DEFAULT_MAX_ITERATIONS),
        "capability_call_count": _non_negative_int(value.get("capability_call_count"), 0),
        "max_capability_calls": _positive_int(value.get("max_capability_calls"), DEFAULT_MAX_CAPABILITY_CALLS),
        "failure_count_by_key": _record(value.get("failure_count_by_key")),
        "last_stop_reason": _normalize_text(value.get("last_stop_reason")),
        "retry_budget": _non_negative_int(value.get("retry_budget"), DEFAULT_RETRY_BUDGET),
        "warnings": _dedupe_texts(value.get("warnings") if isinstance(value.get("warnings"), list) else []),
    }


def _classify_result_stop_reason(result: dict[str, Any], capability_kind: str) -> str:
    status = _result_status(result)
    error_type = _normalize_text(result.get("error_type") or result.get("errorType"))
    if status in {"permission_required", "awaiting_permission", "awaiting_human"}:
        return "permission_required"
    if status not in {"failed", "error"} and not error_type:
        return ""
    if any(token in error_type for token in ("provider", "model", "llm", "openai", "api_timeout", "rate_limit")):
        return "provider_failed"
    if capability_kind in {"tool", "action", "subgraph"}:
        return "tool_failed"
    return "tool_failed"


def _classify_context_stop_reason(report: dict[str, Any]) -> str:
    if _normalize_text(report.get("reason")) == "overflow_recovery" and report.get("should_compact") is False:
        return "context_budget_exhausted"
    return ""


def _result_status(result: dict[str, Any]) -> str:
    status = _normalize_text(result.get("status"))
    if status:
        return status
    outputs = result.get("outputs")
    if isinstance(outputs, dict) and outputs:
        return "succeeded"
    return ""


def _capability_ref(capability: dict[str, Any], capability_kind: str) -> str:
    key = (
        _normalize_text(capability.get("actionKey"))
        or _normalize_text(capability.get("action_key"))
        or _normalize_text(capability.get("toolKey"))
        or _normalize_text(capability.get("tool_key"))
        or _normalize_text(capability.get("subgraphKey"))
        or _normalize_text(capability.get("subgraph_key"))
        or _normalize_text(capability.get("key"))
        or "none"
    )
    return f"{capability_kind}:{key}"


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _dedupe_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "failed", "error_type": "invalid_json", "error": str(exc)}, ensure_ascii=False))
        return
    if not isinstance(payload, dict):
        print(
            json.dumps(
                {"status": "failed", "error_type": "invalid_input", "error": "stdin must be a JSON object."},
                ensure_ascii=False,
            )
        )
        return
    print(json.dumps(agent_loop_guard(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
