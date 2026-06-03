from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database


class RetrievalToolingCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self._temp_dir.name) / "data"
        self._patchers = [
            patch("app.core.storage.database.DATA_DIR", data_dir),
            patch("app.core.storage.database.DB_PATH", data_dir / "toograph.db"),
        ]
        for patcher in self._patchers:
            patcher.start()
        database.initialize_storage()

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._temp_dir.cleanup()

    def test_tool_catalog_uses_only_new_retrieval_tools_for_ingestion_and_query(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog_keys = {tool.tool_key for tool in list_tool_catalog(include_disabled=True)}
        registry_keys = set(get_tool_registry(include_disabled=True).keys())

        self.assertIn("source_chunker", catalog_keys)
        self.assertIn("retrieval_ingestion_writer", catalog_keys)
        self.assertIn("retrieval_query_context_loader", catalog_keys)
        self.assertIn("embedding_job_processor", catalog_keys)
        self.assertIn("embedding_model_registry", catalog_keys)
        self.assertNotIn("knowledge_context_loader", catalog_keys)
        self.assertNotIn("session_search_context_loader", catalog_keys)
        self.assertNotIn("memory_search_context_loader", catalog_keys)
        self.assertNotIn("hybrid_recall_context_loader", catalog_keys)
        self.assertIn("retrieval_ingestion_writer", registry_keys)
        self.assertIn("retrieval_query_context_loader", registry_keys)

    def test_new_storage_schema_does_not_create_legacy_knowledge_tables(self) -> None:
        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }

        self.assertNotIn("knowledge_bases", table_names)
        self.assertNotIn("knowledge_documents", table_names)
        self.assertNotIn("knowledge_chunks", table_names)
        self.assertNotIn("knowledge_chunk_embeddings", table_names)
        self.assertNotIn("knowledge_chunks_fts", table_names)
        self.assertIn("retrieval_documents", table_names)
        self.assertIn("retrieval_chunks", table_names)
        self.assertIn("embedding_jobs", table_names)
        self.assertIn("embedding_vectors", table_names)


if __name__ == "__main__":
    unittest.main()
