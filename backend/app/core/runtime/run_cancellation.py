from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from app.core.runtime.state import utc_now_iso


class RunCancellationRequested(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "").strip() or "Run cancelled by user."
        super().__init__(self.reason)


@dataclass
class RunCancellationToken:
    run_id: str
    _event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reason: str = ""
    _requested_at: str = ""
    _callbacks: list[Callable[[], None]] = field(default_factory=list)

    def request(self, reason: str) -> None:
        normalized_reason = str(reason or "").strip() or "Run cancellation requested."
        callbacks: list[Callable[[], None]] = []
        with self._lock:
            was_requested = self._event.is_set()
            self._reason = normalized_reason
            self._requested_at = self._requested_at or utc_now_iso()
            self._event.set()
            if not was_requested:
                callbacks = list(self._callbacks)
        for callback in callbacks:
            self._invoke_cancel_callback(callback)

    def add_cancel_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        should_invoke = False
        with self._lock:
            if self._event.is_set():
                should_invoke = True
            else:
                self._callbacks.append(callback)
        if should_invoke:
            self._invoke_cancel_callback(callback)

        def remove_callback() -> None:
            with self._lock:
                try:
                    self._callbacks.remove(callback)
                except ValueError:
                    pass

        return remove_callback

    @staticmethod
    def _invoke_cancel_callback(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            pass

    def is_requested(self) -> bool:
        return self._event.is_set()

    def reason(self) -> str:
        with self._lock:
            return self._reason

    def requested_at(self) -> str:
        with self._lock:
            return self._requested_at


_TOKENS: dict[str, RunCancellationToken] = {}
_TOKENS_LOCK = threading.Lock()


def register_run_cancellation_token(run_id: str) -> RunCancellationToken:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        raise ValueError("run_id is required.")
    with _TOKENS_LOCK:
        token = _TOKENS.get(normalized_run_id)
        if token is None:
            token = RunCancellationToken(normalized_run_id)
            _TOKENS[normalized_run_id] = token
        return token


def get_run_cancellation_token(run_id: str) -> RunCancellationToken | None:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None
    with _TOKENS_LOCK:
        return _TOKENS.get(normalized_run_id)


def request_run_cancellation(run_id: str, reason: str) -> bool:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return False
    token = register_run_cancellation_token(normalized_run_id)
    token.request(reason)
    return True


def raise_if_run_cancellation_requested(token: RunCancellationToken | None) -> None:
    if token is not None and token.is_requested():
        raise RunCancellationRequested(token.reason())


def unregister_run_cancellation_token(run_id: str) -> None:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return
    with _TOKENS_LOCK:
        _TOKENS.pop(normalized_run_id, None)
