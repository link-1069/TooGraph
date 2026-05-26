from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


DEFAULT_MAX_MESSAGES = 12
DEFAULT_MAX_CHARS = 4000
DEFAULT_SUMMARY_PLACEHOLDERS = {"当前对话尚未形成摘要。"}


def buddy_history_context_loader(payload: dict[str, Any] | None, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    runtime_context = _resolve_runtime_context(inputs=inputs, explicit_context=context)
    session_id = _text(
        runtime_context.get("buddy_session_id")
        or runtime_context.get("current_session_id")
        or inputs.get("buddy_session_id")
        or inputs.get("current_session_id")
    )
    current_message_id = _text(
        runtime_context.get("buddy_current_message_id")
        or runtime_context.get("current_message_id")
        or inputs.get("buddy_current_message_id")
        or inputs.get("current_message_id")
    )
    source_run_id = _resolve_source_run_id(inputs=inputs, runtime_context=runtime_context, explicit_context=context)
    max_messages = _bounded_int(inputs.get("max_messages"), default=DEFAULT_MAX_MESSAGES, minimum=1, maximum=50)
    max_chars = _bounded_int(inputs.get("max_chars"), default=DEFAULT_MAX_CHARS, minimum=256, maximum=50000)

    if not session_id:
        warnings = [_warning("missing_buddy_session", "No Buddy session runtime context was available.")]
        context_ref = _build_context_ref(
            session_id="",
            current_message_id=current_message_id,
            source_refs=[],
            max_messages=max_messages,
            max_chars=max_chars,
            scope="standalone_run",
        )
        return {
            "status": "succeeded",
            "conversation_history": _build_context_package(
                session_id="",
                current_message_id=current_message_id,
                context_ref=context_ref,
                source_refs=[],
                max_messages=max_messages,
                max_chars=max_chars,
                source_chars=0,
                used_chars=0,
                omitted_count=0,
                warnings=warnings,
            ),
            "existing_session_summary": "",
            "current_session_id": "",
            "source_run_id": source_run_id,
            "history_context_report": _build_report(
                scope="standalone_run",
                session_id="",
                current_message_id=current_message_id,
                source_run_id=source_run_id,
                source_refs=[],
                max_messages=max_messages,
                max_chars=max_chars,
                warning="No Buddy session runtime context was available.",
                omitted_count=0,
                omitted_reason="",
            ),
        }

    try:
        _ensure_backend_path()
        from app.buddy.store import list_chat_messages, load_session_summary

        messages = list_chat_messages(session_id)
        session_summary = load_session_summary()
    except Exception as exc:
        warning = _warning("history_load_failed", str(exc))
        context_ref = _build_context_ref(
            session_id=session_id,
            current_message_id=current_message_id,
            source_refs=[],
            max_messages=max_messages,
            max_chars=max_chars,
            scope="load_failed",
        )
        return {
            "status": "failed",
            "error_type": "history_load_failed",
            "error": str(exc),
            "conversation_history": _build_context_package(
                session_id=session_id,
                current_message_id=current_message_id,
                context_ref=context_ref,
                source_refs=[],
                max_messages=max_messages,
                max_chars=max_chars,
                source_chars=0,
                used_chars=0,
                omitted_count=0,
                warnings=[warning],
            ),
            "existing_session_summary": "",
            "current_session_id": session_id,
            "source_run_id": source_run_id,
            "history_context_report": _build_report(
                scope="load_failed",
                session_id=session_id,
                current_message_id=current_message_id,
                source_run_id=source_run_id,
                source_refs=[],
                max_messages=max_messages,
                max_chars=max_chars,
                warning=str(exc),
                omitted_count=0,
                omitted_reason="",
            ),
        }

    visible_messages = _visible_messages_before_current(messages, current_message_id=current_message_id)
    selected_messages = _select_recent_visible_messages(visible_messages, max_messages=max_messages, max_chars=max_chars)
    omitted_count = max(0, len(visible_messages) - len(selected_messages))
    omitted_reason = _resolve_omitted_reason(
        visible_messages=visible_messages,
        selected_messages=selected_messages,
        max_messages=max_messages,
        max_chars=max_chars,
    )
    source_refs = _build_source_refs(selected_messages)
    summary_content = _text(session_summary.get("content") if isinstance(session_summary, dict) else "")
    if summary_content in DEFAULT_SUMMARY_PLACEHOLDERS:
        summary_content = ""
    if summary_content:
        source_refs.insert(
            0,
            {
                "source_kind": "buddy_session_summary",
                "source_id": "session_summary",
                "role": "summary",
                "ordinal": 0,
            },
        )
        source_refs = [{**ref, "ordinal": index} for index, ref in enumerate(source_refs)]

    ref = _build_context_ref(
        session_id=session_id,
        current_message_id=current_message_id,
        source_refs=source_refs,
        max_messages=max_messages,
        max_chars=max_chars,
        scope="buddy_session",
    )
    rendered_text = _render_history_text(summary_content=summary_content, messages=selected_messages)
    source_chars = len(summary_content) + _messages_char_count(visible_messages)
    return {
        "status": "succeeded",
        "conversation_history": _build_context_package(
            session_id=session_id,
            current_message_id=current_message_id,
            context_ref=ref,
            source_refs=source_refs,
            max_messages=max_messages,
            max_chars=max_chars,
            source_chars=source_chars,
            used_chars=len(rendered_text),
            omitted_count=omitted_count,
            warnings=[],
        ),
        "existing_session_summary": summary_content,
        "current_session_id": session_id,
        "source_run_id": source_run_id,
        "history_context_report": _build_report(
            scope="buddy_session",
            session_id=session_id,
            current_message_id=current_message_id,
            source_run_id=source_run_id,
            source_refs=source_refs,
            max_messages=max_messages,
            max_chars=max_chars,
            warning="",
            omitted_count=omitted_count,
            omitted_reason=omitted_reason,
        ),
    }


def _resolve_runtime_context(*, inputs: dict[str, Any], explicit_context: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(explicit_context, dict):
        nested = explicit_context.get("runtime_context")
        action_nested = explicit_context.get("action_runtime_context")
        if isinstance(nested, dict):
            return nested
        if isinstance(action_nested, dict):
            return action_nested
        return explicit_context
    env_context = _read_json_env("TOOGRAPH_ACTION_RUNTIME_CONTEXT")
    if env_context:
        return env_context
    file_path = _text(os.environ.get("TOOGRAPH_ACTION_RUNTIME_CONTEXT_FILE"))
    if file_path:
        try:
            value = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except Exception:
            value = {}
        if isinstance(value, dict):
            return value
    input_context = inputs.get("runtime_context")
    return input_context if isinstance(input_context, dict) else {}


def _resolve_source_run_id(
    *,
    inputs: dict[str, Any],
    runtime_context: dict[str, Any],
    explicit_context: dict[str, Any] | None,
) -> str:
    if isinstance(explicit_context, dict):
        explicit_run_id = _text(explicit_context.get("run_id"))
        if explicit_run_id:
            return explicit_run_id
    return _text(inputs.get("source_run_id") or runtime_context.get("source_run_id") or runtime_context.get("run_id"))


def _read_json_env(key: str) -> dict[str, Any]:
    raw = _text(os.environ.get(key))
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _visible_messages_before_current(
    messages: list[dict[str, Any]],
    *,
    current_message_id: str,
) -> list[dict[str, Any]]:
    visible = [
        message
        for message in messages
        if message.get("include_in_context", True) is not False and _text(message.get("content"))
    ]
    if current_message_id:
        current_index = next(
            (index for index, message in enumerate(visible) if _text(message.get("message_id")) == current_message_id),
            -1,
        )
        if current_index >= 0:
            visible = visible[:current_index]
    return visible


def _select_recent_visible_messages(
    visible: list[dict[str, Any]],
    *,
    max_messages: int,
    max_chars: int,
) -> list[dict[str, Any]]:
    selected = visible[-max_messages:]
    while len(selected) > 1 and _messages_char_count(selected) > max_chars:
        selected = selected[1:]
    return selected


def _resolve_omitted_reason(
    *,
    visible_messages: list[dict[str, Any]],
    selected_messages: list[dict[str, Any]],
    max_messages: int,
    max_chars: int,
) -> str:
    if len(visible_messages) == len(selected_messages):
        return ""
    reasons: list[str] = []
    if len(visible_messages) > max_messages:
        reasons.append("message_limit")
    if _messages_char_count(visible_messages[-max_messages:]) > max_chars:
        reasons.append("char_budget")
    return ",".join(reasons) or "history_budget"


def _build_source_refs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for message in messages:
        refs.append(
            {
                "source_kind": "buddy_message",
                "source_id": _text(message.get("message_id")),
                "role": _text(message.get("role")),
                "ordinal": len(refs),
            }
        )
    return refs


def _build_context_ref(
    *,
    session_id: str,
    current_message_id: str,
    source_refs: list[dict[str, Any]],
    max_messages: int,
    max_chars: int,
    scope: str,
) -> dict[str, Any]:
    source_key = [
        [ref.get("source_kind"), ref.get("source_id"), ref.get("role"), ref.get("ordinal")]
        for ref in source_refs
    ]
    assembly_key = json.dumps(
        {
            "session_id": session_id,
            "current_message_id": current_message_id,
            "source_refs": source_key,
            "max_messages": max_messages,
            "max_chars": max_chars,
            "scope": scope,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assembly_hash = hashlib.sha256(assembly_key.encode("utf-8")).hexdigest()[:16]
    preview = "no buddy session history" if not source_refs else f"context assembly sources: {len(source_refs)}"
    return {
        "kind": "context_assembly_ref",
        "assembly_id": f"ctx_buddy_history_{assembly_hash}",
        "target_state_key": "conversation_history",
        "renderer_key": "buddy_history",
        "renderer_version": "1",
        "rendered_content_hash": "",
        "source_count": len(source_refs),
        "source_refs": source_refs,
        "budget": {
            "max_messages": max_messages,
            "max_chars": max_chars,
        },
        "metadata": {
            "scope": scope,
            "current_session_id": session_id,
            "current_message_id": current_message_id,
        },
        "preview": preview,
    }


def _build_context_package(
    *,
    session_id: str,
    current_message_id: str,
    context_ref: dict[str, Any],
    source_refs: list[dict[str, Any]],
    max_messages: int,
    max_chars: int,
    source_chars: int,
    used_chars: int,
    omitted_count: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "context_package",
        "package_id": _context_package_id(context_ref),
        "source_kind": "session",
        "authority": "history",
        "title": "Buddy conversation history",
        "items": _build_context_package_items(source_refs),
        "source_refs": source_refs,
        "source_count": len(source_refs),
        "context_ref": context_ref,
        "budget": {
            "max_messages": max_messages,
            "max_chars": max_chars,
            "source_chars": source_chars,
            "used_chars": used_chars,
            "omitted_count": omitted_count,
        },
        "warnings": warnings,
        "metadata": {
            "current_session_id": session_id,
            "current_message_id": current_message_id,
            "renderer_key": "buddy_history",
            "renderer_version": "1",
        },
    }


def _context_package_id(context_ref: dict[str, Any]) -> str:
    assembly_id = _text(context_ref.get("assembly_id"))
    if assembly_id.startswith("ctx_"):
        return f"pkg_{assembly_id[4:]}"
    return f"pkg_{assembly_id or 'buddy_history'}"


def _build_context_package_items(source_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source_ref in source_refs:
        source_id = _text(source_ref.get("source_id"))
        source_kind = _text(source_ref.get("source_kind"))
        role = _text(source_ref.get("role"))
        title = "已有会话摘要" if source_kind == "buddy_session_summary" else _message_title(role)
        items.append(
            {
                "id": source_id,
                "title": title,
                "source_ref": source_ref,
                "metadata": {
                    "source_kind": source_kind,
                    "role": role,
                    "ordinal": source_ref.get("ordinal"),
                },
            }
        )
    return items


def _message_title(role: str) -> str:
    if role == "user":
        return "用户消息"
    if role == "assistant":
        return "伙伴消息"
    return "会话消息"


def _build_report(
    *,
    scope: str,
    session_id: str,
    current_message_id: str,
    source_run_id: str,
    source_refs: list[dict[str, Any]],
    max_messages: int,
    max_chars: int,
    warning: str,
    omitted_count: int,
    omitted_reason: str,
) -> dict[str, Any]:
    message_ids = [
        _text(ref.get("source_id"))
        for ref in source_refs
        if ref.get("source_kind") == "buddy_message" and _text(ref.get("source_id"))
    ]
    summary_ids = [
        _text(ref.get("source_id"))
        for ref in source_refs
        if ref.get("source_kind") == "buddy_session_summary" and _text(ref.get("source_id"))
    ]
    return {
        "scope": scope,
        "session_id": session_id,
        "current_message_id": current_message_id,
        "source_run_id": source_run_id,
        "source_count": len(source_refs),
        "source_refs": source_refs,
        "message_ids": message_ids,
        "summary_ids": summary_ids,
        "omitted_count": omitted_count,
        "omitted_reason": omitted_reason,
        "lineage": {
            "current_session_id": session_id,
            "current_message_id": current_message_id,
            "source_run_id": source_run_id,
        },
        "max_messages": max_messages,
        "max_chars": max_chars,
        "warning": warning,
    }


def _render_history_text(*, summary_content: str, messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if summary_content:
        lines.append("已有会话摘要:")
        lines.append(summary_content)
    for message in messages:
        role = _text(message.get("role"))
        content = _text(message.get("content"))
        if content:
            lines.append(_format_history_line(role, content))
    return "\n".join(lines)


def _format_history_line(role: str, content: str) -> str:
    label = "用户" if role == "user" else "伙伴" if role == "assistant" else "消息"
    return f"{label}: {content.strip()}"


def _warning(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _messages_char_count(messages: list[dict[str, Any]]) -> int:
    return sum(len(_text(message.get("content"))) for message in messages)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _ensure_backend_path() -> None:
    repo_root = Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


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
    print(json.dumps(buddy_history_context_loader(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
