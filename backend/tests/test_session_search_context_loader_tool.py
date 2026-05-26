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
TOOL_DIR = REPO_ROOT / "tool" / "official" / "session_search_context_loader"

sys.path.insert(0, str(BACKEND_ROOT))

from app.buddy import store
from app.core.storage import database
from app.core.storage.context_assembly_store import expand_context_package


def _load_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("session_search_context_loader_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load session_search_context_loader tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SessionSearchContextLoaderToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._temp_dir.name) / "data"
        self._buddy_home_dir = Path(self._temp_dir.name) / "buddy_home"
        self._patchers = [
            patch("app.core.storage.database.DATA_DIR", self._data_dir),
            patch("app.core.storage.database.DB_PATH", self._data_dir / "toograph.db"),
            patch.object(store, "BUDDY_HOME_DIR", self._buddy_home_dir),
            patch.dict("os.environ", {"TOOGRAPH_REPO_ROOT": str(REPO_ROOT)}),
        ]
        for patcher in self._patchers:
            patcher.start()
        database.initialize_storage()

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._temp_dir.cleanup()

    def test_catalog_exposes_session_search_context_loader_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("session_search_context_loader")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Session Search Context Loader")
        self.assertIn("context_package", definition.description)
        self.assertIn("session_search_context_loader", get_tool_registry(include_disabled=True).keys())

    def test_loader_outputs_search_context_package_from_buddy_messages(self) -> None:
        module = _load_tool_module()
        current_session = store.create_chat_session({"title": "当前会话"}, changed_by="user", change_reason="测试创建")
        current_message = store.append_chat_message(
            current_session["session_id"],
            {"role": "user", "content": "当前会话也提到 session-search-evidence。"},
            changed_by="user",
            change_reason="测试追加",
        )
        recalled_session = store.create_chat_session({"title": "历史会话"}, changed_by="user", change_reason="测试创建")
        store.append_chat_message(
            recalled_session["session_id"],
            {"role": "user", "content": "我们讨论过 session-search-evidence 的事实源。", "client_order": 0},
            changed_by="user",
            change_reason="测试追加",
        )
        assistant_message = store.append_chat_message(
            recalled_session["session_id"],
            {"role": "assistant", "content": "历史搜索应该返回 message ids、snippet 和 session lineage。", "client_order": 1},
            changed_by="buddy",
            change_reason="测试追加",
        )

        result = module.session_search_context_loader(
            {
                "query": "session-search-evidence",
                "limit": 5,
                "window": 1,
                "bookend": 0,
                "current_session_id": current_session["session_id"],
            }
        )
        package = result["session_search_context"]
        expanded = expand_context_package(package)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(package["kind"], "context_package")
        self.assertEqual(package["source_kind"], "session")
        self.assertEqual(package["authority"], "history")
        self.assertEqual(package["context_ref"]["kind"], "context_assembly_ref")
        self.assertEqual(package["items"][0]["source_ref"]["source_kind"], "buddy_message")
        self.assertIn("session-search-evidence", expanded["text"])
        self.assertIn("历史搜索应该返回 message ids", expanded["text"])
        self.assertNotIn(current_message["content"], expanded["text"])
        self.assertEqual(result["session_search_report"]["query"], "session-search-evidence")
        self.assertEqual(result["session_search_report"]["session_count"], 1)
        self.assertIn(assistant_message["message_id"], result["session_search_report"]["message_ids"])

    def test_context_package_rebuilds_search_context_from_message_rows(self) -> None:
        module = _load_tool_module()
        session = store.create_chat_session({"title": "历史会话"}, changed_by="user", change_reason="测试创建")
        message = store.append_chat_message(
            session["session_id"],
            {"role": "user", "content": "原始历史搜索文本。"},
            changed_by="user",
            change_reason="测试追加",
        )

        result = module.session_search_context_loader({"query": "原始历史搜索文本", "limit": 5, "window": 0})
        package = result["session_search_context"]
        first_expanded = expand_context_package(package)

        self._delete_blob(first_expanded["assembly"]["rendered_content_hash"])
        self._update_message(message["message_id"], "更新后的历史搜索文本。")

        rebuilt = expand_context_package(package)

        self.assertIn("更新后的历史搜索文本。", rebuilt["text"])
        self.assertEqual(rebuilt["package"]["source_kind"], "session")

    def _delete_blob(self, content_hash: str) -> None:
        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute("DELETE FROM content_blobs WHERE content_hash = ?", (content_hash,))
            connection.commit()

    def _update_message(self, message_id: str, content: str) -> None:
        with sqlite3.connect(database.DB_PATH) as connection:
            connection.execute("UPDATE buddy_messages SET content = ? WHERE message_id = ?", (content, message_id))
            connection.commit()


if __name__ == "__main__":
    unittest.main()
