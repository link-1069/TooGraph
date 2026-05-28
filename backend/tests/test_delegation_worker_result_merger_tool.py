from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOOL_DIR = REPO_ROOT / "tool" / "official" / "delegation_worker_result_merger"

sys.path.insert(0, str(BACKEND_ROOT))


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("delegation_worker_result_merger_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load delegation_worker_result_merger tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DelegationWorkerResultMergerToolTests(unittest.TestCase):
    def test_catalog_exposes_delegation_worker_result_merger_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("delegation_worker_result_merger")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Delegation Worker Result Merger")
        self.assertIn("worker_result_package", definition.description)
        self.assertIn("delegation_worker_result_merger", get_tool_registry(include_disabled=True).keys())

    def test_merger_outputs_partial_review_package_with_worker_links_and_budget(self) -> None:
        module = _load_tool_module()

        result = module.delegation_worker_result_merger(
            {
                "worker_result_packages": [
                    {
                        "kind": "worker_result_package",
                        "task_id": "research_1",
                        "status": "succeeded",
                        "summary": "Found the worker protocol.",
                        "outputs": {
                            "findings": {
                                "name": "Findings",
                                "type": "markdown",
                                "value": "Use worker_task_packet and worker_result_package.",
                                "source_refs": [
                                    {"source_kind": "graph_run", "source_id": "run_worker_1"}
                                ],
                            }
                        },
                        "artifacts": [{"path": "artifacts/research.md", "kind": "markdown"}],
                        "source_refs": [{"source_kind": "graph_run", "source_id": "run_worker_1"}],
                        "budget": {"max_steps": 5, "used_steps": 3},
                    },
                    {
                        "kind": "worker_result_package",
                        "task_id": "research_2",
                        "status": "failed",
                        "summary": "Provider failed before output.",
                        "outputs": {},
                        "errors": [{"message": "provider unavailable"}],
                        "followups": [{"task_id": "retry_research_2", "goal": "Retry with fallback provider"}],
                        "source_refs": [{"source_kind": "graph_run", "source_id": "run_worker_2"}],
                        "budget": {"max_steps": 5, "used_steps": 2},
                    },
                ],
                "merge_goal": "Merge worker findings for Hermes parity review.",
                "expected_output_schema": {"findings": {"type": "markdown"}},
                "review_policy": {"require_all_succeeded": True},
            }
        )

        package = result["worker_merge_review_package"]

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(package["kind"], "worker_merge_review_package")
        self.assertEqual(package["status"], "partial")
        self.assertEqual(package["worker_count"], 2)
        self.assertEqual(package["status_counts"], {"failed": 1, "succeeded": 1})
        self.assertEqual(package["budget"]["max_steps"], 10)
        self.assertEqual(package["budget"]["used_steps"], 5)
        self.assertEqual(
            package["worker_runs"],
            [
                {"run_id": "run_worker_1", "task_id": "research_1"},
                {"run_id": "run_worker_2", "task_id": "research_2"},
            ],
        )
        self.assertEqual(package["outputs"]["findings"]["type"], "markdown")
        self.assertEqual(package["outputs"]["findings"]["values"][0]["task_id"], "research_1")
        self.assertEqual(package["artifacts"][0]["task_id"], "research_1")
        self.assertEqual(package["errors"][0]["task_id"], "research_2")
        self.assertIn("worker_failed:research_2", package["review"]["risk_flags"])
        self.assertEqual(package["review"]["recommended_next_action"], "retry_failed_workers")
        self.assertIn("research_1", result["merge_review_report"])
        self.assertIn("research_2", result["merge_review_report"])

    def test_merger_marks_missing_required_output_for_review(self) -> None:
        module = _load_tool_module()

        result = module.delegation_worker_result_merger(
            {
                "worker_result_packages": [
                    {
                        "kind": "worker_result_package",
                        "task_id": "draft_1",
                        "status": "succeeded",
                        "summary": "Returned only notes.",
                        "outputs": {"notes": {"type": "markdown", "value": "No final answer."}},
                    }
                ],
                "expected_output_schema": {"final_answer": {"type": "markdown"}},
                "review_policy": {"require_outputs": ["final_answer"]},
            }
        )

        package = result["worker_merge_review_package"]

        self.assertEqual(package["status"], "succeeded")
        self.assertIn("missing_required_output:final_answer", package["review"]["risk_flags"])
        self.assertEqual(package["review"]["recommended_next_action"], "provide_more_context")

    def test_merger_flags_budget_exhaustion_and_retry_attempts(self) -> None:
        module = _load_tool_module()

        result = module.delegation_worker_result_merger(
            {
                "worker_result_packages": [
                    {
                        "kind": "worker_result_package",
                        "task_id": "budgeted_research_1",
                        "status": "succeeded",
                        "summary": "Succeeded after retry.",
                        "outputs": {"findings": {"type": "markdown", "value": "Result after retry."}},
                        "budget": {"max_steps": 2, "used_steps": 2, "attempts": 2},
                    },
                    {
                        "kind": "worker_result_package",
                        "task_id": "budgeted_research_2",
                        "status": "partial",
                        "summary": "Stopped after exhausting worker budget.",
                        "outputs": {},
                        "errors": [{"message": "budget exhausted"}],
                        "budget": {"max_steps": 2, "used_steps": 3, "max_chars": 4000, "used_chars": 4500},
                    },
                ],
                "expected_output_schema": {"findings": {"type": "markdown"}},
                "review_policy": {"require_all_succeeded": True},
            }
        )

        package = result["worker_merge_review_package"]
        review = package["review"]

        self.assertEqual(package["status"], "partial")
        self.assertEqual(package["budget"]["max_steps"], 4)
        self.assertEqual(package["budget"]["used_steps"], 5)
        self.assertEqual(
            review["budget_exceeded"],
            [
                {"task_id": "budgeted_research_2", "limit": "max_chars", "used": 4500, "max": 4000},
                {"task_id": "budgeted_research_2", "limit": "max_steps", "used": 3, "max": 2},
            ],
        )
        self.assertEqual(review["retry_attempts"], [{"task_id": "budgeted_research_1", "attempts": 2}])
        self.assertIn("worker_budget_exhausted:budgeted_research_2:max_steps", review["risk_flags"])
        self.assertIn("worker_budget_exhausted:budgeted_research_2:max_chars", review["risk_flags"])
        self.assertIn("worker_retried:budgeted_research_1:2", review["risk_flags"])
        self.assertEqual(review["recommended_next_action"], "tighten_budget_or_split_task")


if __name__ == "__main__":
    unittest.main()
