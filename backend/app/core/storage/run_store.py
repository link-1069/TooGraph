from __future__ import annotations

from typing import Any

from app.core.runtime.run_tree import summarize_run_for_tree
from app.core.storage.database import RUN_DATA_DIR
from app.core.storage.json_file_utils import read_json_file, write_json_file


def save_run(run_state: dict[str, Any]) -> None:
    RUN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json_file(_run_path(run_state["run_id"]), run_state)


def load_run(run_id: str) -> dict[str, Any]:
    RUN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = read_json_file(_run_path(run_id), default=None)
    if payload is None:
        raise FileNotFoundError(f"Run '{run_id}' does not exist.")
    return payload


def list_runs() -> list[dict[str, Any]]:
    RUN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(RUN_DATA_DIR.glob("*.json")):
        payload = read_json_file(path, default=None)
        if payload is not None:
            items.append(payload)
    items.sort(key=lambda item: (str(item.get("started_at", "")), str(item.get("run_id", ""))), reverse=True)
    return items


def list_child_runs(parent_run_id: str) -> list[dict[str, Any]]:
    normalized_parent_run_id = str(parent_run_id or "").strip()
    if not normalized_parent_run_id:
        return []
    children = [
        run
        for run in list_runs()
        if str(run.get("parent_run_id") or "").strip() == normalized_parent_run_id
    ]
    children.sort(key=lambda item: (_run_path_sort_key(item), str(item.get("run_id", ""))))
    return children


def build_run_tree(run_id: str) -> dict[str, Any]:
    root = load_run(run_id)
    runs = list_runs()
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        parent_run_id = str(run.get("parent_run_id") or "").strip()
        if not parent_run_id:
            continue
        children_by_parent.setdefault(parent_run_id, []).append(run)
    for children in children_by_parent.values():
        children.sort(key=lambda item: (_run_path_sort_key(item), str(item.get("run_id", ""))))

    def build_node(run: dict[str, Any], seen: set[str]) -> dict[str, Any]:
        node = summarize_run_for_tree(run)
        current_run_id = str(run.get("run_id") or "")
        if current_run_id in seen:
            return node
        next_seen = {*seen, current_run_id}
        node["children"] = [
            build_node(child, next_seen)
            for child in children_by_parent.get(current_run_id, [])
        ]
        return node

    return build_node(root, set())


def _run_path(run_id: str):
    return RUN_DATA_DIR / f"{run_id}.json"


def _run_path_sort_key(run: dict[str, Any]) -> tuple[int, str, str]:
    path = run.get("run_path")
    path_length = len(path) if isinstance(path, list) else 0
    return (path_length, str(run.get("started_at", "")), str(run.get("run_id", "")))
