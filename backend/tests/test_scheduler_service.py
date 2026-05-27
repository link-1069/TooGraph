from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app, lifespan
from app.scheduler import service


class SchedulerServiceTests(unittest.TestCase):
    def test_scheduler_service_runs_tick_after_start_and_stops(self) -> None:
        tick_event = threading.Event()
        calls: list[str] = []

        def tick() -> dict[str, object]:
            calls.append("tick")
            tick_event.set()
            return {"started_count": 0, "errors": []}

        scheduler = service.SchedulerService(interval_seconds=0.01, run_tick_func=tick)

        started = scheduler.start()
        self.assertTrue(started)
        self.assertTrue(tick_event.wait(timeout=1))
        scheduler.stop(timeout=1)

        self.assertFalse(scheduler.running)
        self.assertGreaterEqual(len(calls), 1)

    def test_disabled_scheduler_service_does_not_start_thread(self) -> None:
        scheduler = service.SchedulerService(interval_seconds=0.01, enabled=False)

        started = scheduler.start()

        self.assertFalse(started)
        self.assertFalse(scheduler.running)

    def test_run_scheduler_tick_delegates_due_jobs_with_threaded_background_tasks(self) -> None:
        captured: dict[str, object] = {}

        def run_due(*, background_tasks: object, now: str | None, limit: int, requested_by: str) -> dict[str, object]:
            captured["has_add_task"] = callable(getattr(background_tasks, "add_task", None))
            captured["now"] = now
            captured["limit"] = limit
            captured["requested_by"] = requested_by
            return {"started_count": 2, "errors": []}

        result = service.run_scheduler_tick(
            now="2026-05-27T08:00:00Z",
            limit=7,
            requested_by="scheduler-test",
            run_due_func=run_due,
        )

        self.assertEqual(result["started_count"], 2)
        self.assertEqual(
            captured,
            {
                "has_add_task": True,
                "now": "2026-05-27T08:00:00Z",
                "limit": 7,
                "requested_by": "scheduler-test",
            },
        )

    def test_lifespan_starts_and_stops_scheduler_service(self) -> None:
        calls: list[str] = []

        async def exercise() -> None:
            async with lifespan(app):
                calls.append("inside")

        with (
            patch("app.main.startup", lambda: calls.append("startup")),
            patch("app.main.start_scheduler_service", lambda: calls.append("start_scheduler_service")),
            patch("app.main.stop_scheduler_service", lambda: calls.append("stop_scheduler_service")),
        ):
            asyncio.run(exercise())

        self.assertEqual(calls, ["startup", "start_scheduler_service", "inside", "stop_scheduler_service"])


if __name__ == "__main__":
    unittest.main()
