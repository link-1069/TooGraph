from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_LIMIT = 5
DEFAULT_WINDOW = 2
DEFAULT_BOOKEND = 1
DEFAULT_MAX_CHARS = 8000


def session_search_context_loader(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        from app.buddy.store import recall_chat_messages

        query = _as_text(inputs.get("query"))
        limit = _bounded_int(inputs.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=20)
        window = _bounded_int(inputs.get("window"), default=DEFAULT_WINDOW, minimum=0, maximum=10)
        bookend = _bounded_int(inputs.get("bookend"), default=DEFAULT_BOOKEND, minimum=0, maximum=10)
        max_chars = _bounded_int(inputs.get("max_chars"), default=DEFAULT_MAX_CHARS, minimum=512, maximum=50000)
        current_session_id = _as_text(inputs.get("current_session_id"))
        sort = _as_text(inputs.get("sort")) or "rank"
        role_filter = inputs.get("role_filter")

        if not query:
            warning = _warning("missing_query", "Session search query is required.")
            context_ref = _empty_context_ref()
            package = _build_context_package(
                query=query,
                source_refs=[],
                context_ref=context_ref,
                sessions=[],
                max_chars=max_chars,
                source_chars=0,
                used_chars=0,
                omitted_count=0,
                warnings=[warning],
            )
            return {
                "status": "succeeded",
                "session_search_context": package,
                "session_search_report": _build_report(
                    query=query,
                    sessions=[],
                    source_refs=[],
                    max_chars=max_chars,
                    source_chars=0,
                    used_chars=0,
                    omitted_count=0,
                    warnings=[warning],
                ),
            }

        result = recall_chat_messages(
            mode="discover",
            query=query,
            limit=limit,
            window=window,
            bookend=bookend,
            sort=sort,
            role_filter=role_filter,
            current_session_id=current_session_id,
        )
        sessions = _list_records(result.get("sessions"))
        rendered_text, source_refs, source_chars, used_chars, omitted_count = _render_search_context(
            query=query,
            sessions=sessions,
            max_chars=max_chars,
        )
        context_ref = _build_context_ref(
            query=query,
            current_session_id=current_session_id,
            source_refs=source_refs,
            max_chars=max_chars,
            rendered_text=rendered_text,
        )
        package = _build_context_package(
            query=query,
            source_refs=source_refs,
            context_ref=context_ref,
            sessions=sessions,
            max_chars=max_chars,
            source_chars=source_chars,
            used_chars=used_chars,
            omitted_count=omitted_count,
            warnings=[],
        )
        return {
            "status": "succeeded",
            "session_search_context": package,
            "session_search_report": _build_report(
                query=query,
                sessions=sessions,
                source_refs=source_refs,
                max_chars=max_chars,
                source_chars=source_chars,
                used_chars=used_chars,
                omitted_count=omitted_count,
                warnings=[],
            ),
        }
    except Exception as exc:
        warning = _warning("session_search_context_load_failed", str(exc))
        return {
            "status": "failed",
            "error_type": "session_search_context_load_failed",
            "error": str(exc),
            "session_search_context": _empty_package([warning]),
            "session_search_report": {
                "scope": "session_search",
                "source_refs": [],
                "source_count": 0,
                "warnings": [warning],
            },
        }


def _render_search_context(
    *,
    query: str,
    sessions: list[dict[str, Any]],
    max_chars: int,
) -> tuple[str, list[dict[str, Any]], int, int, int]:
    sections: list[str] = []
    source_refs: list[dict[str, Any]] = []
    source_chars = 0
    used_chars = 0
    omitted_count = 0
    seen_messages: set[str] = set()
    for session in sessions:
        session_id = _as_text(session.get("session_id"))
        title = _as_text(session.get("title")) or session_id
        lineage_root = _as_text(session.get("lineage_root_session_id") or session.get("parent_session_id") or session_id)
        session_lines = [
            f"Session: {title}",
            f"session_id: {session_id}",
            f"lineage_root_session_id: {lineage_root}",
        ]
        snippet = _as_text(session.get("snippet"))
        if snippet:
            session_lines.append(f"hit_snippet: {snippet}")
        for message in _session_messages(session):
            message_id = _as_text(message.get("message_id"))
            content = _as_text(message.get("content"))
            if not message_id or not content or message_id in seen_messages:
                continue
            seen_messages.add(message_id)
            role = _as_text(message.get("role"))
            session_lines.append(_format_history_line(role, content))
            source_refs.append(
                {
                    "source_kind": "buddy_message",
                    "source_id": message_id,
                    "role": role,
                    "label": title,
                    "ordinal": len(source_refs),
                    "metadata": {
                        "query": query,
                        "session_id": session_id,
                        "session_title": title,
                        "lineage_root_session_id": lineage_root,
                        "created_at": _as_text(message.get("created_at")),
                        "hit": message_id in set(_list_text(session.get("hit_message_ids"))),
                    },
                }
            )
        section = "\n".join(session_lines).strip()
        if not section:
            continue
        source_chars += len(section)
        separator = "\n\n" if sections else ""
        remaining = max_chars - used_chars
        if remaining <= 0:
            omitted_count += 1
            continue
        section_with_separator = f"{separator}{section}"
        if len(section_with_separator) > remaining:
            section_with_separator = section_with_separator[: max(0, remaining)] + "\n[Session search context omitted by max_chars budget.]"
            omitted_count += 1
        used_chars += len(section_with_separator)
        sections.append(section_with_separator if not separator else section_with_separator[len(separator):])
    return "\n\n".join(sections), source_refs, source_chars, used_chars, omitted_count


def _session_messages(session: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for key in ("bookend_start", "messages", "bookend_end"):
        messages.extend(_list_records(session.get(key)))
    return messages


def _build_context_ref(
    *,
    query: str,
    current_session_id: str,
    source_refs: list[dict[str, Any]],
    max_chars: int,
    rendered_text: str,
) -> dict[str, Any]:
    if not source_refs:
        return _empty_context_ref()
    try:
        from app.core.storage.context_assembly_store import create_context_assembly

        return create_context_assembly(
            target_state_key="session_search_context",
            renderer_key="session_search",
            renderer_version="1",
            rendered_text=rendered_text,
            sources=source_refs,
            budget={"max_chars": max_chars},
            metadata={
                "scope": "session_search",
                "query": query,
                "current_session_id": current_session_id,
            },
        )
    except Exception:
        source_key = [[ref.get("source_kind"), ref.get("source_id"), ref.get("role")] for ref in source_refs]
        key = json.dumps({"source_refs": source_key, "query": query, "max_chars": max_chars}, ensure_ascii=False, sort_keys=True)
        return {
            "kind": "context_assembly_ref",
            "assembly_id": f"ctx_session_search_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}",
            "target_state_key": "session_search_context",
            "renderer_key": "session_search",
            "renderer_version": "1",
            "rendered_content_hash": _content_hash(rendered_text) if rendered_text else "",
            "source_count": len(source_refs),
            "source_refs": source_refs,
            "budget": {"max_chars": max_chars},
            "metadata": {"scope": "session_search", "query": query, "current_session_id": current_session_id},
        }


def _build_context_package(
    *,
    query: str,
    source_refs: list[dict[str, Any]],
    context_ref: dict[str, Any],
    sessions: list[dict[str, Any]],
    max_chars: int,
    source_chars: int,
    used_chars: int,
    omitted_count: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    items = [
        {
            "id": _as_text(ref.get("source_id")),
            "title": _as_text(ref.get("label")) or "Session message",
            "source_ref": ref,
            "metadata": {
                "query": query,
                "session_id": _as_text(_coerce_dict(ref.get("metadata")).get("session_id")),
                "lineage_root_session_id": _as_text(_coerce_dict(ref.get("metadata")).get("lineage_root_session_id")),
                "role": _as_text(ref.get("role")),
                "hit": bool(_coerce_dict(ref.get("metadata")).get("hit")),
            },
        }
        for ref in source_refs
    ]
    return {
        "kind": "context_package",
        "package_id": _context_package_id(context_ref),
        "source_kind": "session",
        "authority": "history",
        "title": "Buddy session search",
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
            "renderer_key": "session_search",
            "renderer_version": "1",
            "query": query,
            "session_count": len(sessions),
        },
    }


def _build_report(
    *,
    query: str,
    sessions: list[dict[str, Any]],
    source_refs: list[dict[str, Any]],
    max_chars: int,
    source_chars: int,
    used_chars: int,
    omitted_count: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    message_ids = [_as_text(ref.get("source_id")) for ref in source_refs if _as_text(ref.get("source_id"))]
    return {
        "scope": "session_search",
        "query": query,
        "session_count": len(sessions),
        "source_count": len(source_refs),
        "message_ids": message_ids,
        "sessions": [
            {
                "session_id": _as_text(session.get("session_id")),
                "title": _as_text(session.get("title")),
                "lineage_root_session_id": _as_text(session.get("lineage_root_session_id") or session.get("parent_session_id") or session.get("session_id")),
                "hit_message_ids": _list_text(session.get("hit_message_ids")),
                "snippet": _as_text(session.get("snippet")),
            }
            for session in sessions
        ],
        "source_refs": source_refs,
        "max_chars": max_chars,
        "source_chars": source_chars,
        "used_chars": used_chars,
        "omitted_count": omitted_count,
        "warnings": warnings,
    }


def _empty_package(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "context_package",
        "package_id": "pkg_session_search_empty",
        "source_kind": "session",
        "authority": "history",
        "title": "Buddy session search",
        "items": [],
        "source_refs": [],
        "source_count": 0,
        "context_ref": _empty_context_ref(),
        "budget": {"source_chars": 0, "used_chars": 0, "omitted_count": 0},
        "warnings": warnings,
        "metadata": {"renderer_key": "session_search", "renderer_version": "1"},
    }


def _empty_context_ref() -> dict[str, Any]:
    return {
        "kind": "context_assembly_ref",
        "assembly_id": "ctx_session_search_empty",
        "target_state_key": "session_search_context",
        "renderer_key": "session_search",
        "renderer_version": "1",
        "rendered_content_hash": "",
        "source_count": 0,
        "source_refs": [],
    }


def _context_package_id(context_ref: dict[str, Any]) -> str:
    assembly_id = _as_text(context_ref.get("assembly_id"))
    if assembly_id.startswith("ctx_"):
        return f"pkg_{assembly_id[4:]}"
    if assembly_id:
        return f"pkg_{assembly_id}"
    return "pkg_session_search_empty"


def _format_history_line(role: str, content: str) -> str:
    label = "用户" if role == "user" else "伙伴" if role == "assistant" else "消息"
    return f"{label}: {content.strip()}"


def _ensure_backend_path() -> None:
    repo_root = Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _content_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _warning(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [_as_text(item) for item in value if _as_text(item)]


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


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
    print(json.dumps(session_search_context_loader(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
