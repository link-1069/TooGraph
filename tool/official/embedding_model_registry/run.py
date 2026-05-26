from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


def embedding_model_registry(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    operation = _text(inputs.get("operation") or "list").lower()
    try:
        _ensure_backend_path()
        from app.core.storage.embedding_store import list_embedding_models, register_embedding_model

        if operation == "register":
            model = register_embedding_model(
                provider_key=_text(inputs.get("provider_key")),
                model=_text(inputs.get("model")),
                dimensions=_int(inputs.get("dimensions"), default=384),
                distance_metric=_text(inputs.get("distance_metric") or "cosine"),
                enabled=_bool(inputs.get("enabled"), default=True),
                metadata=_metadata(inputs.get("metadata")),
            )
            return {
                "status": "succeeded",
                "operation": operation,
                "model": model,
                "models": [model],
                "error": "",
            }
        if operation == "list":
            models = list_embedding_models(enabled_only=_bool(inputs.get("enabled_only"), default=False))
            return {
                "status": "succeeded",
                "operation": operation,
                "model": {},
                "models": models,
                "error": "",
            }
        raise ValueError(f"Unsupported operation: {operation}")
    except Exception as exc:
        return {
            "status": "failed",
            "operation": operation,
            "model": {},
            "models": [],
            "error_type": "embedding_model_registry_failed",
            "error": str(exc),
        }


def _ensure_backend_path() -> None:
    repo_root = Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _int(value: Any, *, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"note": value.strip()}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


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
    print(json.dumps(embedding_model_registry(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
