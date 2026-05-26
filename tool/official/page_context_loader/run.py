from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_MAX_CHARS = 12000


def page_context_loader(payload: dict[str, Any] | None, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        page_operation_context = _resolve_page_operation_context(inputs=inputs, explicit_context=context)
        page_context_text = _as_text(inputs.get("page_context"))
        operation_result = _coerce_dict(inputs.get("operation_result"))
        operation_report = _coerce_dict(inputs.get("operation_report"))
        run_id = _resolve_source_run_id(inputs=inputs, page_operation_context=page_operation_context, explicit_context=context)
        max_chars = _bounded_int(inputs.get("max_chars"), default=DEFAULT_MAX_CHARS, minimum=512, maximum=120000)

        rendered_text, source_refs, used_chars, source_chars, omitted_count, warnings = _render_page_context(
            page_operation_context,
            page_context_text=page_context_text,
            operation_result=operation_result,
            operation_report=operation_report,
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
            "page_context_package": package,
            "page_context_report": {
                "scope": "page",
                "run_id": run_id,
                "sections": [_as_text(_coerce_dict(ref.get("metadata")).get("section")) for ref in source_refs],
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
        warning = _warning("page_context_load_failed", str(exc))
        return {
            "status": "failed",
            "error_type": "page_context_load_failed",
            "error": str(exc),
            "page_context_package": _empty_package([warning]),
            "page_context_report": {
                "scope": "page",
                "source_refs": [],
                "source_count": 0,
                "warnings": [warning],
            },
        }


def _render_page_context(
    page_operation_context: dict[str, Any],
    *,
    page_context_text: str,
    operation_result: dict[str, Any],
    operation_report: dict[str, Any],
    run_id: str,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]], int, int, int, list[dict[str, Any]]]:
    sections = _build_sections(
        page_operation_context,
        page_context_text=page_context_text,
        operation_result=operation_result,
        operation_report=operation_report,
    )
    rendered_sections: list[str] = []
    source_refs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    used_chars = 0
    source_chars = 0
    omitted_count = 0
    for section_id, title, content in sections:
        section_text = content.strip()
        if not section_text:
            continue
        source_chars += len(section_text)
        separator = "\n\n" if rendered_sections else ""
        remaining = max_chars - used_chars
        if remaining <= 0:
            omitted_count += 1
            continue
        section_with_separator = f"{separator}{section_text}"
        if len(section_with_separator) > remaining:
            section_with_separator = section_with_separator[: max(0, remaining)] + "\n[Page context omitted by max_chars budget.]"
            omitted_count += 1
        used_chars += len(section_with_separator)
        rendered_sections.append(section_with_separator if not separator else section_with_separator[len(separator):])
        source_refs.append(
            _source_ref_from_section(
                section_id=section_id,
                title=title,
                content=section_text,
                run_id=run_id,
                ordinal=len(source_refs),
            )
        )
    if not source_refs:
        warnings.append(_warning("empty_page_context", "No page context sections were available."))
    return "\n\n".join(rendered_sections), source_refs, used_chars, source_chars, omitted_count, warnings


def _build_sections(
    page_operation_context: dict[str, Any],
    *,
    page_context_text: str,
    operation_result: dict[str, Any],
    operation_report: dict[str, Any],
) -> list[tuple[str, str, str]]:
    book = _coerce_dict(page_operation_context.get("page_operation_book"))
    if not book and ("allowedOperations" in page_operation_context or "inputs" in page_operation_context):
        book = page_operation_context
    page = _coerce_dict(book.get("page"))
    page_path = _as_text(page.get("path") or page_operation_context.get("page_path"))
    page_title = _as_text(page.get("title")) or "Current page"
    snapshot_id = _as_text(page.get("snapshotId") or page.get("snapshot_id"))
    sections: list[tuple[str, str, str]] = []
    if page_path or page_title or snapshot_id:
        lines = [f"Page: {page_title}"]
        if page_path:
            lines.append(f"path: {page_path}")
        if snapshot_id:
            lines.append(f"snapshot_id: {snapshot_id}")
        sections.append(("page", "Page", "\n".join(lines)))
    if page_context_text:
        sections.append(("page_context", "Page context", f"Page context:\n{page_context_text}"))
    allowed_operations = _render_operations("Allowed operations", book.get("allowedOperations"))
    if allowed_operations:
        sections.append(("allowed_operations", "Allowed operations", allowed_operations))
    inputs = _render_operations("Inputs", book.get("inputs"))
    if inputs:
        sections.append(("inputs", "Inputs", inputs))
    unavailable = _render_operations("Unavailable targets", book.get("unavailable"))
    if unavailable:
        sections.append(("unavailable", "Unavailable targets", unavailable))
    page_facts = _coerce_dict(page_operation_context.get("page_facts"))
    if page_facts:
        sections.append(("page_facts", "Page facts", "Page facts:\n" + _stringify(page_facts)))
    if operation_result:
        sections.append(("operation_result", "Operation result", "Operation result:\n" + _stringify(operation_result)))
    if operation_report:
        sections.append(("operation_report", "Operation report", "Operation report:\n" + _stringify(operation_report)))
    return sections


def _render_operations(title: str, value: Any) -> str:
    records = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    if not records:
        return ""
    lines = [f"{title}:"]
    for record in records:
        target_id = _as_text(record.get("targetId") or record.get("target_id"))
        label = _as_text(record.get("label"))
        role = _as_text(record.get("role"))
        commands = _list_text(record.get("commands"))
        line = f"- {target_id or label or 'target'}"
        if label and label != target_id:
            line += f" ({label})"
        if role:
            line += f" role={role}"
        if commands:
            line += f" commands: {', '.join(commands)}"
        lines.append(line)
    return "\n".join(lines)


def _source_ref_from_section(*, section_id: str, title: str, content: str, run_id: str, ordinal: int) -> dict[str, Any]:
    content_hash = _put_section_blob(content, section_id=section_id, run_id=run_id)
    source_id = ":".join(part for part in [run_id, section_id] if part) or f"page:{section_id}"
    return {
        "source_kind": "page_context_item",
        "source_id": source_id,
        "source_content_hash": content_hash,
        "label": title,
        "ordinal": ordinal,
        "metadata": {
            "run_id": run_id,
            "section": section_id,
            "title": title,
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
            target_state_key="page_context_package",
            renderer_key="page_context",
            renderer_version="1",
            rendered_text=rendered_text,
            sources=source_refs,
            budget={"max_chars": max_chars},
            metadata={"scope": "page", "run_id": run_id},
        )
    except Exception:
        source_key = [[ref.get("source_kind"), ref.get("source_id"), ref.get("source_content_hash")] for ref in source_refs]
        key = json.dumps({"source_refs": source_key, "max_chars": max_chars}, ensure_ascii=False, sort_keys=True)
        return {
            "kind": "context_assembly_ref",
            "assembly_id": f"ctx_page_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}",
            "target_state_key": "page_context_package",
            "renderer_key": "page_context",
            "renderer_version": "1",
            "rendered_content_hash": _content_hash(rendered_text) if rendered_text else "",
            "source_count": len(source_refs),
            "source_refs": source_refs,
            "budget": {"max_chars": max_chars},
            "metadata": {"scope": "page", "run_id": run_id},
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
                "section": _as_text(_coerce_dict(ref.get("metadata")).get("section")),
                "title": _as_text(_coerce_dict(ref.get("metadata")).get("title")),
            },
        }
        for ref in source_refs
    ]
    return {
        "kind": "context_package",
        "package_id": _context_package_id(context_ref),
        "source_kind": "page",
        "authority": "context_only",
        "title": "Page context",
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
            "renderer_key": "page_context",
            "renderer_version": "1",
            "run_id": run_id,
        },
    }


def _empty_package(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "context_package",
        "package_id": "pkg_page_empty",
        "source_kind": "page",
        "authority": "context_only",
        "title": "Page context",
        "items": [],
        "source_refs": [],
        "source_count": 0,
        "context_ref": _empty_context_ref(),
        "budget": {"source_chars": 0, "used_chars": 0, "omitted_count": 0},
        "warnings": warnings,
        "metadata": {"renderer_key": "page_context", "renderer_version": "1"},
    }


def _empty_context_ref() -> dict[str, Any]:
    return {
        "kind": "context_assembly_ref",
        "assembly_id": "ctx_page_empty",
        "target_state_key": "page_context_package",
        "renderer_key": "page_context",
        "renderer_version": "1",
        "rendered_content_hash": "",
        "source_count": 0,
        "source_refs": [],
    }


def _put_section_blob(content: str, *, section_id: str, run_id: str) -> str:
    try:
        from app.core.storage.content_blob_store import put_content_blob

        blob = put_content_blob(
            content,
            "text/plain",
            {
                "kind": "page_context_item",
                "run_id": run_id,
                "section": section_id,
            },
        )
        return _as_text(blob.get("content_hash"))
    except Exception:
        return _content_hash(content)


def _resolve_page_operation_context(*, inputs: dict[str, Any], explicit_context: dict[str, Any] | None) -> dict[str, Any]:
    input_context = inputs.get("page_operation_context")
    if isinstance(input_context, dict):
        return input_context
    if isinstance(explicit_context, dict):
        action_runtime_context = explicit_context.get("action_runtime_context")
        runtime_context = explicit_context.get("runtime_context")
        if isinstance(action_runtime_context, dict):
            return action_runtime_context
        if isinstance(runtime_context, dict):
            return runtime_context
    return {}


def _resolve_source_run_id(
    *,
    inputs: dict[str, Any],
    page_operation_context: dict[str, Any],
    explicit_context: dict[str, Any] | None,
) -> str:
    if isinstance(explicit_context, dict):
        explicit_run_id = _as_text(explicit_context.get("run_id"))
        if explicit_run_id:
            return explicit_run_id
    return _as_text(inputs.get("source_run_id") or page_operation_context.get("source_run_id") or page_operation_context.get("run_id"))


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
    return "pkg_page_empty"


def _content_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _warning(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_text(item) for item in value if _as_text(item)]


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
    print(json.dumps(page_context_loader(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
