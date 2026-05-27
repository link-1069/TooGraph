from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.core.storage.run_store import load_run
from app.evaluator.checks import evaluate_case_checks, summarize_check_status


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "error", "awaiting_human", "permission_required"}
CHECKABLE_RUN_STATUSES = {"completed", "awaiting_human", "permission_required"}
PROVIDER_FALLBACK_TRACE_KEYS = (
    "provider_fallback_trace",
    "structured_output_repair_provider_fallback_trace",
    "action_input_provider_fallback_trace",
    "action_input_structured_output_repair_provider_fallback_trace",
    "subgraph_input_provider_fallback_trace",
    "subgraph_input_structured_output_repair_provider_fallback_trace",
)


class EvalGraphRunNotReady(ValueError):
    pass


def collect_eval_case_result_payload(
    case: dict[str, Any],
    case_result: dict[str, Any],
    *,
    judge_runner: Any | None = None,
) -> dict[str, Any]:
    graph_run_id = str(case_result.get("graph_run_id") or "").strip()
    if not graph_run_id:
        raise KeyError("graph_run_id")

    graph_run = load_run(graph_run_id)
    run_status = str(graph_run.get("status") or "").strip()
    if run_status not in TERMINAL_RUN_STATUSES:
        raise EvalGraphRunNotReady(f"Graph run '{graph_run_id}' is not terminal: {run_status or 'unknown'}.")

    final_output = extract_final_output(graph_run)
    artifacts = extract_artifacts(graph_run)
    node_failures = extract_node_failures(graph_run)
    errors = [str(error) for error in graph_run.get("errors", []) if str(error or "").strip()]
    if run_status in CHECKABLE_RUN_STATUSES and not node_failures and not errors:
        check_results = evaluate_case_checks(
            case,
            final_output=final_output,
            artifacts=artifacts,
            judge_runner=judge_runner,
        )
        status = summarize_check_status(check_results)
        error = ""
    else:
        check_results = []
        status = "error"
        error = "\n".join(errors) or f"Graph run '{graph_run_id}' ended with status '{run_status}'."

    return {
        "graph_run_id": graph_run_id,
        "status": status,
        "final_output": final_output,
        "error": error,
        "artifacts": artifacts,
        "node_failures": node_failures,
        "human_review": case_result.get("human_review") or {},
        "check_results": check_results,
    }


def extract_final_output(graph_run: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for preview in _as_list(graph_run.get("output_previews")):
        if not isinstance(preview, dict):
            continue
        key = _output_key(preview)
        if not key:
            continue
        value = copy.deepcopy(preview.get("value"))
        output[key] = value
        tail_key = key.rsplit(".", 1)[-1]
        if tail_key and tail_key not in output:
            output[tail_key] = copy.deepcopy(value)

    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    state_values = artifacts.get("state_values") if isinstance(artifacts.get("state_values"), dict) else {}
    for key, value in state_values.items():
        output.setdefault(str(key), copy.deepcopy(value))

    final_result = graph_run.get("final_result")
    if final_result not in (None, "", [], {}):
        output["final_result"] = copy.deepcopy(final_result)
    provider_fallback_traces = extract_provider_fallback_traces(graph_run)
    if provider_fallback_traces:
        output.setdefault("provider_fallback_trace", copy.deepcopy(provider_fallback_traces[0]))
    return output


def extract_artifacts(graph_run: dict[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for saved in _collect_saved_outputs(graph_run):
        if not isinstance(saved, dict):
            continue
        record = copy.deepcopy(saved)
        for key in _artifact_keys(record):
            artifacts.setdefault(key, record)
    artifacts["saved_outputs"] = _collect_saved_outputs(graph_run)
    artifacts["output_previews"] = _as_list(graph_run.get("output_previews"))
    artifacts["graph_run"] = extract_graph_run_summary(graph_run)
    return artifacts


def extract_graph_run_summary(graph_run: dict[str, Any]) -> dict[str, Any]:
    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    state_values = artifacts.get("state_values") if isinstance(artifacts.get("state_values"), dict) else {}
    direct_state_values = graph_run.get("state_values") if isinstance(graph_run.get("state_values"), dict) else {}
    merged_state_values = {**direct_state_values, **state_values}
    graph_snapshot = graph_run.get("graph_snapshot") if isinstance(graph_run.get("graph_snapshot"), dict) else {}
    graph_nodes = graph_snapshot.get("nodes") if isinstance(graph_snapshot.get("nodes"), dict) else {}
    node_status_map = graph_run.get("node_status_map") if isinstance(graph_run.get("node_status_map"), dict) else {}
    node_executions = [copy.deepcopy(item) for item in _as_list(graph_run.get("node_executions")) if isinstance(item, dict)]
    activity_events = [copy.deepcopy(item) for item in _as_list(graph_run.get("activity_events")) if isinstance(item, dict)]
    child_runs = [item for item in _as_list(graph_run.get("children")) if isinstance(item, dict)]

    return {
        "run_id": str(graph_run.get("run_id") or ""),
        "status": str(graph_run.get("status") or ""),
        "graph_id": str(graph_run.get("graph_id") or ""),
        "graph_name": str(graph_run.get("graph_name") or ""),
        "template_id": str(graph_run.get("template_id") or ""),
        "runtime_backend": str(graph_run.get("runtime_backend") or ""),
        "metadata": copy.deepcopy(graph_run.get("metadata") if isinstance(graph_run.get("metadata"), dict) else {}),
        "state_values": copy.deepcopy(merged_state_values),
        "state_keys": sorted(str(key) for key in merged_state_values.keys()),
        "output_keys": _dedupe(
            [
                key
                for key in (
                    _output_key(preview)
                    for preview in _as_list(graph_run.get("output_previews"))
                    if isinstance(preview, dict)
                )
                if key
            ]
        ),
        "node_ids": _dedupe(
            [
                *[str(key) for key in graph_nodes.keys()],
                *[str(key) for key in node_status_map.keys()],
                *[str(execution.get("node_id") or "") for execution in node_executions],
            ]
        ),
        "node_status_map": copy.deepcopy(node_status_map),
        "node_execution_count": len(node_executions),
        "node_executions": node_executions,
        "activity_kinds": _dedupe(
            [str(event.get("kind") or "") for event in activity_events if str(event.get("kind") or "").strip()]
        ),
        "child_run_ids": _dedupe(
            [str(child.get("run_id") or "") for child in child_runs if str(child.get("run_id") or "")]
        ),
        "provider_fallback_traces": extract_provider_fallback_traces(graph_run),
        "action_invocations": extract_action_invocations(graph_run),
        "tool_invocations": extract_tool_invocations(graph_run),
        "subgraph_invocations": extract_subgraph_invocations(graph_run),
    }


def extract_provider_fallback_traces(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    state_values = artifacts.get("state_values") if isinstance(artifacts.get("state_values"), dict) else {}
    direct_state_values = graph_run.get("state_values") if isinstance(graph_run.get("state_values"), dict) else {}
    for values in (direct_state_values, state_values):
        for key in PROVIDER_FALLBACK_TRACE_KEYS:
            _append_provider_fallback_trace(traces, values.get(key))
    for execution in _as_list(graph_run.get("node_executions")):
        if not isinstance(execution, dict):
            continue
        execution_artifacts = execution.get("artifacts")
        if not isinstance(execution_artifacts, dict):
            continue
        runtime_config = execution_artifacts.get("runtime_config")
        if not isinstance(runtime_config, dict):
            continue
        for key in PROVIDER_FALLBACK_TRACE_KEYS:
            _append_provider_fallback_trace(traces, runtime_config.get(key))
    return traces


def _append_provider_fallback_trace(traces: list[dict[str, Any]], value: Any) -> None:
    if not isinstance(value, dict):
        return
    if str(value.get("kind") or "") != "provider_fallback_trace" and not value.get("fallback_used"):
        return
    model_ref = _provider_fallback_trace_signature(value)
    if model_ref and any(_provider_fallback_trace_signature(existing) == model_ref for existing in traces):
        return
    traces.append(copy.deepcopy(value))


def extract_tool_invocations(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for output in _as_list(graph_run.get("tool_outputs")):
        if isinstance(output, dict):
            _append_tool_invocation(invocations, output)

    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    for output in _as_list(artifacts.get("tool_outputs")):
        if isinstance(output, dict):
            _append_tool_invocation(invocations, output)

    for execution in _as_list(graph_run.get("node_executions")):
        if not isinstance(execution, dict):
            continue
        execution_artifacts = execution.get("artifacts")
        if not isinstance(execution_artifacts, dict):
            continue
        for output in _as_list(execution_artifacts.get("tool_outputs")):
            if isinstance(output, dict):
                _append_tool_invocation(invocations, output)
    return invocations


def extract_action_invocations(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for output in _as_list(graph_run.get("action_outputs")):
        if isinstance(output, dict):
            _append_action_invocation(invocations, output)

    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    for output in _as_list(artifacts.get("action_outputs")):
        if isinstance(output, dict):
            _append_action_invocation(invocations, output)

    for execution in _as_list(graph_run.get("node_executions")):
        if not isinstance(execution, dict):
            continue
        execution_artifacts = execution.get("artifacts")
        if not isinstance(execution_artifacts, dict):
            continue
        for output in _as_list(execution_artifacts.get("action_outputs")):
            if isinstance(output, dict):
                _append_action_invocation(invocations, output)
    return invocations


def extract_subgraph_invocations(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for output in _as_list(graph_run.get("capability_outputs")):
        if isinstance(output, dict):
            _append_subgraph_invocation(invocations, output)

    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    for output in _as_list(artifacts.get("capability_outputs")):
        if isinstance(output, dict):
            _append_subgraph_invocation(invocations, output)

    for execution in _as_list(graph_run.get("node_executions")):
        if not isinstance(execution, dict):
            continue
        execution_artifacts = execution.get("artifacts")
        if not isinstance(execution_artifacts, dict):
            continue
        for output in _as_list(execution_artifacts.get("capability_outputs")):
            if isinstance(output, dict):
                _append_subgraph_invocation(invocations, output)

    for event in _as_list(graph_run.get("activity_events")):
        if isinstance(event, dict):
            _append_subgraph_activity_invocation(invocations, event)
    for event in _as_list(artifacts.get("activity_events")):
        if isinstance(event, dict):
            _append_subgraph_activity_invocation(invocations, event)
    return invocations


def _append_action_invocation(invocations: list[dict[str, Any]], value: dict[str, Any]) -> None:
    record = {
        "node_id": str(value.get("node_id") or ""),
        "action_key": str(value.get("action_key") or value.get("actionKey") or value.get("action_name") or ""),
        "action_name": str(value.get("action_name") or value.get("actionName") or ""),
        "status": str(value.get("status") or ""),
        "error": str(value.get("error") or ""),
        "error_type": str(value.get("error_type") or value.get("errorType") or ""),
        "duration_ms": value.get("duration_ms", value.get("durationMs")),
        "input_keys": sorted(str(key) for key in (value.get("inputs") or {}).keys())
        if isinstance(value.get("inputs"), dict)
        else [],
        "output_keys": sorted(str(key) for key in (value.get("outputs") or {}).keys())
        if isinstance(value.get("outputs"), dict)
        else [],
    }
    signature = (
        record["node_id"],
        record["action_key"],
        record["status"],
        record["error_type"],
        str(record["duration_ms"]),
    )
    existing_signatures = {
        (
            str(item.get("node_id") or ""),
            str(item.get("action_key") or ""),
            str(item.get("status") or ""),
            str(item.get("error_type") or ""),
            str(item.get("duration_ms") or ""),
        )
        for item in invocations
    }
    if signature not in existing_signatures:
        invocations.append(record)


def _append_subgraph_invocation(invocations: list[dict[str, Any]], value: dict[str, Any]) -> None:
    capability_kind = str(value.get("capability_kind") or value.get("sourceType") or "").strip()
    if capability_kind and capability_kind != "subgraph":
        return
    subgraph_key = str(
        value.get("capability_key")
        or value.get("subgraph_key")
        or value.get("subgraphKey")
        or value.get("sourceKey")
        or ""
    ).strip()
    if not subgraph_key:
        return
    inputs = value.get("inputs") if isinstance(value.get("inputs"), dict) else {}
    outputs = value.get("outputs") if isinstance(value.get("outputs"), dict) else {}
    record = {
        "node_id": str(value.get("node_id") or value.get("nodeId") or ""),
        "subgraph_key": subgraph_key,
        "subgraph_name": str(value.get("capability_name") or value.get("subgraph_name") or value.get("sourceName") or ""),
        "status": str(value.get("status") or ""),
        "error": str(value.get("error") or ""),
        "error_type": str(value.get("error_type") or value.get("errorType") or ""),
        "duration_ms": value.get("duration_ms", value.get("durationMs")),
        "child_run_id": str(value.get("child_run_id") or value.get("childRunId") or value.get("triggered_run_id") or ""),
        "input_keys": sorted(str(key) for key in inputs.keys()),
        "output_keys": sorted(str(key) for key in outputs.keys()),
    }
    _append_unique_subgraph_invocation(invocations, record)


def _append_subgraph_activity_invocation(invocations: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if str(value.get("kind") or "") != "subgraph_invocation":
        return
    detail = value.get("detail") if isinstance(value.get("detail"), dict) else {}
    subgraph_key = str(detail.get("capability_key") or detail.get("subgraph_key") or detail.get("subgraphKey") or "").strip()
    if not subgraph_key:
        return
    record = {
        "node_id": str(value.get("node_id") or value.get("nodeId") or ""),
        "subgraph_key": subgraph_key,
        "subgraph_name": str(detail.get("capability_name") or detail.get("subgraph_name") or ""),
        "status": str(value.get("status") or ""),
        "error": str(value.get("error") or ""),
        "error_type": str(detail.get("error_type") or detail.get("errorType") or ""),
        "duration_ms": value.get("duration_ms", value.get("durationMs")),
        "child_run_id": str(detail.get("child_run_id") or detail.get("triggered_run_id") or ""),
        "input_keys": sorted(str(item) for item in _as_list(detail.get("input_keys"))),
        "output_keys": sorted(str(item) for item in _as_list(detail.get("output_keys"))),
    }
    _append_unique_subgraph_invocation(invocations, record)


def _append_unique_subgraph_invocation(invocations: list[dict[str, Any]], record: dict[str, Any]) -> None:
    signature = (
        record["node_id"],
        record["subgraph_key"],
        record["status"],
        record["error_type"],
        str(record["duration_ms"]),
    )
    existing_signatures = {
        (
            str(item.get("node_id") or ""),
            str(item.get("subgraph_key") or ""),
            str(item.get("status") or ""),
            str(item.get("error_type") or ""),
            str(item.get("duration_ms") or ""),
        )
        for item in invocations
    }
    if signature not in existing_signatures:
        invocations.append(record)


def _append_tool_invocation(invocations: list[dict[str, Any]], value: dict[str, Any]) -> None:
    record = {
        "node_id": str(value.get("node_id") or ""),
        "tool_key": str(value.get("tool_key") or value.get("toolKey") or ""),
        "tool_name": str(value.get("tool_name") or value.get("toolName") or ""),
        "status": str(value.get("status") or ""),
        "error": str(value.get("error") or ""),
        "error_type": str(value.get("error_type") or value.get("errorType") or ""),
        "duration_ms": value.get("duration_ms", value.get("durationMs")),
        "input_keys": sorted(str(key) for key in (value.get("inputs") or {}).keys())
        if isinstance(value.get("inputs"), dict)
        else [],
        "output_keys": sorted(str(key) for key in (value.get("outputs") or {}).keys())
        if isinstance(value.get("outputs"), dict)
        else [],
    }
    signature = (
        record["node_id"],
        record["tool_key"],
        record["status"],
        record["error_type"],
        str(record["duration_ms"]),
    )
    existing_signatures = {
        (
            str(item.get("node_id") or ""),
            str(item.get("tool_key") or ""),
            str(item.get("status") or ""),
            str(item.get("error_type") or ""),
            str(item.get("duration_ms") or ""),
        )
        for item in invocations
    }
    if signature not in existing_signatures:
        invocations.append(record)


def _provider_fallback_trace_signature(trace: dict[str, Any]) -> tuple[str, str]:
    requested = trace.get("requested") if isinstance(trace.get("requested"), dict) else {}
    selected = trace.get("selected") if isinstance(trace.get("selected"), dict) else {}
    return (
        str(requested.get("model_ref") or f"{requested.get('provider_id', '')}/{requested.get('model', '')}"),
        str(selected.get("model_ref") or f"{selected.get('provider_id', '')}/{selected.get('model', '')}"),
    )


def extract_node_failures(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for execution in _as_list(graph_run.get("node_executions")):
        if not isinstance(execution, dict):
            continue
        status = str(execution.get("status") or "").strip()
        if status not in {"failed", "error"}:
            continue
        failures.append(
            {
                "node_id": str(execution.get("node_id") or ""),
                "node_type": str(execution.get("node_type") or ""),
                "status": status,
                "errors": _as_list(execution.get("errors")),
            }
        )
    return failures


def _collect_saved_outputs(graph_run: dict[str, Any]) -> list[dict[str, Any]]:
    saved_outputs = [copy.deepcopy(item) for item in _as_list(graph_run.get("saved_outputs")) if isinstance(item, dict)]
    artifacts = graph_run.get("artifacts") if isinstance(graph_run.get("artifacts"), dict) else {}
    for exported in _as_list(artifacts.get("exported_outputs")):
        if not isinstance(exported, dict) or not isinstance(exported.get("saved_file"), dict):
            continue
        saved_file = dict(exported["saved_file"])
        saved_outputs.append(
            {
                **saved_file,
                "node_id": exported.get("node_id"),
                "source_key": exported.get("source_key") or saved_file.get("source_key", ""),
            }
        )
    return saved_outputs


def _output_key(preview: dict[str, Any]) -> str:
    for raw_key in (preview.get("source_key"), preview.get("label"), preview.get("node_id")):
        key = str(raw_key or "").strip()
        if key:
            return key
    return ""


def _artifact_keys(record: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for raw_key in (record.get("file_name"), record.get("source_key"), record.get("path")):
        key = str(raw_key or "").strip()
        if key:
            keys.append(key)
            if "/" in key:
                keys.append(Path(key).name)
    return _dedupe(keys)


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
