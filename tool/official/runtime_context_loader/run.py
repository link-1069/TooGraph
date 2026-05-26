from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_MAX_CHARS = 8000
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "apikey", "api_key", "auth")


def runtime_context_loader(payload: dict[str, Any] | None, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        runtime_context = _resolve_runtime_context(inputs=inputs, explicit_context=context)
        run_id = _resolve_source_run_id(inputs=inputs, runtime_context=runtime_context, explicit_context=context)
        selected_keys = _selected_keys(inputs.get("selected_keys"))
        max_chars = _bounded_int(inputs.get("max_chars"), default=DEFAULT_MAX_CHARS, minimum=256, maximum=100000)

        rendered_text, source_refs, used_chars, source_chars, omitted_count, warnings = _render_runtime_context(
            runtime_context,
            selected_keys=selected_keys,
            run_id=run_id,
            max_chars=max_chars,
        )
        context_ref = _build_context_ref(
            source_refs=source_refs,
            run_id=run_id,
            max_chars=max_chars,
            rendered_text=rendered_text,
        )
        package = _build_context_package(
            source_refs=source_refs,
            context_ref=context_ref,
            run_id=run_id,
            max_chars=max_chars,
            used_chars=used_chars,
            source_chars=source_chars,
            omitted_count=omitted_count,
            warnings=warnings,
        )
        return {
            "status": "succeeded",
            "runtime_context_package": package,
            "runtime_context_report": {
                "scope": "runtime",
                "run_id": run_id,
                "keys": [_as_text(_coerce_dict(ref.get("metadata")).get("key")) for ref in source_refs],
                "source_refs": source_refs,
                "source_count": len(source_refs),
                "max_chars": max_chars,
                "source_chars": source_chars,
                "used_chars": used_chars,
                "omitted_count": omitted_count,
                "warnings": warnings,
            },
        }
    except Exception as exc:
        warning = _warning("runtime_context_load_failed", str(exc))
        return {
            "status": "failed",
            "error_type": "runtime_context_load_failed",
            "error": str(exc),
            "runtime_context_package": _empty_package([warning]),
            "runtime_context_report": {
                "scope": "runtime",
                "source_refs": [],
                "source_count": 0,
                "warnings": [warning],
            },
        }


def _render_runtime_context(
    runtime_context: dict[str, Any],
    *,
    selected_keys: list[str],
    run_id: str,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]], int, int, int, list[dict[str, Any]]]:
    candidates = _selected_runtime_items(runtime_context, selected_keys=selected_keys)
    sections: list[str] = []
    source_refs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    used_chars = 0
    omitted_count = 0
    source_chars = 0
    for key, value in candidates:
        if _is_sensitive_key(key):
            warnings.append(_warning("runtime_context_key_skipped", f"Runtime context key '{key}' is sensitive."))
            continue
        rendered_value = _stringify(value)
        if not rendered_value:
            continue
        line = f"{key}: {rendered_value}"
        source_chars += len(line)
        separator = "\n" if sections else ""
        remaining = max_chars - used_chars
        if remaining <= 0:
            omitted_count += 1
            continue
        line_with_separator = f"{separator}{line}"
        if len(line_with_separator) > remaining:
            line_with_separator = line_with_separator[: max(0, remaining)] + "\n[Runtime context omitted by max_chars budget.]"
            omitted_count += 1
        used_chars += len(line_with_separator)
        sections.append(line_with_separator if not separator else line_with_separator[len(separator):])
        source_refs.append(
            _source_ref_from_item(
                key=key,
                value=value,
                rendered_line=line,
                run_id=run_id,
                ordinal=len(source_refs),
            )
        )
    return "\n".join(sections), source_refs, used_chars, source_chars, omitted_count, warnings


def _selected_runtime_items(runtime_context: dict[str, Any], *, selected_keys: list[str]) -> list[tuple[str, Any]]:
    if selected_keys:
        items: list[tuple[str, Any]] = []
        seen: set[str] = set()
        for key in selected_keys:
            if not key or key in seen:
                continue
            found, value = _get_path(runtime_context, key)
            if found:
                items.append((key, value))
                seen.add(key)
        return items
    return list(_flatten_runtime_context(runtime_context))


def _flatten_runtime_context(value: Any, *, prefix: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    if depth > 4:
        return []
    if isinstance(value, dict):
        items: list[tuple[str, Any]] = []
        for key, nested in value.items():
            text_key = _as_text(key)
            if not text_key:
                continue
            path = f"{prefix}.{text_key}" if prefix else text_key
            if isinstance(nested, dict):
                nested_items = _flatten_runtime_context(nested, prefix=path, depth=depth + 1)
                if nested_items:
                    items.extend(nested_items)
                else:
                    items.append((path, nested))
            elif isinstance(nested, list):
                items.append((path, nested))
            else:
                items.append((path, nested))
        return items
    return [(prefix or "runtime_context", value)]


def _get_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return False, None
    return True, current


def _source_ref_from_item(*, key: str, value: Any, rendered_line: str, run_id: str, ordinal: int) -> dict[str, Any]:
    content_hash = _put_item_blob(rendered_line, key=key, run_id=run_id)
    source_id = ":".join(part for part in [run_id, key] if part) or f"runtime:{key}"
    return {
        "source_kind": "runtime_context_item",
        "source_id": source_id,
        "source_content_hash": content_hash,
        "label": key,
        "ordinal": ordinal,
        "metadata": {
            "run_id": run_id,
            "key": key,
            "value_type": _value_type(value),
        },
    }


def _build_context_ref(
    *,
    source_refs: list[dict[str, Any]],
    run_id: str,
    max_chars: int,
    rendered_text: str,
) -> dict[str, Any]:
    if not source_refs:
        return _empty_context_ref()
    try:
        from app.core.storage.context_assembly_store import create_context_assembly

        return create_context_assembly(
            target_state_key="runtime_context_package",
            renderer_key="runtime_context",
            renderer_version="1",
            rendered_text=rendered_text,
            sources=source_refs,
            budget={"max_chars": max_chars},
            metadata={"scope": "runtime", "run_id": run_id},
        )
    except Exception:
        source_key = [[ref.get("source_kind"), ref.get("source_id"), ref.get("source_content_hash")] for ref in source_refs]
        key = json.dumps({"source_refs": source_key, "max_chars": max_chars}, ensure_ascii=False, sort_keys=True)
        return {
            "kind": "context_assembly_ref",
            "assembly_id": f"ctx_runtime_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}",
            "target_state_key": "runtime_context_package",
            "renderer_key": "runtime_context",
            "renderer_version": "1",
            "rendered_content_hash": _content_hash(rendered_text) if rendered_text else "",
            "source_count": len(source_refs),
            "source_refs": source_refs,
            "budget": {"max_chars": max_chars},
            "metadata": {"scope": "runtime", "run_id": run_id},
        }


def _build_context_package(
    *,
    source_refs: list[dict[str, Any]],
    context_ref: dict[str, Any],
    run_id: str,
    max_chars: int,
    used_chars: int,
    source_chars: int,
    omitted_count: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    items = [
        {
            "id": _as_text(ref.get("source_id")),
            "title": _as_text(ref.get("label")),
            "source_ref": ref,
            "metadata": {
                "run_id": run_id,
                "key": _as_text(_coerce_dict(ref.get("metadata")).get("key")),
                "value_type": _as_text(_coerce_dict(ref.get("metadata")).get("value_type")),
            },
        }
        for ref in source_refs
    ]
    return {
        "kind": "context_package",
        "package_id": _context_package_id(context_ref),
        "source_kind": "runtime",
        "authority": "context_only",
        "title": "Runtime context",
        "items": items,
        "source_refs": source_refs,
        "source_count": len(source_refs),
        "context_ref": context_ref,
        "budget": {
            "max_chars": max_chars,
            "source_chars": source_chars,
            "used_chars": used_chars,
            "omitted_count": omitted_count,
        },
        "warnings": warnings,
        "metadata": {
            "renderer_key": "runtime_context",
            "renderer_version": "1",
            "run_id": run_id,
        },
    }


def _empty_package(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "context_package",
        "package_id": "pkg_runtime_empty",
        "source_kind": "runtime",
        "authority": "context_only",
        "title": "Runtime context",
        "items": [],
        "source_refs": [],
        "source_count": 0,
        "context_ref": _empty_context_ref(),
        "budget": {"source_chars": 0, "used_chars": 0, "omitted_count": 0},
        "warnings": warnings,
        "metadata": {"renderer_key": "runtime_context", "renderer_version": "1"},
    }


def _empty_context_ref() -> dict[str, Any]:
    return {
        "kind": "context_assembly_ref",
        "assembly_id": "ctx_runtime_empty",
        "target_state_key": "runtime_context_package",
        "renderer_key": "runtime_context",
        "renderer_version": "1",
        "rendered_content_hash": "",
        "source_count": 0,
        "source_refs": [],
    }


def _put_item_blob(rendered_line: str, *, key: str, run_id: str) -> str:
    try:
        from app.core.storage.content_blob_store import put_content_blob

        blob = put_content_blob(
            rendered_line,
            "text/plain",
            {
                "kind": "runtime_context_item",
                "run_id": run_id,
                "key": key,
            },
        )
        return _as_text(blob.get("content_hash"))
    except Exception:
        return _content_hash(rendered_line)


def _resolve_runtime_context(*, inputs: dict[str, Any], explicit_context: dict[str, Any] | None) -> dict[str, Any]:
    input_context = inputs.get("runtime_context")
    if isinstance(input_context, dict):
        return input_context
    if isinstance(explicit_context, dict):
        nested = explicit_context.get("runtime_context")
        action_nested = explicit_context.get("action_runtime_context")
        if isinstance(nested, dict):
            return nested
        if isinstance(action_nested, dict):
            return action_nested
    env_context = _read_json_env("TOOGRAPH_ACTION_RUNTIME_CONTEXT")
    if env_context:
        return env_context
    file_path = _as_text(os.environ.get("TOOGRAPH_ACTION_RUNTIME_CONTEXT_FILE"))
    if file_path:
        try:
            value = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except Exception:
            value = {}
        if isinstance(value, dict):
            return value
    return {}


def _resolve_source_run_id(
    *,
    inputs: dict[str, Any],
    runtime_context: dict[str, Any],
    explicit_context: dict[str, Any] | None,
) -> str:
    if isinstance(explicit_context, dict):
        explicit_run_id = _as_text(explicit_context.get("run_id"))
        if explicit_run_id:
            return explicit_run_id
    return _as_text(inputs.get("source_run_id") or runtime_context.get("source_run_id") or runtime_context.get("run_id"))


def _read_json_env(key: str) -> dict[str, Any]:
    raw = _as_text(os.environ.get(key))
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _selected_keys(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "json_object"
    if isinstance(value, list):
        return "json_array"
    return "text"


def _ensure_backend_path() -> None:
    repo_root = Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _context_package_id(context_ref: dict[str, Any]) -> str:
    assembly_id = _as_text(context_ref.get("assembly_id"))
    if assembly_id.startswith("ctx_"):
        return f"pkg_{assembly_id[4:]}"
    if assembly_id:
        return f"pkg_{assembly_id}"
    return "pkg_runtime_empty"


def _content_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _warning(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
    print(json.dumps(runtime_context_loader(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
