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
TOOL_DIR = REPO_ROOT / "tool" / "official" / "buddy_home_context_loader"

sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import database
from app.core.storage.context_assembly_store import expand_context_package


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("buddy_home_context_loader_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load buddy_home_context_loader tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuddyHomeContextLoaderToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._temp_dir.name)
        self.data_dir = self.workspace / "data"
        self.buddy_home = self.workspace / "buddy_home"
        self.buddy_home.mkdir()
        self._patchers = [
            patch("app.core.storage.database.DATA_DIR", self.data_dir),
            patch("app.core.storage.database.DB_PATH", self.data_dir / "toograph.db"),
            patch.dict(
                "os.environ",
                {
                    "TOOGRAPH_BUDDY_HOME": str(self.buddy_home),
                    "TOOGRAPH_REPO_ROOT": str(self.workspace),
                },
            ),
        ]
        for patcher in self._patchers:
            patcher.start()
        database.initialize_storage()
        (self.buddy_home / "AGENTS.md").write_text("Home boundary line.", encoding="utf-8")
        (self.buddy_home / "SOUL.md").write_text("Identity line.", encoding="utf-8")
        (self.buddy_home / "USER.md").write_text("User preference line.", encoding="utf-8")
        (self.buddy_home / "MEMORY.md").write_text("Durable memory line.", encoding="utf-8")

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._temp_dir.cleanup()

    def test_catalog_exposes_buddy_home_context_loader_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("buddy_home_context_loader")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Buddy Home Context Loader")
        self.assertIn("Buddy Home", definition.description)
        self.assertIn("buddy_home_context_loader", get_tool_registry(include_disabled=True).keys())

    def test_loader_outputs_buddy_home_context_package_with_authority_boundaries(self) -> None:
        module = _load_tool_module()

        result = module.buddy_home_context_loader(
            {
                "buddy_home_selection": {
                    "kind": "local_folder",
                    "root": "buddy_home",
                    "selected": ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"],
                },
                "max_chars": 4000,
            }
        )
        package = result["buddy_context"]
        expanded = expand_context_package(package)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(package["kind"], "context_package")
        self.assertEqual(package["source_kind"], "buddy_home")
        self.assertEqual(package["authority"], "context_only")
        self.assertEqual(package["context_ref"]["kind"], "context_assembly_ref")
        self.assertEqual([ref["source_id"] for ref in package["source_refs"]], ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"])
        self.assertEqual(
            [item["metadata"]["authority"] for item in package["items"]],
            ["context_only", "identity", "preference", "preference"],
        )
        self.assertIn("source: AGENTS.md", expanded["text"])
        self.assertIn("authority: context_only", expanded["text"])
        self.assertIn("Identity line.", expanded["text"])
        self.assertIn("User preference line.", expanded["text"])
        self.assertIn("Durable memory line.", expanded["text"])
        self.assertGreater(package["budget"]["used_chars"], 0)
        self.assertEqual(package["budget"]["omitted_count"], 0)
        self.assertEqual(result["buddy_home_context_report"]["selected_files"], ["AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md"])

    def test_context_package_can_rebuild_buddy_home_text_from_source_refs(self) -> None:
        module = _load_tool_module()
        result = module.buddy_home_context_loader(
            {
                "buddy_home_selection": {
                    "kind": "local_folder",
                    "root": "buddy_home",
                    "selected": ["SOUL.md"],
                }
            }
        )
        package = result["buddy_context"]
        first_expanded = expand_context_package(package)

        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute(
                "DELETE FROM content_blobs WHERE content_hash = ?",
                (first_expanded["assembly"]["rendered_content_hash"],),
            )
            connection.commit()
        (self.buddy_home / "SOUL.md").write_text("Updated identity line.", encoding="utf-8")

        rebuilt = expand_context_package(package)

        self.assertIn("Updated identity line.", rebuilt["text"])
        self.assertEqual(rebuilt["package"]["source_kind"], "buddy_home")


if __name__ == "__main__":
    unittest.main()
