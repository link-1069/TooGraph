from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.storage import database
from app.scheduler import official_seed, store


class SchedulerOfficialSeedTests(unittest.TestCase):
    def test_seed_official_jobs_creates_disabled_curator_and_embedding_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            db_path = data_dir / "toograph.db"
            with (
                patch("app.core.storage.database.DATA_DIR", data_dir),
                patch("app.core.storage.database.DB_PATH", db_path),
            ):
                database.initialize_storage()

                result = official_seed.seed_official_scheduled_graph_jobs(now="2026-05-27T00:00:00Z")
                jobs = {job["job_id"]: job for job in store.list_scheduled_graph_jobs(include_disabled=True)}
                due = store.list_due_scheduled_graph_jobs(now="2026-05-27T00:00:00Z")

        self.assertEqual(result["created_count"], 2)
        self.assertEqual(result["existing_count"], 0)
        self.assertEqual(set(jobs), {"official_buddy_capability_curator", "official_embedding_maintenance"})
        curator = jobs["official_buddy_capability_curator"]
        embedding = jobs["official_embedding_maintenance"]
        self.assertEqual(curator["template_id"], "buddy_capability_curator")
        self.assertEqual(curator["schedule_kind"], "interval")
        self.assertEqual(curator["schedule_expr"], "PT168H")
        self.assertFalse(curator["enabled"])
        self.assertEqual(curator["next_run_at"], "")
        self.assertEqual(
            curator["retry_policy"],
            {"max_attempts": 3, "delay_seconds": 1800, "backoff_multiplier": 2.0},
        )
        self.assertEqual(curator["metadata"]["source"], "official_seed")
        self.assertEqual(curator["input_bindings"]["curator_scope"]["lookback_days"], 30)
        self.assertEqual(embedding["template_id"], "embedding_maintenance")
        self.assertEqual(embedding["schedule_expr"], "PT1H")
        self.assertFalse(embedding["enabled"])
        self.assertEqual(
            embedding["retry_policy"],
            {"max_attempts": 3, "delay_seconds": 300, "backoff_multiplier": 2.0},
        )
        self.assertEqual(embedding["input_bindings"], {"model_ref": "", "job_limit": 50})
        self.assertEqual(due, [])

    def test_seed_official_jobs_is_idempotent_and_preserves_enabled_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            db_path = data_dir / "toograph.db"
            with (
                patch("app.core.storage.database.DATA_DIR", data_dir),
                patch("app.core.storage.database.DB_PATH", db_path),
            ):
                database.initialize_storage()

                first = official_seed.seed_official_scheduled_graph_jobs(now="2026-05-27T00:00:00Z")
                store.set_scheduled_graph_job_enabled(
                    "official_embedding_maintenance",
                    True,
                    now="2026-05-27T01:00:00Z",
                )
                second = official_seed.seed_official_scheduled_graph_jobs(now="2026-05-27T02:00:00Z")
                jobs = store.list_scheduled_graph_jobs(include_disabled=True)
                embedding = store.load_scheduled_graph_job("official_embedding_maintenance")

        self.assertEqual(first["created_count"], 2)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["existing_count"], 2)
        self.assertEqual(len(jobs), 2)
        self.assertTrue(embedding["enabled"])
        self.assertEqual(embedding["next_run_at"], "2026-05-27T02:00:00Z")


if __name__ == "__main__":
    unittest.main()
