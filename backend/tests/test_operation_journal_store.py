from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage.operation_journal_store import list_operation_journal_entries, record_operation_journal_event


class OperationJournalStoreTests(unittest.TestCase):
    def test_operation_journal_reads_camel_case_operation_request_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "operation_journal.jsonl"
            with patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path):
                entry = record_operation_journal_event(
                    run_id="run_parent",
                    event={
                        "sequence": 1,
                        "kind": "virtual_ui_operation",
                        "summary": "Requested virtual input.",
                        "status": "requested",
                        "created_at": "2026-05-18T10:00:00Z",
                        "detail": {
                            "operationRequest": {
                                "operationRequestId": "vop_input",
                                "operations": [{"kind": "input", "targetId": "buddy.input", "inputText": "继续"}],
                            },
                        },
                    },
                )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["operation_request_id"], "vop_input")
        self.assertEqual(entry["target_id"], "buddy.input")
        self.assertEqual(entry["input_text"], "继续")

    def test_operation_journal_infers_operation_from_operation_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "operation_journal.jsonl"
            with patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path):
                entry = record_operation_journal_event(
                    run_id="run_parent",
                    event={
                        "sequence": 1,
                        "kind": "virtual_ui_operation",
                        "summary": "Requested virtual click.",
                        "node_id": "execute_page_operation",
                        "status": "requested",
                        "created_at": "2026-05-18T10:00:00Z",
                        "detail": {
                            "operation_request_id": "vop_click",
                            "operation_request": {
                                "commands": ["click app.nav.runs"],
                                "operations": [
                                    {
                                        "kind": "click",
                                        "target_id": "app.nav.runs",
                                        "target_label": "运行记录",
                                    }
                                ],
                            },
                        },
                    },
                )

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["operation"]["kind"], "click")
        self.assertEqual(entry["target_id"], "app.nav.runs")
        self.assertEqual(entry["target_label"], "运行记录")

    def test_operation_journal_links_request_and_completion_by_operation_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "operation_journal.jsonl"
            with patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path):
                request_entry = record_operation_journal_event(
                    run_id="run_parent",
                    event={
                        "sequence": 1,
                        "kind": "virtual_ui_operation",
                        "summary": "Requested virtual template run.",
                        "node_id": "run_visible_template_operation",
                        "subgraph_node_id": "buddy_capability_loop",
                        "subgraph_path": ["buddy_capability_loop"],
                        "status": "requested",
                        "created_at": "2026-05-18T10:00:00Z",
                        "detail": {
                            "operation_request_id": "vop_template",
                            "operation": {
                                "kind": "run_template",
                                "target_id": "library.template.advanced_web_research_loop.open",
                                "target_label": "高级联网搜索",
                                "input_text": "鸣潮最新资讯",
                            },
                            "operation_request": {
                                "commands": ["run_template advanced_web_research_loop"],
                                "operations": [
                                    {
                                        "kind": "run_template",
                                        "target_id": "library.template.advanced_web_research_loop.open",
                                        "input_text": "鸣潮最新资讯",
                                    }
                                ],
                            },
                            "journal": [
                                {
                                    "kind": "run_template",
                                    "operation_request_id": "vop_template",
                                    "status": "requested",
                                    "target_id": "library.template.advanced_web_research_loop.open",
                                }
                            ],
                        },
                    },
                )
                completion_entry = record_operation_journal_event(
                    run_id="run_parent",
                    event={
                        "sequence": 2,
                        "kind": "virtual_ui_operation",
                        "summary": "Virtual run_template succeeded.",
                        "node_id": "run_visible_template_operation",
                        "subgraph_node_id": "buddy_capability_loop",
                        "subgraph_path": ["buddy_capability_loop"],
                        "status": "succeeded",
                        "created_at": "2026-05-18T10:00:12Z",
                        "detail": {
                            "operation_request_id": "vop_template",
                            "operation": {
                                "kind": "run_template",
                                "target_id": "library.template.advanced_web_research_loop.open",
                                "search_text": "advanced_web_research_loop",
                                "input_text": "鸣潮最新资讯",
                            },
                            "operation_report": {
                                "operation_request_id": "vop_template",
                                "status": "succeeded",
                                "triggered_run_id": "run_search",
                                "triggered_run_status": "completed",
                                "triggered_run_result_summary": "已拿到《鸣潮》最新资讯摘要。",
                            },
                            "page_snapshots": {
                                "before": {"snapshot_id": "before_1", "path": "/library", "title": "图与模板"},
                                "after": {"snapshot_id": "after_1", "path": "/editor", "title": "编辑器"},
                            },
                            "triggered_run": {
                                "run_id": "run_search",
                                "graph_id": "advanced_web_research_loop",
                                "initial_status": "queued",
                                "status": "completed",
                                "result_summary": "已拿到《鸣潮》最新资讯摘要。",
                            },
                        },
                    },
                )

                result = list_operation_journal_entries(operation_request_id="vop_template")

        self.assertEqual(request_entry["stage"], "request")
        self.assertEqual(completion_entry["stage"], "completion")
        self.assertEqual(result["total"], 2)
        self.assertEqual([entry["stage"] for entry in result["entries"]], ["request", "completion"])
        latest = result["entries"][-1]
        self.assertEqual(latest["operation_request_id"], "vop_template")
        self.assertEqual(latest["operation"]["kind"], "run_template")
        self.assertEqual(latest["operation"]["input_text"], "鸣潮最新资讯")
        self.assertEqual(latest["triggered_run"]["run_id"], "run_search")
        self.assertEqual(latest["triggered_run"]["status"], "completed")
        self.assertEqual(latest["page_snapshots"]["before"]["path"], "/library")

    def test_operation_journal_preserves_compact_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "operation_journal.jsonl"
            with patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path):
                entry = record_operation_journal_event(
                    run_id="run_parent",
                    event={
                        "sequence": 2,
                        "kind": "virtual_ui_operation",
                        "summary": "Virtual run_template succeeded.",
                        "node_id": "run_visible_template_operation",
                        "status": "succeeded",
                        "created_at": "2026-05-18T10:00:12Z",
                        "detail": {
                            "operation_request_id": "vop_template",
                            "operation": {
                                "kind": "run_template",
                                "target_id": "library.template.advanced_web_research_loop.open",
                            },
                            "operation_report": {
                                "operation_request_id": "vop_template",
                                "status": "succeeded",
                                "triggered_run_id": "run_search",
                                "retry_chain": [
                                    {
                                        "kind": "affordance",
                                        "target_id": "app.nav.library",
                                        "attempts": 4,
                                        "status": "resolved",
                                        "elapsed_ms": 360,
                                        "debug_payload": {"selector": "not compact"},
                                    }
                                ],
                                "artifact_refs": [
                                    {
                                        "title": "Brief",
                                        "artifact_kind": "saved_output",
                                        "path": "runs/run_search/brief.md",
                                        "file_name": "brief.md",
                                        "source_key": "brief",
                                        "node_id": "output_brief",
                                        "format": "md",
                                        "unexpected_large_value": {"body": "not part of the compact journal contract"},
                                    },
                                    {
                                        "title": "Chart",
                                        "artifact_kind": "image",
                                        "local_path": "runs/run_search/chart.png",
                                        "file_name": "chart.png",
                                        "content_type": "image/png",
                                    },
                                ],
                            },
                            "triggered_run": {
                                "run_id": "run_search",
                                "status": "completed",
                            },
                        },
                    },
                )

                result = list_operation_journal_entries(operation_request_id="vop_template")

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["artifact_refs"][0]["path"], "runs/run_search/brief.md")
        self.assertNotIn("unexpected_large_value", entry["artifact_refs"][0])
        self.assertEqual(entry["artifact_refs"][1]["local_path"], "runs/run_search/chart.png")
        self.assertEqual(entry["retry_chain"][0]["target_id"], "app.nav.library")
        self.assertEqual(entry["retry_chain"][0]["attempts"], 4)
        self.assertNotIn("debug_payload", entry["retry_chain"][0])
        self.assertEqual(result["entries"][0]["artifact_refs"], entry["artifact_refs"])
        self.assertEqual(result["entries"][0]["retry_chain"], entry["retry_chain"])

    def test_operation_journal_backfills_jsonl_into_sqlite_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            journal_path = temp_path / "operation_journal.jsonl"
            db_path = temp_path / "operation_journal.sqlite3"
            legacy_entry = {
                "id": "opj_legacy",
                "operation_request_id": "vop_legacy",
                "run_id": "run_legacy",
                "stage": "completion",
                "status": "succeeded",
                "summary": "Legacy JSONL entry.",
                "target_id": "app.nav.runs",
                "activity_sequence": 7,
                "activity_created_at": "2026-05-18T10:00:12Z",
                "recorded_at": "2026-05-18T10:00:13Z",
            }
            journal_path.write_text(json.dumps(legacy_entry, ensure_ascii=False) + "\n", encoding="utf-8")

            with (
                patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path),
                patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_DB_PATH", db_path),
            ):
                migrated = list_operation_journal_entries(run_id="run_legacy")
                journal_path.unlink()
                durable = list_operation_journal_entries(run_id="run_legacy")

            self.assertEqual(migrated["total"], 1)
            self.assertEqual(migrated["entries"][0]["id"], "opj_legacy")
            self.assertEqual(durable["total"], 1)
            self.assertEqual(durable["entries"][0]["operation_request_id"], "vop_legacy")
            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute("SELECT COUNT(*) FROM operation_journal_entries").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 1)

    def test_operation_journal_repairs_partial_sqlite_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            journal_path = temp_path / "operation_journal.jsonl"
            db_path = temp_path / "operation_journal.sqlite3"
            legacy_entry = {
                "id": "opj_partial_marker",
                "operation_request_id": "vop_partial_marker",
                "run_id": "run_partial_marker",
                "stage": "completion",
                "status": "succeeded",
                "summary": "Entry not present in the partial SQLite index.",
                "target_id": "app.nav.runs",
                "activity_sequence": 8,
                "activity_created_at": "2026-05-18T10:00:14Z",
                "recorded_at": "2026-05-18T10:00:15Z",
            }
            journal_path.write_text(json.dumps(legacy_entry, ensure_ascii=False) + "\n", encoding="utf-8")
            stat = journal_path.stat()
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE operation_journal_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE operation_journal_entries (
                        id TEXT PRIMARY KEY,
                        operation_request_id TEXT NOT NULL DEFAULT '',
                        run_id TEXT NOT NULL DEFAULT '',
                        stage TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT '',
                        target_id TEXT NOT NULL DEFAULT '',
                        failure_category TEXT NOT NULL DEFAULT '',
                        activity_created_at TEXT NOT NULL DEFAULT '',
                        activity_sequence INTEGER NOT NULL DEFAULT 0,
                        recorded_at TEXT NOT NULL DEFAULT '',
                        entry_json TEXT NOT NULL
                    );
                    """
                )
                connection.executemany(
                    "INSERT INTO operation_journal_metadata (key, value) VALUES (?, ?)",
                    [
                        ("schema_version", "1"),
                        ("jsonl_path", str(journal_path)),
                        ("jsonl_size", str(stat.st_size)),
                        ("jsonl_mtime_ns", str(stat.st_mtime_ns)),
                    ],
                )
                connection.commit()
            finally:
                connection.close()

            with (
                patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_PATH", journal_path),
                patch("app.core.storage.operation_journal_store.OPERATION_JOURNAL_DB_PATH", db_path),
            ):
                repaired = list_operation_journal_entries(run_id="run_partial_marker")

            self.assertEqual(repaired["total"], 1)
            self.assertEqual(repaired["entries"][0]["id"], "opj_partial_marker")


if __name__ == "__main__":
    unittest.main()
