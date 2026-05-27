from __future__ import annotations

import json
import sys
from typing import Any


LANES = ["todo", "ready", "running", "blocked", "review", "done", "archived"]


def delegation_kanban_board_builder(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        task_packets = [_normalize_task_packet(item) for item in _list_or_empty(inputs.get("worker_task_packets"))]
        merge_package = _as_dict(inputs.get("worker_merge_review_package"))
        workers = _workers_from_inputs(inputs, merge_package)
        cards = _build_cards(task_packets, workers, merge_package)
        columns = {lane: [card for card in cards if card.get("lane") == lane] for lane in LANES}
        columns = {lane: items for lane, items in columns.items() if items}
        board = {
            "kind": "delegation_board_snapshot",
            "version": 1,
            "board_id": _text(inputs.get("board_id")) or "delegation_board",
            "title": _text(inputs.get("board_title")) or "Delegation Board",
            "status": _board_status(cards, merge_package),
            "lanes": LANES,
            "status_counts": _status_counts(cards),
            "columns": columns,
            "cards": cards,
            "source_refs": _dedupe_source_refs(_collect_source_refs(cards, merge_package)),
            "next_actions": _next_actions(cards),
            "merge_review": _merge_review_summary(merge_package),
        }
        return {
            "status": "succeeded",
            "delegation_board_snapshot": board,
            "kanban_board_report": _report(board),
        }
    except Exception as exc:
        board = {
            "kind": "delegation_board_snapshot",
            "version": 1,
            "board_id": _text(inputs.get("board_id")) or "delegation_board",
            "title": _text(inputs.get("board_title")) or "Delegation Board",
            "status": "failed",
            "lanes": LANES,
            "status_counts": {},
            "columns": {},
            "cards": [],
            "source_refs": [],
            "next_actions": [],
            "merge_review": {},
            "errors": [{"message": str(exc)}],
        }
        return {
            "status": "failed",
            "error_type": "delegation_kanban_board_build_failed",
            "error": str(exc),
            "delegation_board_snapshot": board,
            "kanban_board_report": _report(board),
        }


def _workers_from_inputs(inputs: dict[str, Any], merge_package: dict[str, Any]) -> list[dict[str, Any]]:
    workers = [_normalize_worker(item) for item in _list_or_empty(merge_package.get("workers"))]
    if workers:
        return workers
    return [_normalize_worker(item) for item in _list_or_empty(inputs.get("worker_result_packages"))]


def _build_cards(
    task_packets: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    merge_package: dict[str, Any],
) -> list[dict[str, Any]]:
    workers_by_task = {_text(worker.get("task_id")): worker for worker in workers if _text(worker.get("task_id"))}
    tasks_by_id = {_text(task.get("task_id")): task for task in task_packets if _text(task.get("task_id"))}
    ordered_task_ids = [task["task_id"] for task in task_packets]
    for worker in workers:
        task_id = _text(worker.get("task_id"))
        if task_id and task_id not in tasks_by_id and task_id not in ordered_task_ids:
            ordered_task_ids.append(task_id)

    review = _as_dict(merge_package.get("review"))
    global_recommended = _text(review.get("recommended_next_action"))
    risk_flags = _string_list(review.get("risk_flags"))
    budget_exceeded = _list_or_empty(review.get("budget_exceeded"))
    retry_attempts = _list_or_empty(review.get("retry_attempts"))

    cards: list[dict[str, Any]] = []
    for task_id in ordered_task_ids:
        task = tasks_by_id.get(task_id, {"task_id": task_id})
        worker = workers_by_task.get(task_id, {})
        task_risk_flags = [flag for flag in risk_flags if f":{task_id}" in flag]
        task_budget_exceeded = [_as_dict(item) for item in budget_exceeded if _text(_as_dict(item).get("task_id")) == task_id]
        task_retry_attempts = [_as_dict(item) for item in retry_attempts if _text(_as_dict(item).get("task_id")) == task_id]
        retry_count = max([int(item.get("attempts") or 0) for item in task_retry_attempts] or [int(_as_dict(worker.get("budget")).get("attempts") or 0)])
        worker_status = _text(worker.get("status")) or "todo"
        lane = _lane_for(worker_status, task_risk_flags, retry_count)
        block_reason = _block_reason(task_risk_flags, worker)
        card = {
            "task_id": task_id,
            "goal": _text(task.get("goal")) or _text(worker.get("summary")),
            "lane": lane,
            "worker_status": worker_status,
            "summary": _text(worker.get("summary")),
            "allowed_capabilities": _list_or_empty(task.get("allowed_capabilities") or task.get("allowedCapabilities")),
            "budget": _merge_dicts(_as_dict(task.get("budget")), _as_dict(worker.get("budget"))),
            "retry_attempts": retry_count,
            "risk_flags": task_risk_flags,
            "block_reason": block_reason,
            "recommended_next_action": _card_next_action(lane, block_reason, task_risk_flags, global_recommended),
            "source_refs": _dedupe_source_refs(
                _source_ref_list(task.get("context_package_refs") or task.get("contextPackageRefs"))
                + _source_ref_list(worker.get("source_refs"))
            ),
            "outputs": _as_dict(worker.get("outputs")),
            "errors": _list_or_empty(worker.get("errors")),
            "followups": _list_or_empty(worker.get("followups")),
            "budget_exceeded": task_budget_exceeded,
        }
        cards.append(card)
    return cards


def _lane_for(worker_status: str, risk_flags: list[str], retry_count: int) -> str:
    if not worker_status or worker_status == "todo":
        return "todo"
    if worker_status in {"running"}:
        return "running"
    if worker_status in {"failed", "partial", "cancelled", "skipped"}:
        return "blocked"
    if any(flag.startswith("worker_budget_exhausted:") for flag in risk_flags):
        return "blocked"
    if retry_count > 1 or risk_flags:
        return "review"
    if worker_status in {"succeeded", "completed"}:
        return "done"
    return "review"


def _block_reason(risk_flags: list[str], worker: dict[str, Any]) -> str:
    if any(flag.startswith("worker_budget_exhausted:") for flag in risk_flags):
        return "budget_exhausted"
    if any(flag.startswith("missing_required_output:") for flag in risk_flags):
        return "missing_required_output"
    if any(flag.startswith("worker_failed:") for flag in risk_flags):
        return "worker_failed"
    if _list_or_empty(worker.get("errors")):
        return "worker_error"
    return ""


def _card_next_action(lane: str, block_reason: str, risk_flags: list[str], global_recommended: str) -> str:
    if block_reason == "budget_exhausted":
        return "tighten_budget_or_split_task"
    if block_reason == "missing_required_output":
        return "provide_more_context"
    if block_reason == "worker_failed":
        return "retry_failed_workers"
    if lane == "review" and any(flag.startswith("worker_retried:") for flag in risk_flags):
        return "review_retry_result"
    return global_recommended if lane in {"blocked", "review"} else ""


def _next_actions(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actionable: list[dict[str, Any]] = []
    for card in cards:
        action = _text(card.get("recommended_next_action"))
        if not action:
            continue
        actionable.append(
            {
                "task_id": _text(card.get("task_id")),
                "lane": _text(card.get("lane")),
                "action": action,
                "reason": _text(card.get("block_reason")) or ", ".join(_string_list(card.get("risk_flags"))),
            }
        )
    priority = {"blocked": 0, "review": 1, "todo": 2, "ready": 3, "running": 4, "done": 5, "archived": 6}
    return sorted(actionable, key=lambda item: (priority.get(item.get("lane", ""), 9), item.get("task_id", "")))


def _board_status(cards: list[dict[str, Any]], merge_package: dict[str, Any]) -> str:
    if not cards:
        return "empty"
    if any(card.get("lane") == "blocked" for card in cards):
        return "blocked"
    if any(card.get("lane") == "review" for card in cards):
        return "review"
    merge_status = _text(merge_package.get("status"))
    if merge_status:
        return merge_status
    if all(card.get("lane") == "done" for card in cards):
        return "done"
    return "active"


def _status_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        lane = _text(card.get("lane")) or "todo"
        counts[lane] = counts.get(lane, 0) + 1
    return dict(sorted(counts.items()))


def _merge_review_summary(merge_package: dict[str, Any]) -> dict[str, Any]:
    review = _as_dict(merge_package.get("review"))
    return {
        "status": _text(merge_package.get("status")),
        "summary": _text(merge_package.get("summary")),
        "recommended_next_action": _text(review.get("recommended_next_action")),
        "risk_flags": _string_list(review.get("risk_flags")),
    }


def _report(board: dict[str, Any]) -> str:
    lines = ["# Delegation Kanban Board"]
    lines.append(f"- Board: {board.get('title')} ({board.get('board_id')})")
    lines.append(f"- Status: {board.get('status')}")
    counts = _as_dict(board.get("status_counts"))
    if counts:
        lines.append("- Columns: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    for card in _list_or_empty(board.get("cards")):
        record = _as_dict(card)
        task_id = _text(record.get("task_id")) or "unknown"
        lane = _text(record.get("lane")) or "todo"
        summary = _text(record.get("summary") or record.get("goal"))
        lines.append(f"- {task_id}: {lane}" + (f" - {summary}" if summary else ""))
    next_actions = _list_or_empty(board.get("next_actions"))
    if next_actions:
        lines.append("- Next actions: " + ", ".join(f"{item.get('task_id')}={item.get('action')}" for item in next_actions if isinstance(item, dict)))
    return "\n".join(lines)


def _normalize_task_packet(value: Any) -> dict[str, Any]:
    raw = _as_dict(value)
    task_id = _text(raw.get("task_id") or raw.get("taskId"))
    if not task_id:
        return {}
    return {
        "kind": "worker_task_packet",
        "task_id": task_id,
        "goal": _text(raw.get("goal")),
        "allowed_capabilities": _list_or_empty(raw.get("allowed_capabilities") or raw.get("allowedCapabilities")),
        "budget": _as_dict(raw.get("budget")),
        "context_package_refs": _source_ref_list(raw.get("context_package_refs") or raw.get("contextPackageRefs")),
    }


def _normalize_worker(value: Any) -> dict[str, Any]:
    raw = _as_dict(value)
    task_id = _text(raw.get("task_id") or raw.get("taskId"))
    if not task_id:
        return {}
    return {
        "kind": "worker_result_package",
        "task_id": task_id,
        "status": _text(raw.get("status")),
        "summary": _text(raw.get("summary")),
        "outputs": _as_dict(raw.get("outputs")),
        "errors": _list_or_empty(raw.get("errors")),
        "followups": _list_or_empty(raw.get("followups")),
        "budget": _as_dict(raw.get("budget")),
        "source_refs": _source_ref_list(raw.get("source_refs")),
    }


def _collect_source_refs(cards: list[dict[str, Any]], merge_package: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    refs.extend(_source_ref_list(merge_package.get("source_refs")))
    for card in cards:
        refs.extend(_source_ref_list(card.get("source_refs")))
    return refs


def _merge_dicts(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    return {**first, **second}


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


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [_text(item) for item in _list_or_empty(value) if _text(item)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    print(json.dumps(delegation_kanban_board_builder(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
