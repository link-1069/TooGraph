from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


def embedding_job_processor(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        from app.core.storage.embedding_store import process_pending_embedding_jobs

        return process_pending_embedding_jobs(
            model_ref=_text(inputs.get("model_ref")),
            limit=_int(inputs.get("limit"), default=50),
        )
    except Exception as exc:
        return {
            "status": "failed",
            "error_type": "embedding_job_processing_failed",
            "error": str(exc),
            "processed_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "processed_jobs": [],
        }


def _ensure_backend_path() -> None:
    repo_root = Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _int(value: Any, *, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "failed", "error_type": "invalid_json", "error": str(exc)}, ensure_ascii=False))
        return
    if not isinstance(payload, dict):
        print(
            json.dumps(
                {"status": "failed", "error_type": "invalid_input", "error": "stdin must be a JSON object."},
                ensure_ascii=False,
            )
        )
        return
    print(json.dumps(embedding_job_processor(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
