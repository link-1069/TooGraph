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
TOOL_DIR = REPO_ROOT / "tool" / "official" / "capability_context_loader"

sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import database
from app.core.storage.context_assembly_store import expand_context_package


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("capability_context_loader_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load capability_context_loader tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapabilityContextLoaderToolTests(unittest.TestCase):
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

    def test_catalog_exposes_capability_context_loader_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("capability_context_loader")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Capability Context Loader")
        self.assertIn("context_package", definition.description)
        self.assertIn("capability_context_loader", get_tool_registry(include_disabled=True).keys())

    def test_loader_outputs_capability_context_package_from_result_package(self) -> None:
        module = _load_tool_module()

        result = module.capability_context_loader(
            {
                "result_package": _result_package("Original capability answer."),
                "run_id": "run_capability_1",
                "state_key": "capability_result",
                "max_chars": 4000,
            }
        )
        package = result["capability_context"]
        expanded = expand_context_package(package)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(package["kind"], "context_package")
        self.assertEqual(package["source_kind"], "capability")
        self.assertEqual(package["authority"], "evidence")
        self.assertEqual(package["context_ref"]["kind"], "context_assembly_ref")
        self.assertEqual(package["items"][0]["source_ref"]["source_kind"], "capability_result_output")
        self.assertEqual(package["items"][0]["metadata"]["source_type"], "action")
        self.assertEqual(package["items"][0]["metadata"]["source_key"], "buddy_session_recall")
        self.assertEqual(package["items"][0]["metadata"]["output_key"], "answer")
        self.assertIn("Capability: Buddy Session Recall", expanded["text"])
        self.assertIn("output: answer", expanded["text"])
        self.assertIn("Original capability answer.", expanded["text"])
        self.assertEqual(result["capability_context_report"]["source_type"], "action")
        self.assertEqual(result["capability_context_report"]["source_key"], "buddy_session_recall")
        self.assertGreater(package["budget"]["used_chars"], 0)
        self.assertEqual(package["budget"]["omitted_count"], 0)

    def test_context_package_rebuilds_capability_output_from_run_state(self) -> None:
        module = _load_tool_module()
        run_id = "run_capability_rebuild"
        state_key = "capability_result"
        self._insert_run_state(run_id, {state_key: _result_package("Original persisted answer.")})

        result = module.capability_context_loader(
            {
                "result_package": _result_package("Original persisted answer."),
                "run_id": run_id,
                "state_key": state_key,
            }
        )
        package = result["capability_context"]
        first_expanded = expand_context_package(package)

        self._delete_blob(first_expanded["assembly"]["rendered_content_hash"])
        self._update_run_state(run_id, {state_key: _result_package("Updated answer from graph run state.")})

        rebuilt = expand_context_package(package)

        self.assertIn("Updated answer from graph run state.", rebuilt["text"])
        self.assertEqual(rebuilt["package"]["source_kind"], "capability")

    def _insert_run_state(self, run_id: str, state_values: dict[str, object]) -> None:
        now = "2026-05-27T00:00:00Z"
        detail_json = json.dumps({"state_values": state_values}, ensure_ascii=False)
        with sqlite3.connect(database.DB_PATH) as connection:
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
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, '', ?, ?, ?)
                """,
                (run_id, run_id, "Capability test", "completed", "test", now, detail_json, now, now),
            )
            connection.commit()

    def _update_run_state(self, run_id: str, state_values: dict[str, object]) -> None:
        detail_json = json.dumps({"state_values": state_values}, ensure_ascii=False)
        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute("UPDATE graph_runs SET detail_json = ? WHERE run_id = ?", (detail_json, run_id))
            connection.commit()

    def _delete_blob(self, content_hash: str) -> None:
        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute("DELETE FROM content_blobs WHERE content_hash = ?", (content_hash,))
            connection.commit()


def _result_package(answer: str) -> dict[str, object]:
    return {
        "kind": "result_package",
        "sourceType": "action",
        "sourceKey": "buddy_session_recall",
        "sourceName": "Buddy Session Recall",
        "status": "succeeded",
        "outputs": {
            "answer": {
                "name": "Answer",
                "description": "Capability answer.",
                "type": "markdown",
                "value": answer,
            },
            "evidence": {
                "name": "Evidence",
                "description": "Structured evidence.",
                "type": "json",
                "value": {"citations": ["kb:1"]},
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
