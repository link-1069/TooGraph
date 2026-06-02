from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.langgraph.compiler import compile_graph_to_langgraph_plan, get_langgraph_runtime_unsupported_reasons
from app.core.langgraph.runtime import execute_node_system_graph_langgraph
from app.core.schemas.node_system import NodeSystemGraphPayload


def _manual_graph() -> NodeSystemGraphPayload:
    return NodeSystemGraphPayload.model_validate(
        {
            "name": "Manual Graph",
            "state_schema": {
                "question": {"name": "Question", "type": "text", "value": "Hello"},
                "answer": {"name": "Answer", "type": "markdown", "value": ""},
            },
            "nodes": {
                "input_question": {
                    "kind": "input",
                    "name": "input_question",
                    "ui": {"position": {"x": 0, "y": 0}},
                    "writes": [{"state": "question"}],
                    "config": {"value": "Hello"},
                },
                "answer_agent": {
                    "kind": "agent",
                    "name": "answer_agent",
                    "ui": {"position": {"x": 240, "y": 0}},
                    "reads": [{"state": "question"}],
                    "writes": [{"state": "answer"}],
                    "config": {"taskInstruction": "Answer briefly."},
                },
                "output_answer": {
                    "kind": "output",
                    "name": "output_answer",
                    "ui": {"position": {"x": 480, "y": 0}},
                    "reads": [{"state": "answer"}],
                },
            },
            "edges": [
                {"source": "input_question", "target": "answer_agent"},
                {"source": "answer_agent", "target": "output_answer"},
            ],
            "conditional_edges": [],
            "metadata": {},
        }
    )


def _input_and_runtime_predecessor_graph() -> NodeSystemGraphPayload:
    return NodeSystemGraphPayload.model_validate(
        {
            "name": "Input And Runtime Predecessor Graph",
            "state_schema": {
                "question": {"name": "Question", "type": "text", "value": "Hello"},
                "context": {"name": "Context", "type": "markdown", "value": ""},
                "answer": {"name": "Answer", "type": "markdown", "value": ""},
            },
            "nodes": {
                "input_question": {
                    "kind": "input",
                    "name": "input_question",
                    "ui": {"position": {"x": 0, "y": 0}},
                    "writes": [{"state": "question"}],
                    "config": {"value": "Hello"},
                },
                "load_context": {
                    "kind": "agent",
                    "name": "load_context",
                    "ui": {"position": {"x": 240, "y": 0}},
                    "reads": [{"state": "question"}],
                    "writes": [{"state": "context"}],
                    "config": {"taskInstruction": "Load context."},
                },
                "answer_agent": {
                    "kind": "agent",
                    "name": "answer_agent",
                    "ui": {"position": {"x": 480, "y": 0}},
                    "reads": [{"state": "question"}, {"state": "context"}],
                    "writes": [{"state": "answer"}],
                    "config": {"taskInstruction": "Answer briefly."},
                },
                "output_answer": {
                    "kind": "output",
                    "name": "output_answer",
                    "ui": {"position": {"x": 720, "y": 0}},
                    "reads": [{"state": "answer"}],
                },
            },
            "edges": [
                {"source": "input_question", "target": "load_context"},
                {"source": "input_question", "target": "answer_agent"},
                {"source": "load_context", "target": "answer_agent"},
                {"source": "answer_agent", "target": "output_answer"},
            ],
            "conditional_edges": [],
            "metadata": {},
        }
    )


def _input_and_loop_predecessor_graph() -> NodeSystemGraphPayload:
    return NodeSystemGraphPayload.model_validate(
        {
            "name": "Input And Loop Predecessor Graph",
            "state_schema": {
                "question": {"name": "Question", "type": "text", "value": "Hello"},
                "should_continue": {"name": "Should Continue", "type": "boolean", "value": False},
                "answer": {"name": "Answer", "type": "markdown", "value": ""},
            },
            "nodes": {
                "input_question": {
                    "kind": "input",
                    "name": "input_question",
                    "ui": {"position": {"x": 0, "y": 0}},
                    "writes": [{"state": "question"}],
                    "config": {"value": "Hello"},
                },
                "answer_agent": {
                    "kind": "agent",
                    "name": "answer_agent",
                    "ui": {"position": {"x": 240, "y": 0}},
                    "reads": [{"state": "question"}],
                    "writes": [{"state": "answer"}, {"state": "should_continue"}],
                    "config": {"taskInstruction": "Answer or continue."},
                },
                "continue_condition": {
                    "kind": "condition",
                    "name": "continue_condition",
                    "ui": {"position": {"x": 480, "y": 0}},
                    "reads": [{"state": "should_continue"}],
                    "config": {
                        "branches": ["true", "false", "exhausted"],
                        "branchMapping": {"true": "true", "false": "false"},
                        "rule": {"source": "$state.should_continue", "operator": "==", "value": True},
                    },
                },
                "loop_agent": {
                    "kind": "agent",
                    "name": "loop_agent",
                    "ui": {"position": {"x": 720, "y": 0}},
                    "reads": [{"state": "answer"}],
                    "writes": [{"state": "answer"}],
                    "config": {"taskInstruction": "Improve answer."},
                },
                "output_answer": {
                    "kind": "output",
                    "name": "output_answer",
                    "ui": {"position": {"x": 960, "y": 0}},
                    "reads": [{"state": "answer"}],
                },
            },
            "edges": [
                {"source": "input_question", "target": "answer_agent"},
                {"source": "answer_agent", "target": "continue_condition"},
                {"source": "loop_agent", "target": "answer_agent"},
            ],
            "conditional_edges": [
                {
                    "source": "continue_condition",
                    "branches": {"true": "loop_agent", "false": "output_answer", "exhausted": "output_answer"},
                }
            ],
            "metadata": {},
        }
    )


class LangGraphMigrationTests(unittest.TestCase):
    def test_manual_graph_validates_and_builds_runtime_plan_without_builtin_templates(self) -> None:
        graph = _manual_graph()

        unsupported_reasons = get_langgraph_runtime_unsupported_reasons(graph)
        plan = compile_graph_to_langgraph_plan(graph)

        self.assertEqual(unsupported_reasons, [])
        self.assertEqual(list(plan.nodes), ["input_question", "answer_agent", "output_answer"])
        self.assertEqual([(edge.source, edge.target) for edge in plan.edges], [("input_question", "answer_agent"), ("answer_agent", "output_answer")])

    def test_input_edge_does_not_start_runtime_node_before_acyclic_runtime_predecessor(self) -> None:
        plan = compile_graph_to_langgraph_plan(_input_and_runtime_predecessor_graph())

        self.assertEqual(plan.requirements.runtime_entry_nodes, ["load_context"])

    def test_input_edge_still_starts_runtime_node_with_only_loop_predecessors(self) -> None:
        plan = compile_graph_to_langgraph_plan(_input_and_loop_predecessor_graph())

        self.assertEqual(plan.requirements.runtime_entry_nodes, ["answer_agent"])

    def test_runtime_does_not_execute_input_candidate_after_acyclic_runtime_predecessor_twice(self) -> None:
        graph = _input_and_runtime_predecessor_graph()

        with patch("app.core.runtime.node_system_executor.chat_with_model_ref_with_meta") as chat, patch(
            "app.core.runtime.node_system_executor._chat_with_local_model_with_meta"
        ) as local_chat:
            chat.return_value = ('{"context":"loaded context","answer":"single answer"}', {"warnings": [], "model": "test"})
            local_chat.return_value = ('{"context":"loaded context","answer":"single answer"}', {"warnings": [], "model": "test"})
            result = execute_node_system_graph_langgraph(
                graph,
                {"run_id": "run_single_answer", "status": "running"},
                save_final_run=False,
                emit_lifecycle_events=False,
            )

        answer_executions = [
            execution
            for execution in result["node_executions"]
            if execution["node_id"] == "answer_agent"
        ]
        self.assertEqual(len(answer_executions), 1)


if __name__ == "__main__":
    unittest.main()
