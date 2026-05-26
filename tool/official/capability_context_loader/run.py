from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_MAX_CHARS = 24000


def capability_context_loader(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        result_package = _coerce_result_package(inputs.get("result_package") or inputs.get("capability_result"))
        run_id = _as_text(inputs.get("run_id"))
        state_key = _as_text(inputs.get("state_key")) or "capability_result"
        max_chars = _bounded_int(inputs.get("max_chars"), default=DEFAULT_MAX_CHARS, minimum=512, maximum=200000)

        rendered_text, source_refs, used_chars, source_chars, omitted_count, warnings = _render_result_package(
            result_package,
            run_id=run_id,
            state_key=state_key,
            max_chars=max_chars,
        )
        context_ref = _build_context_ref(
            source_refs=source_refs,
            result_package=result_package,
            run_id=run_id,
            state_key=state_key,
            max_chars=max_chars,
            rendered_text=rendered_text,
        )
        package = _build_context_package(
            result_package=result_package,
            source_refs=source_refs,
            context_ref=context_ref,
            run_id=run_id,
            state_key=state_key,
            max_chars=max_chars,
            used_chars=used_chars,
            source_chars=source_chars,
            omitted_count=omitted_count,
            warnings=warnings,
        )
        return {
            "status": "succeeded",
            "capability_context": package,
            "capability_context_report": {
                "scope": "capability",
                "source_type": _source_type(result_package),
                "source_key": _source_key(result_package),
                "source_name": _source_name(result_package),
                "result_status": _as_text(result_package.get("status")),
                "run_id": run_id,
                "state_key": state_key,
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
        warning = _warning("capability_context_load_failed", str(exc))
        return {
            "status": "failed",
            "error_type": "capability_context_load_failed",
            "error": str(exc),
            "capability_context": _empty_package([warning]),
            "capability_context_report": {
                "scope": "capability",
                "source_refs": [],
                "source_count": 0,
                "warnings": [warning],
            },
        }


def _render_result_package(
    package: dict[str, Any],
    *,
    run_id: str,
    state_key: str,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]], int, int, int, list[dict[str, Any]]]:
    outputs = package.get("outputs") if isinstance(package.get("outputs"), dict) else {}
    sections: list[str] = []
    source_refs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    used_chars = 0
    omitted_count = 0
    source_chars = 0
    for output_key, raw_output in outputs.items():
        normalized_output_key = _as_text(output_key)
        if not normalized_output_key:
            warnings.append(_warning("capability_output_missing_key", "Capability output is missing an output key."))
            continue
        output_value = raw_output.get("value") if isinstance(raw_output, dict) else raw_output
        rendered_value = _stringify(output_value)
        source_chars += len(rendered_value)
        section = _render_output_section(package, normalized_output_key, raw_output, rendered_value)
        separator = "\n\n" if sections else ""
        remaining = max_chars - used_chars
        if remaining <= 0:
            omitted_count += 1
            continue
        section_with_separator = f"{separator}{section}"
        if len(section_with_separator) > remaining:
            section_with_separator = section_with_separator[: max(0, remaining)] + "\n[Capability context omitted by max_chars budget.]"
            omitted_count += 1
        used_chars += len(section_with_separator)
        sections.append(section_with_separator if not separator else section_with_separator[len(separator):])
        source_refs.append(
            _source_ref_from_output(
                package,
                output_key=normalized_output_key,
                raw_output=raw_output,
                output_text=rendered_value,
                run_id=run_id,
                state_key=state_key,
                ordinal=len(source_refs),
            )
        )
    return "\n\n".join(sections), source_refs, used_chars, source_chars, omitted_count, warnings


def _render_output_section(package: dict[str, Any], output_key: str, raw_output: Any, rendered_value: str) -> str:
    output_name = _as_text(raw_output.get("name")) if isinstance(raw_output, dict) else output_key
    output_type = _as_text(raw_output.get("type")) if isinstance(raw_output, dict) else ("json" if isinstance(raw_output, (dict, list)) else "text")
    lines = [
        f"Capability: {_source_name(package)}",
        f"source_type: {_source_type(package)}",
        f"source_key: {_source_key(package)}",
        f"status: {_as_text(package.get('status')) or 'unknown'}",
        f"output: {output_key}",
    ]
    if output_name and output_name != output_key:
        lines.append(f"name: {output_name}")
    if output_type:
        lines.append(f"type: {output_type}")
    if rendered_value:
        lines.append(rendered_value)
    return "\n".join(lines)


def _source_ref_from_output(
    package: dict[str, Any],
    *,
    output_key: str,
    raw_output: Any,
    output_text: str,
    run_id: str,
    state_key: str,
    ordinal: int,
) -> dict[str, Any]:
    content_hash = _put_output_blob(output_text, package=package, output_key=output_key, run_id=run_id, state_key=state_key)
    output_name = _as_text(raw_output.get("name")) if isinstance(raw_output, dict) else output_key
    output_type = _as_text(raw_output.get("type")) if isinstance(raw_output, dict) else ("json" if isinstance(raw_output, (dict, list)) else "text")
    source_key = _source_key(package)
    source_type = _source_type(package)
    source_id = ":".join(
        part
        for part in [run_id, state_key, source_type, source_key, output_key]
        if part
    ) or f"{source_type}:{source_key}:{output_key}"
    return {
        "source_kind": "capability_result_output",
        "source_id": source_id,
        "source_content_hash": content_hash,
        "label": output_name or output_key,
        "ordinal": ordinal,
        "metadata": {
            "run_id": run_id,
            "state_key": state_key,
            "output_key": output_key,
            "output_name": output_name or output_key,
            "output_type": output_type,
            "source_type": source_type,
            "source_key": source_key,
            "source_name": _source_name(package),
            "status": _as_text(package.get("status")),
        },
    }


def _build_context_ref(
    *,
    source_refs: list[dict[str, Any]],
    result_package: dict[str, Any],
    run_id: str,
    state_key: str,
    max_chars: int,
    rendered_text: str,
) -> dict[str, Any]:
    if not source_refs:
        return _empty_context_ref()
    try:
        from app.core.storage.context_assembly_store import create_context_assembly

        return create_context_assembly(
            target_state_key="capability_context",
            renderer_key="capability_context",
            renderer_version="1",
            rendered_text=rendered_text,
            sources=source_refs,
            budget={"max_chars": max_chars},
            metadata={
                "scope": "capability",
                "run_id": run_id,
                "state_key": state_key,
                "source_type": _source_type(result_package),
                "source_key": _source_key(result_package),
            },
        )
    except Exception:
        source_key = [[ref.get("source_kind"), ref.get("source_id"), ref.get("source_content_hash")] for ref in source_refs]
        key = json.dumps({"source_refs": source_key, "max_chars": max_chars}, ensure_ascii=False, sort_keys=True)
        return {
            "kind": "context_assembly_ref",
            "assembly_id": f"ctx_capability_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}",
            "target_state_key": "capability_context",
            "renderer_key": "capability_context",
            "renderer_version": "1",
            "rendered_content_hash": _content_hash(rendered_text) if rendered_text else "",
            "source_count": len(source_refs),
            "source_refs": source_refs,
            "budget": {"max_chars": max_chars},
            "metadata": {"scope": "capability", "run_id": run_id, "state_key": state_key},
        }


def _build_context_package(
    *,
    result_package: dict[str, Any],
    source_refs: list[dict[str, Any]],
    context_ref: dict[str, Any],
    run_id: str,
    state_key: str,
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
                "state_key": state_key,
                "output_key": _as_text(_coerce_dict(ref.get("metadata")).get("output_key")),
                "output_type": _as_text(_coerce_dict(ref.get("metadata")).get("output_type")),
                "source_type": _source_type(result_package),
                "source_key": _source_key(result_package),
                "source_name": _source_name(result_package),
                "status": _as_text(result_package.get("status")),
            },
        }
        for ref in source_refs
    ]
    return {
        "kind": "context_package",
        "package_id": _context_package_id(context_ref),
        "source_kind": "capability",
        "authority": "evidence",
        "title": "Capability context",
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
            "renderer_key": "capability_context",
            "renderer_version": "1",
            "run_id": run_id,
            "state_key": state_key,
            "source_type": _source_type(result_package),
            "source_key": _source_key(result_package),
            "source_name": _source_name(result_package),
            "status": _as_text(result_package.get("status")),
        },
    }


def _empty_package(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "context_package",
        "package_id": "pkg_capability_empty",
        "source_kind": "capability",
        "authority": "evidence",
        "title": "Capability context",
        "items": [],
        "source_refs": [],
        "source_count": 0,
        "context_ref": _empty_context_ref(),
        "budget": {"source_chars": 0, "used_chars": 0, "omitted_count": 0},
        "warnings": warnings,
        "metadata": {"renderer_key": "capability_context", "renderer_version": "1"},
    }


def _empty_context_ref() -> dict[str, Any]:
    return {
        "kind": "context_assembly_ref",
        "assembly_id": "ctx_capability_empty",
        "target_state_key": "capability_context",
        "renderer_key": "capability_context",
        "renderer_version": "1",
        "rendered_content_hash": "",
        "source_count": 0,
        "source_refs": [],
    }


def _put_output_blob(
    output_text: str,
    *,
    package: dict[str, Any],
    output_key: str,
    run_id: str,
    state_key: str,
) -> str:
    try:
        from app.core.storage.content_blob_store import put_content_blob

        blob = put_content_blob(
            output_text,
            "text/plain",
            {
                "kind": "capability_result_output",
                "run_id": run_id,
                "state_key": state_key,
                "output_key": output_key,
                "source_type": _source_type(package),
                "source_key": _source_key(package),
            },
        )
        return _as_text(blob.get("content_hash"))
    except Exception:
        return _content_hash(output_text)


def _coerce_result_package(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("kind") == "result_package":
        return value
    raise ValueError("capability_context_loader requires a result_package.")


def _source_type(package: dict[str, Any]) -> str:
    return _as_text(package.get("sourceType") or package.get("source_type") or "capability")


def _source_key(package: dict[str, Any]) -> str:
    return _as_text(package.get("sourceKey") or package.get("source_key"))


def _source_name(package: dict[str, Any]) -> str:
    return _as_text(package.get("sourceName") or package.get("source_name") or _source_key(package) or "Capability")


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
    return "pkg_capability_empty"


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


if __name__ == "__main__":
    print(json.dumps(capability_context_loader(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
