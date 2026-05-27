from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from app.scheduler import runner


logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_INTERVAL_SECONDS = 60.0
DEFAULT_SCHEDULER_DUE_JOB_LIMIT = 25


class ThreadedBackgroundTasks:
    def __init__(self) -> None:
        self._threads: list[threading.Thread] = []

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        self._threads.append(thread)
        thread.start()


class SchedulerService:
    def __init__(
        self,
        *,
        interval_seconds: float = DEFAULT_SCHEDULER_INTERVAL_SECONDS,
        enabled: bool = True,
        run_tick_func: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.interval_seconds = max(0.01, float(interval_seconds))
        self.enabled = bool(enabled)
        self._run_tick_func = run_tick_func or run_scheduler_tick
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            if self.running:
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="toograph-scheduler", daemon=True)
            self._thread.start()
            return True

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict[str, Any]:
        return self._run_tick_func()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - defensive background loop path
                logger.exception("Scheduler tick failed: %s", exc)
            self._stop_event.wait(self.interval_seconds)


def run_scheduler_tick(
    *,
    now: str | None = None,
    limit: int = DEFAULT_SCHEDULER_DUE_JOB_LIMIT,
    requested_by: str = "scheduler",
    run_due_func: Callable[..., dict[str, Any]] = runner.run_due_scheduled_graph_jobs,
) -> dict[str, Any]:
    return run_due_func(
        background_tasks=ThreadedBackgroundTasks(),
        now=now,
        limit=limit,
        requested_by=requested_by,
    )


def start_scheduler_service() -> bool:
    return _default_scheduler_service().start()


def stop_scheduler_service() -> None:
    service = _default_scheduler_service()
    service.stop()


_DEFAULT_SERVICE: SchedulerService | None = None


def _default_scheduler_service() -> SchedulerService:
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = SchedulerService(
            interval_seconds=_scheduler_interval_from_env(),
            enabled=_scheduler_enabled_from_env(),
        )
    return _DEFAULT_SERVICE


def _scheduler_enabled_from_env() -> bool:
    value = os.environ.get("TOOGRAPH_SCHEDULER_DISABLED", "").strip().lower()
    return value not in {"1", "true", "yes", "on"}


def _scheduler_interval_from_env() -> float:
    value = os.environ.get("TOOGRAPH_SCHEDULER_POLL_INTERVAL_SECONDS", "").strip()
    if not value:
        return DEFAULT_SCHEDULER_INTERVAL_SECONDS
    try:
        return max(1.0, float(value))
    except ValueError:
        return DEFAULT_SCHEDULER_INTERVAL_SECONDS
