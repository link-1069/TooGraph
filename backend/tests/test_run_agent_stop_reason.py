from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.runtime.agent_stop_reason import resolve_agent_stop_reason, set_agent_stop_reason


def test_resolve_agent_stop_reason_prefers_explicit_graph_state() -> None:
    run_state = {
        "status": "completed",
        "state_values": {"agent_loop_stop_reason": "capability_budget_exhausted"},
        "cycle_summary": {"stop_reason": "completed"},
    }

    assert resolve_agent_stop_reason(run_state) == "capability_budget_exhausted"


def test_resolve_agent_stop_reason_maps_cycle_limit() -> None:
    run_state = {
        "status": "completed",
        "state_values": {},
        "cycle_summary": {"stop_reason": "max_iterations_exceeded"},
    }

    assert resolve_agent_stop_reason(run_state) == "max_iterations_reached"


def test_resolve_agent_stop_reason_maps_permission_metadata() -> None:
    run_state = {
        "status": "awaiting_human",
        "metadata": {"pending_permission_approval": {"capability_key": "write_file"}},
    }

    assert resolve_agent_stop_reason(run_state) == "permission_required"


def test_resolve_agent_stop_reason_classifies_provider_and_graph_failures() -> None:
    provider_state = {"status": "failed", "errors": ["OpenAI provider timeout while calling model"]}
    graph_state = {"status": "failed", "errors": ["Graph validation failed: missing node"]}

    assert resolve_agent_stop_reason(provider_state) == "provider_failed"
    assert resolve_agent_stop_reason(graph_state) == "graph_validation_failed"


def test_set_agent_stop_reason_stores_value_on_run_state() -> None:
    run_state = {"status": "completed", "state_values": {}}

    set_agent_stop_reason(run_state)

    assert run_state["stop_reason"] == "completed"
