from __future__ import annotations

import copy
from typing import Any

from app.core.runtime.output_artifacts import (
    apply_loop_limit_exhausted_output_message,
    resolve_active_output_nodes,
)
from app.core.runtime.output_boundary_utils import save_output_value
from app.core.schemas.node_system import NodeSystemGraphDocument, NodeSystemOutputNode


def execute_output_node(
    node_name: str,
    node: NodeSystemOutputNode,
    input_values: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    binding = node.reads[0]
    raw_value = input_values.get(binding.state)
    resolved = resolve_output_preview_value(
        binding.state,
        raw_value,
        configured_display_mode=node.config.display_mode.value,
    )
    value = resolved["value"]
    preview = {
        "node_id": node_name,
        "label": resolved["label"],
        "source_kind": "state",
        "source_key": resolved["source_key"],
        "display_mode": resolved["display_mode"],
        "persist_enabled": node.config.persist_enabled,
        "persist_format": node.config.persist_format.value,
        "value": value,
    }
    saved_outputs: list[dict[str, Any]] = []
    if node.config.persist_enabled:
        fallback_file_name_template = node.config.file_name_template or (
            "" if is_result_package_value(raw_value) else resolved["file_name_template"]
        )
        for persist_item in list_output_persistence_values(
            binding.state,
            raw_value,
            fallback_source_key=resolved["source_key"],
            fallback_file_name_template=fallback_file_name_template,
            fallback_value=value,
        ):
            if persist_item["value"] in (None, "", [], {}):
                continue
            saved_outputs.append(
                save_output_value(
                    run_id=str(state.get("run_id", "")),
                    node_id=node_name,
                    source_key=persist_item["source_key"],
                    value=persist_item["value"],
                    persist_format=node.config.persist_format.value,
                    file_name_template=persist_item["file_name_template"],
                )
            )
    return {
        "outputs": {binding.state: value},
        "output_previews": [preview],
        "saved_outputs": saved_outputs,
        "final_result": "" if value is None else str(value),
    }


def list_output_persistence_values(
    state_key: str,
    value: Any,
    *,
    fallback_source_key: str,
    fallback_file_name_template: str,
    fallback_value: Any,
) -> list[dict[str, Any]]:
    if not is_result_package_value(value):
        return [
            {
                "source_key": fallback_source_key,
                "file_name_template": fallback_file_name_template,
                "value": fallback_value,
            }
        ]

    outputs = value.get("outputs")
    if not isinstance(outputs, dict):
        return []

    items: list[dict[str, Any]] = []
    for output_key, raw_output in outputs.items():
        output_key_text = str(output_key or "").strip()
        if not output_key_text:
            continue
        output_value = raw_output.get("value") if isinstance(raw_output, dict) else raw_output
        items.append(
            {
                "source_key": f"{state_key}.{output_key_text}",
                "file_name_template": resolve_result_package_file_name_template(
                    fallback_file_name_template,
                    output_key_text,
                ),
                "value": output_value,
            }
        )
    return items


def resolve_result_package_file_name_template(file_name_template: str, output_key: str) -> str:
    template = str(file_name_template or "").strip()
    if not template or template == output_key:
        return output_key
    return f"{template}_{output_key}"


def is_result_package_value(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "result_package" and isinstance(value.get("outputs"), dict)


def resolve_output_preview_value(
    state_key: str,
    value: Any,
    *,
    configured_display_mode: str,
) -> dict[str, Any]:
    fallback = {
        "label": state_key,
        "source_key": state_key,
        "display_mode": configured_display_mode,
        "file_name_template": state_key,
        "value": value,
    }
    return fallback


def collect_output_boundaries(
    graph: NodeSystemGraphDocument,
    state: dict[str, Any],
    active_edge_ids: set[str] | None = None,
) -> None:
    edge_ids = set(active_edge_ids or set())
    selected_output_nodes = resolve_active_output_nodes(graph, edge_ids)
    output_node_names = {
        node_name
        for node_name, node in graph.nodes.items()
        if isinstance(node, NodeSystemOutputNode)
    }
    refreshed_output_nodes = selected_output_nodes if edge_ids else output_node_names
    state["output_previews"] = [
        preview
        for preview in state.get("output_previews", [])
        if preview.get("node_id") not in refreshed_output_nodes
    ]
    state["saved_outputs"] = [
        output
        for output in state.get("saved_outputs", [])
        if output.get("node_id") not in refreshed_output_nodes
    ]
    final_results: list[Any] = []

    for node_name, node in graph.nodes.items():
        if not isinstance(node, NodeSystemOutputNode) or not node.reads:
            continue
        if edge_ids and node_name not in selected_output_nodes:
            continue

        binding = node.reads[0]
        body = execute_output_node(
            node_name,
            node,
            {binding.state: copy.deepcopy(state.get("state_values", {}).get(binding.state))},
            state,
        )
        if state.get("loop_limit_exhaustion"):
            body = apply_loop_limit_exhausted_output_message(body)
        state["output_previews"] = [*state.get("output_previews", []), *body.get("output_previews", [])]
        state["saved_outputs"] = [*state.get("saved_outputs", []), *body.get("saved_outputs", [])]
        state.setdefault("node_status_map", {})[node_name] = "success"
        if body.get("final_result") not in (None, "", [], {}):
            final_results.append(body["final_result"])

    if final_results:
        state["final_result"] = str(final_results[-1])
