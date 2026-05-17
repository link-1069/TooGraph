from __future__ import annotations

import copy
from typing import Any

from app.core.runtime.state import RunState, create_initial_run_state


def create_child_run_state(
    parent_state: dict[str, Any],
    *,
    graph_id: str,
    graph_name: str,
    parent_node_id: str,
    invocation_kind: str,
    invocation_key: str,
    batch_group_id: str = "",
    batch_item_index: int | None = None,
    batch_item_label: str = "",
) -> RunState:
    child = create_initial_run_state(graph_id=graph_id, graph_name=graph_name)
    parent_run_id = str(parent_state.get("run_id") or "").strip()
    parent_root_run_id = str(parent_state.get("root_run_id") or "").strip()
    root_run_id = parent_root_run_id or parent_run_id or str(child.get("run_id") or "")
    parent_path = _normalize_run_path(parent_state.get("run_path"), fallback=parent_run_id)
    child_run_id = str(child.get("run_id") or "")

    child["parent_run_id"] = parent_run_id
    child["root_run_id"] = root_run_id
    child["parent_node_id"] = str(parent_node_id or "").strip()
    child["invocation_kind"] = str(invocation_kind or "").strip()
    child["invocation_key"] = str(invocation_key or "").strip()
    child["run_depth"] = _parent_run_depth(parent_state) + 1
    child["run_path"] = [*parent_path, child_run_id] if parent_path else [child_run_id]
    child["batch_group_id"] = str(batch_group_id or "").strip()
    child["batch_item_index"] = batch_item_index
    child["batch_item_label"] = str(batch_item_label or "").strip()
    child["metadata"] = copy.deepcopy(parent_state.get("metadata") or {})
    child["metadata"]["parent_run_id"] = parent_run_id
    child["metadata"]["root_run_id"] = root_run_id
    child["metadata"]["parent_node_id"] = child["parent_node_id"]
    child["metadata"]["invocation_kind"] = child["invocation_kind"]
    child["metadata"]["invocation_key"] = child["invocation_key"]
    if child["batch_group_id"]:
        child["metadata"]["batch_group_id"] = child["batch_group_id"]
    if batch_item_index is not None:
        child["metadata"]["batch_item_index"] = batch_item_index
    if child["batch_item_label"]:
        child["metadata"]["batch_item_label"] = child["batch_item_label"]
    return child


def summarize_run_for_tree(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(run.get("run_id") or ""),
        "graph_id": str(run.get("graph_id") or ""),
        "graph_name": str(run.get("graph_name") or ""),
        "status": str(run.get("status") or ""),
        "parent_run_id": str(run.get("parent_run_id") or ""),
        "root_run_id": str(run.get("root_run_id") or run.get("run_id") or ""),
        "parent_node_id": str(run.get("parent_node_id") or ""),
        "invocation_kind": str(run.get("invocation_kind") or ""),
        "invocation_key": str(run.get("invocation_key") or ""),
        "run_depth": _int(run.get("run_depth"), default=0),
        "run_path": _normalize_run_path(run.get("run_path"), fallback=str(run.get("run_id") or "")),
        "batch_group_id": str(run.get("batch_group_id") or ""),
        "batch_item_index": run.get("batch_item_index") if isinstance(run.get("batch_item_index"), int) else None,
        "batch_item_label": str(run.get("batch_item_label") or ""),
        "current_node_id": run.get("current_node_id"),
        "started_at": str(run.get("started_at") or ""),
        "completed_at": run.get("completed_at"),
        "duration_ms": run.get("duration_ms"),
        "final_result": str(run.get("final_result") or ""),
        "children": [],
    }


def _normalize_run_path(value: Any, *, fallback: str) -> list[str]:
    if isinstance(value, list):
        path = [str(item).strip() for item in value if str(item or "").strip()]
        if path:
            return path
    fallback = str(fallback or "").strip()
    return [fallback] if fallback else []


def _parent_run_depth(parent_state: dict[str, Any]) -> int:
    return _int(parent_state.get("run_depth"), default=max(0, len(_normalize_run_path(parent_state.get("run_path"), fallback="")) - 1))


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
