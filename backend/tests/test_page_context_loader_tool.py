from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOOL_DIR = REPO_ROOT / "tool" / "official" / "page_context_loader"

sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import database
from app.core.storage.context_assembly_store import expand_context_package


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("page_context_loader_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load page_context_loader tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PageContextLoaderToolTests(unittest.TestCase):
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

    def test_catalog_exposes_page_context_loader_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("page_context_loader")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Page Context Loader")
        self.assertIn("context_package", definition.description)
        self.assertIn("page_context_loader", get_tool_registry(include_disabled=True).keys())

    def test_loader_outputs_page_context_package_from_page_operation_context(self) -> None:
        module = _load_tool_module()

        result = module.page_context_loader(
            {
                "page_operation_context": _page_operation_context(),
                "page_context": "当前页面有 2 个可操作目标。",
                "source_run_id": "run_page_1",
                "max_chars": 4000,
            }
        )
        package = result["page_context_package"]
        expanded = expand_context_package(package)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(package["kind"], "context_package")
        self.assertEqual(package["source_kind"], "page")
        self.assertEqual(package["authority"], "context_only")
        self.assertEqual(package["context_ref"]["kind"], "context_assembly_ref")
        self.assertEqual(package["items"][0]["source_ref"]["source_kind"], "page_context_item")
        self.assertIn("Page: 图编辑器", expanded["text"])
        self.assertIn("path: /editor", expanded["text"])
        self.assertIn("click app.nav.runs", expanded["text"])
        self.assertIn("editor.search.query", expanded["text"])
        self.assertIn("当前页面有 2 个可操作目标。", expanded["text"])
        self.assertEqual(result["page_context_report"]["run_id"], "run_page_1")
        self.assertGreaterEqual(result["page_context_report"]["source_count"], 4)
        self.assertEqual(package["budget"]["omitted_count"], 0)

    def test_context_package_rebuilds_page_context_from_source_blobs(self) -> None:
        module = _load_tool_module()

        result = module.page_context_loader(
            {
                "page_operation_context": _page_operation_context(),
                "source_run_id": "run_page_rebuild",
            }
        )
        package = result["page_context_package"]
        first_expanded = expand_context_package(package)

        self._delete_blob(first_expanded["assembly"]["rendered_content_hash"])

        rebuilt = expand_context_package(package)

        self.assertIn("Page: 图编辑器", rebuilt["text"])
        self.assertIn("click app.nav.runs", rebuilt["text"])
        self.assertEqual(rebuilt["package"]["source_kind"], "page")

    def _delete_blob(self, content_hash: str) -> None:
        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute("DELETE FROM content_blobs WHERE content_hash = ?", (content_hash,))
            connection.commit()


def _page_operation_context() -> dict[str, object]:
    return {
        "page_path": "/editor",
        "page_operation_book": {
            "page": {
                "path": "/editor",
                "title": "图编辑器",
                "snapshotId": "snapshot_1",
            },
            "allowedOperations": [
                {
                    "targetId": "app.nav.runs",
                    "label": "运行历史",
                    "role": "navigation",
                    "commands": ["click app.nav.runs"],
                }
            ],
            "inputs": [
                {
                    "targetId": "editor.search.query",
                    "label": "搜索框",
                    "commands": ["focus editor.search.query", "type editor.search.query <text>"],
                }
            ],
        },
        "page_facts": {
            "latestForegroundRun": {
                "runId": "run_foreground",
                "status": "completed",
                "resultSummary": "最近一次运行完成。",
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
