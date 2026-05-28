from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOOL_DIR = REPO_ROOT / "tool" / "official" / "delegation_kanban_board_builder"

sys.path.insert(0, str(BACKEND_ROOT))


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("delegation_kanban_board_builder_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load delegation_kanban_board_builder tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DelegationKanbanBoardBuilderToolTests(unittest.TestCase):
    def test_catalog_exposes_delegation_kanban_board_builder_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("delegation_kanban_board_builder")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Delegation Kanban Board Builder")
        self.assertIn("delegation_board_snapshot", definition.description)
        self.assertIn("delegation_kanban_board_builder", get_tool_registry(include_disabled=True).keys())

    def test_builder_projects_worker_results_into_review_and_blocked_columns(self) -> None:
        module = _load_tool_module()

        result = module.delegation_kanban_board_builder(
            {
                "board_id": "hermes_parity_delegation",
                "board_title": "Hermes parity delegation work",
                "worker_task_packets": [
                    {
                        "task_id": "worker_eval_research_1",
                        "goal": "Compare TooGraph and Hermes delegation protocols.",
                        "allowed_capabilities": [{"kind": "tool", "key": "knowledge_context_loader"}],
                        "budget": {"max_steps": 2, "max_chars": 4000},
                        "context_package_refs": [
                            {"source_kind": "context_package", "source_id": "ctx_eval_worker_batch_brief"}
                        ],
                    },
                    {
                        "task_id": "worker_eval_research_2",
                        "goal": "Check fallback behavior for delegation workers.",
                        "allowed_capabilities": [{"kind": "tool", "key": "provider_fallback_resolver"}],
                        "budget": {"max_steps": 2, "max_chars": 4000},
                    },
                ],
                "worker_merge_review_package": {
                    "kind": "worker_merge_review_package",
                    "status": "partial",
                    "summary": "Merged two worker results.",
                    "worker_count": 2,
                    "workers": [
                        {
                            "kind": "worker_result_package",
                            "task_id": "worker_eval_research_1",
                            "status": "succeeded",
                            "summary": "Succeeded after retry.",
                            "outputs": {"findings": {"type": "markdown", "value": "Result after retry."}},
                            "budget": {"max_steps": 2, "used_steps": 2, "attempts": 2},
                            "source_refs": [{"source_kind": "graph_run", "source_id": "run_worker_1"}],
                        },
                        {
                            "kind": "worker_result_package",
                            "task_id": "worker_eval_research_2",
                            "status": "partial",
                            "summary": "Stopped after exhausting worker budget.",
                            "outputs": {},
                            "errors": [{"message": "budget exhausted"}],
                            "budget": {"max_steps": 2, "used_steps": 3, "max_chars": 4000, "used_chars": 4500},
                            "source_refs": [{"source_kind": "graph_run", "source_id": "run_worker_2"}],
                        },
                    ],
                    "review": {
                        "needs_review": True,
                        "risk_flags": [
                            "worker_retried:worker_eval_research_1:2",
                            "worker_budget_exhausted:worker_eval_research_2:max_steps",
                            "worker_budget_exhausted:worker_eval_research_2:max_chars",
                            "worker_partial:worker_eval_research_2",
                        ],
                        "budget_exceeded": [
                            {"task_id": "worker_eval_research_2", "limit": "max_steps", "used": 3, "max": 2}
                        ],
                        "retry_attempts": [{"task_id": "worker_eval_research_1", "attempts": 2}],
                        "recommended_next_action": "tighten_budget_or_split_task",
                    },
                },
            }
        )

        board = result["delegation_board_snapshot"]

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(board["kind"], "delegation_board_snapshot")
        self.assertEqual(board["board_id"], "hermes_parity_delegation")
        self.assertEqual(board["status_counts"], {"blocked": 1, "review": 1})
        self.assertEqual([card["task_id"] for card in board["columns"]["review"]], ["worker_eval_research_1"])
        self.assertEqual([card["task_id"] for card in board["columns"]["blocked"]], ["worker_eval_research_2"])

        review_card = board["cards"][0]
        blocked_card = board["cards"][1]
        self.assertEqual(review_card["lane"], "review")
        self.assertEqual(review_card["worker_status"], "succeeded")
        self.assertEqual(review_card["retry_attempts"], 2)
        self.assertIn("worker_retried:worker_eval_research_1:2", review_card["risk_flags"])
        self.assertEqual(blocked_card["lane"], "blocked")
        self.assertEqual(blocked_card["block_reason"], "budget_exhausted")
        self.assertEqual(blocked_card["recommended_next_action"], "tighten_budget_or_split_task")
        self.assertIn("worker_budget_exhausted:worker_eval_research_2:max_steps", blocked_card["risk_flags"])
        self.assertEqual(
            board["source_refs"],
            [
                {"source_kind": "context_package", "source_id": "ctx_eval_worker_batch_brief"},
                {"source_kind": "graph_run", "source_id": "run_worker_1"},
                {"source_kind": "graph_run", "source_id": "run_worker_2"},
            ],
        )
        self.assertEqual(
            [action["task_id"] for action in board["next_actions"]],
            ["worker_eval_research_2", "worker_eval_research_1"],
        )
        self.assertIn("worker_eval_research_2", result["kanban_board_report"])


if __name__ == "__main__":
    unittest.main()
