from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database
from app.evaluator import store
from app.main import app


@contextmanager
def isolated_eval_database():
    old_data_dir = database.DATA_DIR
    old_db_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir)
        database.DATA_DIR = data_dir
        database.DB_PATH = data_dir / "toograph.db"
        try:
            database.initialize_storage()
            yield
        finally:
            database.DATA_DIR = old_data_dir
            database.DB_PATH = old_db_path


class EvaluatorStoreRouteTests(unittest.TestCase):
    def test_eval_store_records_suite_cases_runs_results_and_checks(self) -> None:
        with isolated_eval_database():
            suite = store.create_eval_suite(
                {
                    "suite_id": "buddy_loop_core",
                    "name": "Buddy loop core",
                    "description": "Core Buddy regression suite.",
                    "target_template_id": "buddy_autonomous_loop",
                    "tags": ["buddy", "capability_loop"],
                    "metadata": {"owner": "product"},
                }
            )
            case = store.create_eval_case(
                "buddy_loop_core",
                {
                    "case_id": "answers_with_citations",
                    "name": "Answers with citations",
                    "input_values": {"input_user_message": "Summarize the cited policy."},
                    "expected": {"must_include": ["citation"]},
                    "checks": [
                        {"kind": "schema", "name": "Final reply schema", "required": ["final_reply"]},
                        {"kind": "citation", "name": "Citation present"},
                    ],
                    "metadata": {"priority": "p0"},
                },
            )
            eval_run = store.create_eval_run("buddy_loop_core", requested_by="unit-test", metadata={"reason": "regression"})
            pending_detail = store.load_eval_run(eval_run["eval_run_id"])

            self.assertEqual(suite["suite_id"], "buddy_loop_core")
            self.assertEqual(case["checks"][1]["kind"], "citation")
            self.assertEqual(pending_detail["case_results"][0]["status"], "pending")
            self.assertEqual(pending_detail["case_results"][0]["case_id"], "answers_with_citations")

            result = store.record_eval_case_result(
                eval_run["eval_run_id"],
                "answers_with_citations",
                {
                    "graph_run_id": "run_graph_123",
                    "status": "failed",
                    "final_output": {"final_reply": "No citation."},
                    "error": "Missing citation.",
                    "artifacts": {"output_path": "backend/data/outputs/run_graph_123/final.md"},
                    "node_failures": [{"node_id": "citation_check", "error": "No citation ids found."}],
                    "check_results": [
                        {"kind": "schema", "name": "Final reply schema", "status": "passed", "score": 1},
                        {
                            "kind": "citation",
                            "name": "Citation present",
                            "status": "failed",
                            "score": 0,
                            "message": "No citation ids found.",
                            "expected": {"min_citations": 1},
                            "actual": {"citations": []},
                        },
                    ],
                    "human_review": {"reviewer": "qa", "decision": "needs_fix"},
                },
            )
            loaded = store.load_eval_run(eval_run["eval_run_id"])

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["graph_run_id"], "run_graph_123")
            self.assertEqual(result["node_failures"][0]["node_id"], "citation_check")
            self.assertEqual([check["status"] for check in result["check_results"]], ["passed", "failed"])
            self.assertEqual(loaded["status"], "failed")
            self.assertEqual(loaded["case_results"][0]["error"], "Missing citation.")
            self.assertEqual(loaded["case_results"][0]["human_review"]["decision"], "needs_fix")
            self.assertEqual(store.list_eval_suites()[0]["case_count"], 1)

    def test_eval_routes_create_and_report_suite_run_results(self) -> None:
        with isolated_eval_database():
            with TestClient(app) as client:
                suite_response = client.post(
                    "/api/evals/suites",
                    json={
                        "suite_id": "template_quality",
                        "name": "Template quality",
                        "target_template_id": "policy_navigator_agent",
                        "tags": ["gallery"],
                    },
                )
                case_response = client.post(
                    "/api/evals/suites/template_quality/cases",
                    json={
                        "case_id": "policy_citation",
                        "name": "Policy citation",
                        "input_values": {"policy_text": "Policy text"},
                        "expected": {"citations": 1},
                        "checks": [{"kind": "citation", "name": "Has citation"}],
                    },
                )
                run_response = client.post(
                    "/api/evals/runs",
                    json={"suite_id": "template_quality", "requested_by": "route-test"},
                )
                eval_run_id = run_response.json()["eval_run_id"]
                result_response = client.post(
                    f"/api/evals/runs/{eval_run_id}/cases/policy_citation/result",
                    json={
                        "graph_run_id": "run_policy_1",
                        "status": "passed",
                        "final_output": {"answer": "Includes [1]."},
                        "artifacts": {"citations": ["kb:policy:1"]},
                        "check_results": [
                            {"kind": "citation", "name": "Has citation", "status": "passed", "score": 1}
                        ],
                    },
                )
                suites_response = client.get("/api/evals/suites")
                run_detail_response = client.get(f"/api/evals/runs/{eval_run_id}")

        self.assertEqual(suite_response.status_code, 200)
        self.assertEqual(case_response.status_code, 200)
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(result_response.status_code, 200)
        self.assertEqual(suites_response.json()[0]["suite_id"], "template_quality")
        self.assertEqual(suites_response.json()[0]["case_count"], 1)
        self.assertEqual(run_detail_response.json()["status"], "passed")
        self.assertEqual(run_detail_response.json()["case_results"][0]["graph_run_id"], "run_policy_1")
        self.assertEqual(run_detail_response.json()["case_results"][0]["check_results"][0]["kind"], "citation")


if __name__ == "__main__":
    unittest.main()
