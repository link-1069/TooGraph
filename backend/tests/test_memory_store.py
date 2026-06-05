from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database


def _project_memory_for_test_recall(memory: dict[str, object]) -> dict[str, object]:
    from app.core.storage.retrieval_store import upsert_retrieval_chunks, upsert_retrieval_document

    document = upsert_retrieval_document(
        document_id=f"test_memory_doc_{memory['memory_id']}",
        source_kind="memory_entry",
        source_id=str(memory["memory_id"]),
        source_revision_id=str(memory.get("latest_revision_id") or ""),
        title=str(memory.get("title") or ""),
        content=str(memory.get("content") or ""),
        scope={
            "scope_kind": memory.get("scope_kind"),
            "scope_id": memory.get("scope_id"),
            "layer": memory.get("layer"),
        },
        metadata={
            "memory_type": memory.get("memory_type"),
            "status": memory.get("status"),
        },
    )
    [chunk] = upsert_retrieval_chunks(
        document["document_id"],
        [
            {
                "chunk_id": f"test_memory_chunk_{memory['memory_id']}",
                "content": str(memory.get("content") or ""),
                "source_locator": {"field": "content"},
                "metadata": {
                    "scope_kind": memory.get("scope_kind"),
                    "scope_id": memory.get("scope_id"),
                    "layer": memory.get("layer"),
                    "memory_type": memory.get("memory_type"),
                    "status": memory.get("status"),
                },
            }
        ],
    )
    return chunk


class MemoryStoreTests(unittest.TestCase):
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

    def test_create_memory_entry_creates_revision_event_and_retrieval_projection(self) -> None:
        from app.core.storage.memory_store import create_memory_entry

        memory = create_memory_entry(
            scope_kind="buddy_session",
            scope_id="session_1",
            layer="long_term",
            memory_type="preference",
            title="Source of truth preference",
            content="The user treats graph run records as the durable source of truth.",
            confidence=0.9,
            salience=0.8,
            sources=[
                {
                    "source_kind": "buddy_message",
                    "source_id": "msg_1",
                    "source_revision_id": "msgrev_1",
                    "source_locator": {"field": "content"},
                }
            ],
            metadata={"topic": "storage"},
        )

        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            revision_count = connection.execute("SELECT COUNT(*) FROM memory_revisions").fetchone()[0]
            event_count = connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
            retrieval_doc = connection.execute(
                """
                SELECT source_kind, source_id, source_revision_id, title, scope_json, metadata_json
                FROM retrieval_documents
                WHERE source_kind = 'memory_entry' AND source_id = ?
                """,
                (memory["memory_id"],),
            ).fetchone()
            retrieval_chunk = connection.execute(
                """
                SELECT chunk_id, content, source_locator_json, metadata_json
                FROM retrieval_chunks
                WHERE source_kind = 'memory_entry' AND source_id = ?
                """,
                (memory["memory_id"],),
            ).fetchone()

        self.assertEqual(memory["latest_revision_id"], memory["revisions"][0]["revision_id"])
        self.assertEqual(revision_count, 1)
        self.assertEqual(event_count, 1)
        self.assertEqual(retrieval_doc[0], "memory_entry")
        self.assertEqual(retrieval_doc[1], memory["memory_id"])
        self.assertEqual(retrieval_doc[2], memory["latest_revision_id"])
        self.assertEqual(retrieval_doc[3], memory["title"])
        self.assertEqual(json.loads(retrieval_doc[4])["scope_id"], "session_1")
        self.assertEqual(json.loads(retrieval_doc[5])["status"], "active")
        self.assertEqual(retrieval_chunk[0], f"memory_entry:{memory['memory_id']}:body")
        self.assertEqual(retrieval_chunk[1], memory["content"])
        self.assertEqual(json.loads(retrieval_chunk[2])["memory_id"], memory["memory_id"])
        self.assertEqual(json.loads(retrieval_chunk[3])["memory_type"], "preference")
        self.assertEqual(memory["retrieval_projection"]["status"], "succeeded")
        self.assertEqual(memory["retrieval_projection"]["chunk_count"], 1)

    def test_memory_writes_project_to_retrieval_and_queue_default_embedding_jobs(self) -> None:
        from app.core.storage.memory_store import create_memory_entry, update_memory_entry

        embedding_settings = {
            "embedding_model_ref": "local/test-embedding",
            "model_providers": {
                "local": {
                    "label": "Local",
                    "transport": "openai-compatible",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "enabled": True,
                    "models": [
                        {
                            "model": "test-embedding",
                            "label": "test-embedding",
                            "capabilities": {"chat": False, "embedding": True},
                            "embedding": {"dimensions": 3},
                        }
                    ],
                }
            },
        }
        with patch("app.core.storage.settings_store.load_app_settings", return_value=embedding_settings):
            memory = create_memory_entry(
                scope_kind="buddy_session",
                scope_id="session_1",
                layer="long_term",
                memory_type="preference",
                title="Recall preference",
                content="The user wants fresh long-term memories to become searchable.",
            )
            updated = update_memory_entry(
                memory["memory_id"],
                {"content": "The user wants updated long-term memories to become searchable after review."},
            )

        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            jobs = connection.execute(
                """
                SELECT source_kind, source_id, chunk_id, embedding_model_id, content_hash, status, last_error
                FROM embedding_jobs
                WHERE source_id = ?
                ORDER BY created_at ASC, job_id ASC
                """,
                (memory["memory_id"],),
            ).fetchall()
            current_chunk = connection.execute(
                "SELECT chunk_id, content, content_hash, metadata_json FROM retrieval_chunks WHERE source_id = ?",
                (memory["memory_id"],),
            ).fetchone()

        self.assertEqual(current_chunk[0], f"memory_entry:{memory['memory_id']}:body")
        self.assertIn("updated long-term memories", current_chunk[1])
        self.assertEqual(json.loads(current_chunk[3])["status"], "active")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0][0], "memory_entry")
        self.assertEqual(jobs[0][1], memory["memory_id"])
        self.assertEqual(jobs[0][2], current_chunk[0])
        self.assertEqual(jobs[0][5], "failed")
        self.assertIn("superseded", jobs[0][6])
        self.assertEqual(jobs[1][5], "pending")
        self.assertEqual(jobs[1][4], current_chunk[2])
        self.assertEqual(updated["retrieval_projection"]["embedding_job_count"], 1)

    def test_create_memory_entry_skips_duplicate_content_and_merges_sources(self) -> None:
        from app.core.storage.memory_store import create_memory_entry

        first = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Reply preference",
            content="The user prefers conclusions first, then details.",
            sources=[{"source_kind": "buddy_message", "source_id": "msg_original"}],
        )
        duplicate = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Duplicate reply preference",
            content=" The user prefers conclusions first, then details. ",
            sources=[{"source_kind": "buddy_message", "source_id": "msg_duplicate"}],
        )

        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            memory_count = connection.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            revision_operations = [
                row[0]
                for row in connection.execute(
                    "SELECT operation FROM memory_revisions WHERE memory_id = ? ORDER BY revision_number",
                    (first["memory_id"],),
                ).fetchall()
            ]
            event_types = [
                row[0]
                for row in connection.execute(
                    "SELECT event_type FROM memory_events WHERE memory_id = ? ORDER BY created_at, event_id",
                    (first["memory_id"],),
                ).fetchall()
            ]

        self.assertEqual(duplicate["memory_id"], first["memory_id"])
        self.assertEqual(duplicate["dedupe"]["status"], "skipped_duplicate")
        self.assertEqual(duplicate["dedupe"]["reason"], "duplicate_canonical_content")
        self.assertEqual(duplicate["dedupe"]["requested_title"], "Duplicate reply preference")
        self.assertTrue(duplicate["dedupe"]["content_fingerprint"].startswith("sha256:"))
        self.assertEqual(memory_count, 1)
        self.assertEqual(
            [(source["source_kind"], source["source_id"]) for source in duplicate["sources"]],
            [("buddy_message", "msg_original"), ("buddy_message", "msg_duplicate")],
        )
        self.assertEqual(revision_operations, ["create", "dedupe_merge_sources"])
        self.assertEqual(event_types, ["created", "duplicate_skipped"])

    def test_create_memory_entry_skips_near_duplicate_content(self) -> None:
        from app.core.storage.memory_store import create_memory_entry

        first = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Planning style preference",
            content="The user wants architecture decisions summarized before implementation details.",
            sources=[{"source_kind": "buddy_message", "source_id": "msg_near_original"}],
        )
        duplicate = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Implementation planning preference",
            content="The user wants architecture decisions summarized first, before implementation details.",
            sources=[{"source_kind": "buddy_message", "source_id": "msg_near_duplicate"}],
        )

        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            memory_count = connection.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            duplicate_event = connection.execute(
                """
                SELECT detail_json
                FROM memory_events
                WHERE memory_id = ? AND event_type = 'duplicate_skipped'
                ORDER BY created_at DESC, event_id DESC
                LIMIT 1
                """,
                (first["memory_id"],),
            ).fetchone()

        self.assertEqual(duplicate["memory_id"], first["memory_id"])
        self.assertEqual(duplicate["dedupe"]["status"], "skipped_duplicate")
        self.assertEqual(duplicate["dedupe"]["reason"], "near_duplicate_content")
        self.assertGreaterEqual(duplicate["dedupe"]["similarity_score"], 0.58)
        self.assertEqual(memory_count, 1)
        self.assertEqual(
            [(source["source_kind"], source["source_id"]) for source in duplicate["sources"]],
            [("buddy_message", "msg_near_original"), ("buddy_message", "msg_near_duplicate")],
        )
        self.assertEqual(json.loads(duplicate_event[0])["reason"], "near_duplicate_content")

    def test_memory_entry_sources_can_reference_supported_fact_types(self) -> None:
        from app.core.storage.memory_store import create_memory_entry

        memory = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="session",
            memory_type="observation",
            title="Source support",
            content="Memory entries can cite messages, runs, outputs, and retrieval chunks.",
            sources=[
                {"source_kind": "buddy_message", "source_id": "msg_1", "source_revision_id": "rev_1"},
                {"source_kind": "graph_run", "source_id": "run_1"},
                {"source_kind": "graph_output", "source_id": "output_1"},
                {"source_kind": "retrieval_chunk", "source_id": "chunk_1"},
            ],
        )

        self.assertEqual(
            [source["source_kind"] for source in memory["sources"]],
            ["buddy_message", "graph_run", "graph_output", "retrieval_chunk"],
        )

    def test_update_and_archive_preserve_revisions_and_projection_status(self) -> None:
        from app.core.storage.memory_store import archive_memory_entry, create_memory_entry, update_memory_entry

        memory = create_memory_entry(
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Update preference",
            content="The user prefers concise replies.",
        )
        updated = update_memory_entry(
            memory["memory_id"],
            {"content": "The user prefers concise replies with concrete next steps.", "salience": 0.7},
            changed_by="buddy",
            change_reason="test update",
        )
        archived = archive_memory_entry(memory["memory_id"], changed_by="buddy", change_reason="test archive")

        with closing(sqlite3.connect(database.DB_PATH)) as connection:
            revision_count = connection.execute(
                "SELECT COUNT(*) FROM memory_revisions WHERE memory_id = ?",
                (memory["memory_id"],),
            ).fetchone()[0]
            retrieval_chunk = connection.execute(
                "SELECT content, metadata_json FROM retrieval_chunks WHERE source_id = ?",
                (memory["memory_id"],),
            ).fetchone()

        self.assertEqual(updated["content"], "The user prefers concise replies with concrete next steps.")
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["retrieval_projection"]["metadata"]["status"], "archived")
        self.assertEqual(revision_count, 3)
        self.assertIn("concrete next steps", retrieval_chunk[0])
        self.assertEqual(json.loads(retrieval_chunk[1])["status"], "archived")

    def test_recall_memories_returns_source_refs(self) -> None:
        from app.core.storage.memory_store import create_memory_entry, recall_memories

        memory = create_memory_entry(
            scope_kind="buddy_session",
            scope_id="session_1",
            layer="long_term",
            memory_type="preference",
            title="Searchable memory",
            content="The user wants embedding memory chunks to serve recall.",
        )
        results = recall_memories(
            "embedding memory chunks",
            filters={"scope_kind": "buddy_session", "scope_id": "session_1"},
            limit=3,
        )

        self.assertEqual(results[0]["memory_id"], memory["memory_id"])
        self.assertEqual(results[0]["source_ref"]["source_kind"], "memory_entry")
        self.assertEqual(results[0]["source_ref"]["source_id"], memory["memory_id"])

    def test_recall_memories_uses_reranker_without_embedding_model(self) -> None:
        from app.core.storage.memory_store import create_memory_entry, recall_memories

        first = create_memory_entry(
            memory_id="mem_base_first",
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Older evidence",
            content="rerank-memory-evidence older preference.",
        )
        second = create_memory_entry(
            memory_id="mem_reranked_first",
            scope_kind="buddy",
            scope_id="default",
            layer="long_term",
            memory_type="preference",
            title="Exact evidence",
            content="rerank-memory-evidence exact current preference.",
        )
        def fake_rerank(**kwargs):
            self.assertEqual(kwargs["model_ref"], "local-rerank/bge-reranker-v2")
            self.assertEqual(len(kwargs["documents"]), 2)
            exact_index = 0 if "exact current" in kwargs["documents"][0] else 1
            other_index = 1 - exact_index
            return [
                {"index": exact_index, "score": 0.98, "document": kwargs["documents"][exact_index]},
                {"index": other_index, "score": 0.41, "document": kwargs["documents"][other_index]},
            ], {"provider_id": "local-rerank", "model": "bge-reranker-v2"}

        with patch("app.core.storage.retrieval_store.rerank_documents_with_model_ref", side_effect=fake_rerank):
            results = recall_memories(
                "rerank-memory-evidence preference",
                filters={"reranker_model_ref": "local-rerank/bge-reranker-v2"},
                limit=2,
            )

        self.assertEqual([memory["memory_id"] for memory in results], [second["memory_id"], first["memory_id"]])
        self.assertEqual(results[0]["retrieval"]["mode"], "hybrid_rerank")
        self.assertEqual(results[0]["retrieval"]["rerank_score"], 0.98)


if __name__ == "__main__":
    unittest.main()
