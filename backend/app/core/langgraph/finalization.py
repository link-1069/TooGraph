from __future__ import annotations

from typing import Any, Callable

from app.core.langgraph.checkpoints import JsonCheckpointSaver
from app.core.langgraph.checkpoint_runtime import sync_checkpoint_metadata
from app.core.langgraph.cycle_tracker import finalize_langgraph_cycle_summary
from app.core.langgraph.interrupts import clear_pending_interrupt_metadata, next_run_snapshot_id
from app.core.runtime.agent_stop_reason import set_agent_stop_reason
from app.core.runtime.node_execution_records import duration_between_iso_ms, find_latest_running_execution
from app.core.runtime.output_boundaries import collect_output_boundaries
from app.core.runtime.run_artifacts import append_run_snapshot, refresh_run_artifacts
from app.core.runtime.run_events import publish_run_event
from app.core.runtime.state import set_run_status, utc_now_iso
from app.core.schemas.node_system import NodeSystemGraphDocument
from app.core.storage.run_store import save_run


def finalize_completed_langgraph_state(
    graph: NodeSystemGraphDocument,
    state: dict[str, Any],
    active_edge_ids: set[str],
    cycle_tracker: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    *,
    started_perf: float,
    checkpoint_saver: JsonCheckpointSaver,
    checkpoint_lookup_config: dict[str, Any],
    append_snapshot: bool,
    clear_pending_interrupt_metadata_func: Callable[..., None] = clear_pending_interrupt_metadata,
    set_run_status_func: Callable[..., None] = set_run_status,
    collect_output_boundaries_func: Callable[..., None] = collect_output_boundaries,
    finalize_cycle_summary_func: Callable[..., None] = finalize_langgraph_cycle_summary,
    set_agent_stop_reason_func: Callable[..., None] = set_agent_stop_reason,
    sync_checkpoint_metadata_func: Callable[..., None] = sync_checkpoint_metadata,
    refresh_run_artifacts_func: Callable[..., None] = refresh_run_artifacts,
    next_run_snapshot_id_func: Callable[..., str] = next_run_snapshot_id,
    append_run_snapshot_func: Callable[..., None] = append_run_snapshot,
    save_run_func: Callable[..., None] = save_run,
    publish_run_event_func: Callable[..., None] = publish_run_event,
) -> dict[str, Any]:
    clear_pending_interrupt_metadata_func(state)
    set_run_status_func(state, "completed")
    state["current_node_id"] = None
    collect_output_boundaries_func(graph, state, active_edge_ids)
    finalize_cycle_summary_func(state, cycle_tracker, active_edge_ids)
    set_agent_stop_reason_func(state)
    sync_checkpoint_metadata_func(state, checkpoint_saver, checkpoint_lookup_config)
    refresh_run_artifacts_func(state, node_outputs, active_edge_ids, started_perf=started_perf)
    if append_snapshot:
        append_run_snapshot_func(
            state,
            snapshot_id=next_run_snapshot_id_func(state, "completed"),
            kind="completed",
            label="Completed",
        )
    save_run_func(state)
    publish_run_event_func(str(state.get("run_id") or ""), "run.completed", {"status": "completed"})
    return state


def finalize_failed_langgraph_state(
    state: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    active_edge_ids: set[str],
    *,
    exc: Exception,
    started_perf: float,
    checkpoint_saver: JsonCheckpointSaver,
    checkpoint_lookup_config: dict[str, Any],
    set_run_status_func: Callable[..., None] = set_run_status,
    set_agent_stop_reason_func: Callable[..., None] = set_agent_stop_reason,
    sync_checkpoint_metadata_func: Callable[..., None] = sync_checkpoint_metadata,
    refresh_run_artifacts_func: Callable[..., None] = refresh_run_artifacts,
    next_run_snapshot_id_func: Callable[..., str] = next_run_snapshot_id,
    append_run_snapshot_func: Callable[..., None] = append_run_snapshot,
    save_run_func: Callable[..., None] = save_run,
    publish_run_event_func: Callable[..., None] = publish_run_event,
) -> dict[str, Any]:
    error = str(exc)
    set_run_status_func(state, "failed")
    state.setdefault("errors", []).append(error)
    set_agent_stop_reason_func(state)
    sync_checkpoint_metadata_func(state, checkpoint_saver, checkpoint_lookup_config)
    refresh_run_artifacts_func(state, node_outputs, active_edge_ids, started_perf=started_perf)
    append_run_snapshot_func(
        state,
        snapshot_id=next_run_snapshot_id_func(state, "failed"),
        kind="failed",
        label="Failed",
    )
    save_run_func(state)
    publish_run_event_func(
        str(state.get("run_id") or ""),
        "run.failed",
        {"status": "failed", "error": error},
    )
    return state


def finalize_cancelled_langgraph_state(
    state: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    active_edge_ids: set[str],
    *,
    reason: str,
    started_perf: float,
    checkpoint_saver: JsonCheckpointSaver,
    checkpoint_lookup_config: dict[str, Any],
    set_run_status_func: Callable[..., None] = set_run_status,
    set_agent_stop_reason_func: Callable[..., None] = set_agent_stop_reason,
    sync_checkpoint_metadata_func: Callable[..., None] = sync_checkpoint_metadata,
    refresh_run_artifacts_func: Callable[..., None] = refresh_run_artifacts,
    next_run_snapshot_id_func: Callable[..., str] = next_run_snapshot_id,
    append_run_snapshot_func: Callable[..., None] = append_run_snapshot,
    save_run_func: Callable[..., None] = save_run,
    publish_run_event_func: Callable[..., None] = publish_run_event,
) -> dict[str, Any]:
    cancellation_reason = str(reason or "").strip() or "Run cancelled by user."
    metadata = dict(state.get("metadata") or {})
    metadata["cancelled"] = True
    metadata["cancellation_requested"] = True
    metadata["cancellation_reason"] = cancellation_reason
    metadata.setdefault("cancelled_at", utc_now_iso())
    state["metadata"] = metadata
    _mark_running_execution_cancelled(state, cancellation_reason)
    set_run_status_func(state, "cancelled")
    set_agent_stop_reason_func(state)
    sync_checkpoint_metadata_func(state, checkpoint_saver, checkpoint_lookup_config)
    refresh_run_artifacts_func(state, node_outputs, active_edge_ids, started_perf=started_perf)
    append_run_snapshot_func(
        state,
        snapshot_id=next_run_snapshot_id_func(state, "cancelled"),
        kind="cancelled",
        label="Cancelled",
    )
    save_run_func(state)
    publish_run_event_func(
        str(state.get("run_id") or ""),
        "run.cancelled",
        {"status": "cancelled", "reason": cancellation_reason},
    )
    return state


def _mark_running_execution_cancelled(state: dict[str, Any], reason: str) -> None:
    current_node_id = str(state.get("current_node_id") or "").strip()
    if not current_node_id:
        return
    execution = find_latest_running_execution(state, current_node_id)
    if execution is None:
        return
    finished_at = utc_now_iso()
    execution["status"] = "cancelled"
    execution["finished_at"] = finished_at
    execution["duration_ms"] = duration_between_iso_ms(execution.get("started_at"), finished_at)
    execution["warnings"] = [*list(execution.get("warnings") or []), reason]
    node_status_map = state.setdefault("node_status_map", {})
    if isinstance(node_status_map, dict):
        node_status_map[current_node_id] = "cancelled"
