from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOOL_DIR = REPO_ROOT / "tool" / "official" / "capability_curator_context_loader"

sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import database


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("capability_curator_context_loader_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load capability_curator_context_loader tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapabilityCuratorContextLoaderToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self._temp_dir.name) / "data"
        self._patchers = [
            patch("app.core.storage.database.DATA_DIR", data_dir),
            patch("app.core.storage.database.DB_PATH", data_dir / "toograph.db"),
            patch.dict("os.environ", {"TOOGRAPH_REPO_ROOT": str(REPO_ROOT)}),
        ]
        for patcher in self._patchers:
            patcher.start()
        database.initialize_storage()

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._temp_dir.cleanup()

    def test_catalog_exposes_capability_curator_context_loader_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("capability_curator_context_loader")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Capability Curator Context Loader")
        self.assertIn("capability catalog", definition.description)
        self.assertIn("capability_curator_context_loader", get_tool_registry(include_disabled=True).keys())

    def test_loader_builds_catalog_usage_eval_and_candidate_snapshots(self) -> None:
        module = _load_tool_module()
        self._insert_usage_event(
            run_id="run_usage_1",
            capability_kind="action",
            capability_key="web_search",
            status="failed",
            error_type="network_error",
            summary="Search failed once.",
        )
        from app.buddy import store

        store.upsert_improvement_candidates_for_review(
            {
                "review_id": "review_1",
                "source_run_id": "run_source_1",
                "review_run_id": "run_review_1",
            },
            [
                {
                    "candidate_id": "candidate_curator_1",
                    "kind": "action_revision",
                    "status": "waiting_for_approval",
                    "target_ref": {"kind": "action", "key": "web_search"},
                    "evidence_refs": [{"source_kind": "capability_usage_event", "source_id": "event_1"}],
                    "risk_level": "medium",
                    "expected_benefit": "Reduce repeated search failures.",
                    "proposed_change_summary": "Improve web_search failure handling.",
                    "approval_required": True,
                }
            ],
        )

        result = module.capability_curator_context_loader(
            {
                "curator_scope": {
                    "lookback_days": 7,
                    "candidate_limit": 10,
                    "include_official": True,
                    "include_user": True,
                }
            }
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["curator_scope"]["lookback_days"], 7)
        catalog = result["capability_catalog_snapshot"]
        self.assertEqual(catalog["kind"], "capability_catalog_snapshot")
        self.assertGreater(catalog["counts"]["actions"], 0)
        self.assertGreater(catalog["counts"]["tools"], 0)
        self.assertGreater(catalog["counts"]["templates"], 0)
        self.assertIn("web_search", {item["key"] for item in catalog["actions"]})
        self.assertIn("agent_loop_guard", {item["key"] for item in catalog["tools"]})
        self.assertIn("buddy_capability_curator", {item["key"] for item in catalog["templates"]})
        usage = result["capability_usage_snapshot"]
        self.assertEqual(usage["kind"], "capability_usage_snapshot")
        self.assertEqual(usage["counts"]["events"], 1)
        self.assertEqual(usage["by_capability"]["action:web_search"]["failure_count"], 1)
        self.assertEqual(usage["events"][0]["error_type"], "network_error")
        candidates = result["existing_candidates_snapshot"]
        self.assertEqual(candidates["kind"], "existing_candidates_snapshot")
        self.assertEqual(candidates["counts"]["total"], 1)
        self.assertEqual(candidates["counts_by_status"], {"waiting_for_approval": 1})
        self.assertEqual(candidates["candidates"][0]["candidate_id"], "candidate_curator_1")
        report = result["curator_context_report"]
        self.assertEqual(report["scope"], "capability_curator")
        self.assertEqual(report["source_counts"]["usage_events"], 1)
        self.assertEqual(report["source_counts"]["existing_candidates"], 1)

    def _insert_usage_event(
        self,
        *,
        run_id: str,
        capability_kind: str,
        capability_key: str,
        status: str,
        error_type: str,
        summary: str,
    ) -> None:
        connection = sqlite3.connect(database.DB_PATH)
        try:
            connection.execute(
                """
                INSERT INTO graph_runs (
                    run_id,
                    root_run_id,
                    graph_id,
                    graph_name,
                    status,
                    runtime_backend,
                    started_at,
                    final_result,
                    detail_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, '', '{}', ?, ?)
                """,
                (
                    run_id,
                    run_id,
                    "Usage source",
                    "completed",
                    "test",
                    "2026-05-27T00:00:00Z",
                    "2026-05-27T00:00:00Z",
                    "2026-05-27T00:00:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO capability_usage_events (
                    event_id,
                    invocation_id,
                    run_id,
                    node_id,
                    capability_kind,
                    capability_key,
                    selected_reason,
                    status,
                    latency_ms,
                    error_type,
                    error_message,
                    permission_result,
                    summary,
                    detail_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event_1",
                    "invocation_1",
                    run_id,
                    "node_capability",
                    capability_kind,
                    capability_key,
                    "selected for test",
                    status,
                    123,
                    error_type,
                    "network unavailable",
                    "",
                    summary,
                    json.dumps({"source": "test"}, ensure_ascii=False),
                    "2026-05-27T00:00:01Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
