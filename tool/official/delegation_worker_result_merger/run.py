from __future__ import annotations

import json
import sys
from typing import Any


TERMINAL_STATUSES = {"succeeded", "completed", "failed", "partial", "cancelled", "skipped"}
SUCCESS_STATUSES = {"succeeded", "completed"}


def delegation_worker_result_merger(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        workers = [_normalize_worker_package(item) for item in _worker_package_inputs(inputs)]
        expected_output_schema = _as_dict(inputs.get("expected_output_schema") or inputs.get("expectedOutputSchema"))
        review_policy = _as_dict(inputs.get("review_policy") or inputs.get("reviewPolicy"))
        merged_outputs = _merge_outputs(workers, expected_output_schema)
        status_counts = _status_counts(workers)
        status = _aggregate_status(status_counts, len(workers))
        source_refs = _dedupe_source_refs(_collect_source_refs(workers))
        worker_runs = _worker_runs(workers)
        budget = _merge_budgets(workers)
        artifacts = _merge_list_field(workers, "artifacts")
        errors = _merge_list_field(workers, "errors")
        followups = _merge_list_field(workers, "followups")
        budget_exceeded = _budget_exceeded(workers)
        retry_attempts = _retry_attempts(workers)
        risk_flags = _risk_flags(
            workers,
            merged_outputs,
            expected_output_schema=expected_output_schema,
            review_policy=review_policy,
            budget_exceeded=budget_exceeded,
            retry_attempts=retry_attempts,
        )
        review = {
            "needs_review": bool(risk_flags) or status != "succeeded",
            "risk_flags": risk_flags,
            "budget_exceeded": budget_exceeded,
            "retry_attempts": retry_attempts,
            "recommended_next_action": _recommended_next_action(
                workers=workers,
                risk_flags=risk_flags,
                status=status,
            ),
        }
        package = {
            "kind": "worker_merge_review_package",
            "version": 1,
            "status": status,
            "summary": _summary(inputs, workers, status, risk_flags),
            "worker_count": len(workers),
            "status_counts": status_counts,
            "outputs": merged_outputs,
            "artifacts": artifacts,
            "errors": errors,
            "followups": followups,
            "source_refs": source_refs,
            "worker_runs": worker_runs,
            "budget": budget,
            "review": review,
            "workers": workers,
        }
        report = _report(package, inputs)
        return {
            "status": "succeeded",
            "worker_merge_review_package": package,
            "merge_review_report": report,
        }
    except Exception as exc:
        package = {
            "kind": "worker_merge_review_package",
            "version": 1,
            "status": "failed",
            "summary": str(exc),
            "worker_count": 0,
            "status_counts": {},
            "outputs": {},
            "artifacts": [],
            "errors": [{"message": str(exc)}],
            "followups": [],
            "source_refs": [],
            "worker_runs": [],
            "budget": {},
            "review": {
                "needs_review": True,
                "risk_flags": ["merge_failed"],
                "recommended_next_action": "review",
            },
            "workers": [],
        }
        return {
            "status": "failed",
            "error_type": "delegation_worker_result_merge_failed",
            "error": str(exc),
            "worker_merge_review_package": package,
            "merge_review_report": _report(package, inputs),
        }


def _worker_package_inputs(inputs: dict[str, Any]) -> list[Any]:
    value = inputs.get("worker_result_packages")
    if isinstance(value, list):
        return value
    value = inputs.get("worker_results")
    if isinstance(value, list):
        return value
    value = inputs.get("worker_result_package")
    return [value] if isinstance(value, dict) else []


def _normalize_worker_package(value: Any) -> dict[str, Any]:
    raw = _as_dict(value)
    task_id = _text(raw.get("task_id") or raw.get("taskId"))
    status = _normalize_status(raw.get("status"), raw)
    outputs = _normalize_outputs(raw.get("outputs"))
    worker = {
        "kind": "worker_result_package",
        "version": int(raw.get("version") or 1) if _is_intish(raw.get("version")) else 1,
        "task_id": task_id,
        "status": status,
        "summary": _text(raw.get("summary")),
        "outputs": outputs,
        "artifacts": _list_or_empty(raw.get("artifacts")),
        "errors": _list_or_empty(raw.get("errors")),
        "followups": _list_or_empty(raw.get("followups")),
        "source_refs": _dedupe_source_refs(_source_ref_list(raw.get("source_refs")) + _output_source_refs(outputs)),
        "allowed_capabilities": _list_or_empty(raw.get("allowed_capabilities") or raw.get("allowedCapabilities")),
        "budget": _as_dict(raw.get("budget")),
    }
    for key in ("child_run_id", "childRunId", "worker_run_id", "workerRunId", "run_id", "runId"):
        run_id = _text(raw.get(key))
        if run_id:
            worker["worker_run_id"] = run_id
            break
    return worker


def _normalize_outputs(value: Any) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}
    for key, raw_output in _as_dict(value).items():
        output_key = _text(key)
        if not output_key:
            continue
        record = _as_dict(raw_output)
        if record:
            output_value = record.get("value") if "value" in record else raw_output
            output_type = _text(record.get("type") or record.get("valueType")) or _infer_type(output_value)
            output_record = {
                "name": _text(record.get("name")) or output_key,
                "type": output_type,
                "value": output_value,
            }
            source_refs = _source_ref_list(record.get("source_refs"))
            if source_refs:
                output_record["source_refs"] = source_refs
            outputs[output_key] = output_record
        else:
            outputs[output_key] = {
                "name": output_key,
                "type": _infer_type(raw_output),
                "value": raw_output,
            }
    return outputs


def _normalize_status(value: Any, raw: dict[str, Any]) -> str:
    status = _text(value).lower()
    if status in TERMINAL_STATUSES:
        return "succeeded" if status == "completed" else status
    if _list_or_empty(raw.get("errors")):
        return "failed"
    return "succeeded" if _as_dict(raw.get("outputs")) else "partial"


def _merge_outputs(
    workers: list[dict[str, Any]],
    expected_output_schema: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for worker in workers:
        task_id = _text(worker.get("task_id"))
        status = _text(worker.get("status"))
        for output_key, output in _as_dict(worker.get("outputs")).items():
            key = _text(output_key)
            if not key:
                continue
            schema_record = _as_dict(expected_output_schema.get(key))
            merged_record = merged.setdefault(
                key,
                {
                    "name": _text(schema_record.get("name")) or _text(output.get("name")) or key,
                    "type": _text(schema_record.get("type") or schema_record.get("valueType") or output.get("type"))
                    or "json",
                    "values": [],
                },
            )
            merged_record["values"].append(
                {
                    "task_id": task_id,
                    "status": status,
                    "value": output.get("value"),
                    "source_refs": _source_ref_list(output.get("source_refs")),
                }
            )
    return merged


def _status_counts(workers: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for worker in workers:
        status = _text(worker.get("status")) or "partial"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _aggregate_status(status_counts: dict[str, int], worker_count: int) -> str:
    if worker_count <= 0:
        return "failed"
    if status_counts.get("succeeded") == worker_count:
        return "succeeded"
    if status_counts.get("cancelled") == worker_count:
        return "cancelled"
    if status_counts.get("skipped") == worker_count:
        return "skipped"
    if status_counts.get("failed") == worker_count:
        return "failed"
    return "partial"


def _risk_flags(
    workers: list[dict[str, Any]],
    merged_outputs: dict[str, Any],
    *,
    expected_output_schema: dict[str, Any],
    review_policy: dict[str, Any],
    budget_exceeded: list[dict[str, Any]],
    retry_attempts: list[dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    for worker in workers:
        task_id = _text(worker.get("task_id")) or "unknown"
        status = _text(worker.get("status"))
        if status == "failed":
            flags.append(f"worker_failed:{task_id}")
        elif status in {"partial", "cancelled", "skipped"}:
            flags.append(f"worker_{status}:{task_id}")
    required_outputs = set(expected_output_schema.keys())
    required_outputs.update(_text(item) for item in _list_or_empty(review_policy.get("require_outputs")))
    for output_key in sorted(key for key in required_outputs if _text(key)):
        if output_key not in merged_outputs:
            flags.append(f"missing_required_output:{output_key}")
    if review_policy.get("require_all_succeeded") and any(_text(worker.get("status")) != "succeeded" for worker in workers):
        if "workers_not_all_succeeded" not in flags:
            flags.append("workers_not_all_succeeded")
    for item in budget_exceeded:
        task_id = _text(item.get("task_id")) or "unknown"
        limit = _text(item.get("limit")) or "budget"
        flags.append(f"worker_budget_exhausted:{task_id}:{limit}")
    for item in retry_attempts:
        task_id = _text(item.get("task_id")) or "unknown"
        attempts = _text(item.get("attempts")) or "unknown"
        flags.append(f"worker_retried:{task_id}:{attempts}")
    return flags


def _recommended_next_action(*, workers: list[dict[str, Any]], risk_flags: list[str], status: str) -> str:
    if not workers:
        return "provide_more_context"
    if any(flag.startswith("missing_required_output:") for flag in risk_flags):
        return "provide_more_context"
    if any(flag.startswith("worker_budget_exhausted:") for flag in risk_flags):
        return "tighten_budget_or_split_task"
    if any(flag.startswith("worker_failed:") for flag in risk_flags):
        return "retry_failed_workers"
    if risk_flags or status != "succeeded":
        return "review"
    return "accept"


def _summary(
    inputs: dict[str, Any],
    workers: list[dict[str, Any]],
    status: str,
    risk_flags: list[str],
) -> str:
    merge_goal = _text(inputs.get("merge_goal") or inputs.get("mergeGoal"))
    prefix = f"{status}: merged {len(workers)} worker result package(s)"
    if merge_goal:
        prefix = f"{prefix} for {merge_goal}"
    if risk_flags:
        return f"{prefix}. Review flags: {', '.join(risk_flags)}."
    return f"{prefix}."


def _report(package: dict[str, Any], inputs: dict[str, Any]) -> str:
    merge_goal = _text(inputs.get("merge_goal") or inputs.get("mergeGoal"))
    lines = ["# Delegation Worker Merge Review"]
    if merge_goal:
        lines.append(f"- Goal: {merge_goal}")
    lines.append(f"- Status: {package.get('status')}")
    lines.append(f"- Workers: {package.get('worker_count')}")
    status_counts = _as_dict(package.get("status_counts"))
    if status_counts:
        lines.append("- Status counts: " + ", ".join(f"{key}={value}" for key, value in status_counts.items()))
    for worker in _list_or_empty(package.get("workers")):
        task_id = _text(_as_dict(worker).get("task_id")) or "unknown"
        status = _text(_as_dict(worker).get("status")) or "partial"
        summary = _text(_as_dict(worker).get("summary"))
        lines.append(f"- Worker {task_id}: {status}" + (f" - {summary}" if summary else ""))
    review = _as_dict(package.get("review"))
    risk_flags = _list_or_empty(review.get("risk_flags"))
    if risk_flags:
        lines.append("- Review flags: " + ", ".join(str(item) for item in risk_flags))
    recommended = _text(review.get("recommended_next_action"))
    if recommended:
        lines.append(f"- Recommended next action: {recommended}")
    return "\n".join(lines)


def _merge_list_field(workers: list[dict[str, Any]], field: str) -> list[Any]:
    merged: list[Any] = []
    for worker in workers:
        task_id = _text(worker.get("task_id"))
        for item in _list_or_empty(worker.get(field)):
            record = dict(item) if isinstance(item, dict) else {"value": item}
            if task_id and "task_id" not in record:
                record["task_id"] = task_id
            merged.append(record)
    return merged


def _merge_budgets(workers: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for worker in workers:
        for key, value in _as_dict(worker.get("budget")).items():
            key_text = str(key)
            if _is_number(value):
                merged[key_text] = merged.get(key_text, 0) + value
            elif key_text not in merged:
                merged[key_text] = value
    return merged


def _budget_exceeded(workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exceeded: list[dict[str, Any]] = []
    for worker in workers:
        task_id = _text(worker.get("task_id")) or "unknown"
        budget = _as_dict(worker.get("budget"))
        for key, max_value in budget.items():
            key_text = str(key)
            if not key_text.startswith("max_") or not _is_number(max_value):
                continue
            used_key = f"used_{key_text[4:]}"
            used_value = budget.get(used_key)
            if not _is_number(used_value) or used_value <= max_value:
                continue
            exceeded.append(
                {
                    "task_id": task_id,
                    "limit": key_text,
                    "used": used_value,
                    "max": max_value,
                }
            )
    return sorted(exceeded, key=lambda item: (str(item.get("task_id")), str(item.get("limit"))))


def _retry_attempts(workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for worker in workers:
        task_id = _text(worker.get("task_id")) or "unknown"
        budget = _as_dict(worker.get("budget"))
        attempt_count = budget.get("attempts") or worker.get("attempts")
        if not _is_number(attempt_count) or attempt_count <= 1:
            continue
        attempts.append({"task_id": task_id, "attempts": attempt_count})
    return sorted(attempts, key=lambda item: (str(item.get("task_id")), float(item.get("attempts") or 0)))


def _collect_source_refs(workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for worker in workers:
        refs.extend(_source_ref_list(worker.get("source_refs")))
        refs.extend(_output_source_refs(_as_dict(worker.get("outputs"))))
    return refs


def _worker_runs(workers: list[dict[str, Any]]) -> list[dict[str, str]]:
    runs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for worker in workers:
        task_id = _text(worker.get("task_id"))
        run_ids = [_text(worker.get("worker_run_id"))]
        for ref in _source_ref_list(worker.get("source_refs")):
            if ref.get("source_kind") == "graph_run":
                run_ids.append(_text(ref.get("source_id")))
        for run_id in run_ids:
            if not run_id:
                continue
            key = (task_id, run_id)
            if key in seen:
                continue
            seen.add(key)
            runs.append({"run_id": run_id, "task_id": task_id})
    return runs


def _output_source_refs(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for output in outputs.values():
        record = _as_dict(output)
        refs.extend(_source_ref_list(record.get("source_refs")))
        value = record.get("value")
        if isinstance(value, dict):
            refs.extend(_source_ref_list(value.get("source_refs")))
            if _text(value.get("source_kind")) and _text(value.get("source_id")):
                refs.append(value)
        elif isinstance(value, list):
            refs.extend(_source_ref_list(value))
    return refs


def _source_ref_list(value: Any) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in (value if isinstance(value, list) else []):
        record = _as_dict(item)
        source_kind = _text(record.get("source_kind") or record.get("kind"))
        source_id = _text(record.get("source_id") or record.get("id"))
        if source_kind and source_id:
            refs.append({"source_kind": source_kind, "source_id": source_id})
    return refs


def _dedupe_source_refs(refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        source_kind = _text(ref.get("source_kind"))
        source_id = _text(ref.get("source_id"))
        if not source_kind or not source_id:
            continue
        key = (source_kind, source_id)
        if key in seen:
            continue
        seen.add(key)
        result.append({"source_kind": source_kind, "source_id": source_id})
    return result


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, dict | list):
        return "json"
    text = _text(value)
    if "\n" in text or len(text) > 120:
        return "markdown"
    return "text"


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_intish(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    print(json.dumps(delegation_worker_result_merger(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
