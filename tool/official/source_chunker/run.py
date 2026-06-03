from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any


DEFAULT_MESSAGE_MAX_CHARS = 2400
DEFAULT_MESSAGE_MAX_TURNS = 3
DEFAULT_MESSAGE_OVERLAP = 0
DEFAULT_DOCUMENT_MAX_CHARS = 1800
DEFAULT_DOCUMENT_OVERLAP_CHARS = 200


def source_chunker(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    source_kind = _text(inputs.get("source_kind"))
    strategy = _text(inputs.get("strategy"))
    limits = _dict(inputs.get("limits"))
    source = _dict(inputs.get("source"))

    try:
        if source_kind == "buddy_messages":
            resolved_strategy = strategy or "conversation_turn_window"
            if resolved_strategy != "conversation_turn_window":
                return _failed("unsupported_strategy", f"Unsupported buddy_messages strategy: {resolved_strategy}")
            chunks, report = _chunk_buddy_messages(source, limits)
            return _succeeded(source_kind, resolved_strategy, chunks, report)

        if source_kind == "normalized_documents":
            resolved_strategy = strategy or "document_section_window"
            if resolved_strategy != "document_section_window":
                return _failed("unsupported_strategy", f"Unsupported normalized_documents strategy: {resolved_strategy}")
            chunks, report = _chunk_normalized_documents(source, limits)
            return _succeeded(source_kind, resolved_strategy, chunks, report)

        return _failed("unsupported_source_kind", f"Unsupported source_kind: {source_kind or '<empty>'}")
    except Exception as exc:
        return _failed("source_chunking_failed", str(exc), source_kind=source_kind, strategy=strategy)


def _chunk_buddy_messages(source: dict[str, Any], limits: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session_id = _text(source.get("session_id"))
    messages = _normalize_messages(source.get("messages"))
    max_chars = _bounded_int(limits.get("max_chars"), default=DEFAULT_MESSAGE_MAX_CHARS, minimum=200, maximum=20_000)
    max_turns = _bounded_int(
        limits.get("max_turns_per_chunk"),
        default=DEFAULT_MESSAGE_MAX_TURNS,
        minimum=1,
        maximum=20,
    )
    overlap_messages = _bounded_int(
        limits.get("overlap_messages"),
        default=DEFAULT_MESSAGE_OVERLAP,
        minimum=0,
        maximum=10,
    )
    turns = _message_turns(messages)
    chunks: list[dict[str, Any]] = []
    current_turns: list[list[dict[str, Any]]] = []
    previous_tail: list[dict[str, Any]] = []

    for turn in turns:
        candidate_turns = [*current_turns, turn]
        if current_turns and (
            len(candidate_turns) > max_turns
            or len(_format_messages(_flatten(candidate_turns))) > max_chars
        ):
            chunks.extend(
                _message_window_chunks(
                    session_id=session_id,
                    turns=current_turns,
                    overlap_prefix=previous_tail,
                    ordinal_start=len(chunks) + 1,
                    max_chars=max_chars,
                )
            )
            primary_messages = _flatten(current_turns)
            previous_tail = primary_messages[-overlap_messages:] if overlap_messages else []
            current_turns = [turn]
        else:
            current_turns = candidate_turns

    if current_turns:
        chunks.extend(
            _message_window_chunks(
                session_id=session_id,
                turns=current_turns,
                overlap_prefix=previous_tail,
                ordinal_start=len(chunks) + 1,
                max_chars=max_chars,
            )
        )

    return chunks, {
        "message_count": len(messages),
        "turn_count": len(turns),
        "max_chars": max_chars,
        "max_turns_per_chunk": max_turns,
        "overlap_messages": overlap_messages,
    }


def _message_window_chunks(
    *,
    session_id: str,
    turns: list[list[dict[str, Any]]],
    overlap_prefix: list[dict[str, Any]],
    ordinal_start: int,
    max_chars: int,
) -> list[dict[str, Any]]:
    primary_messages = _flatten(turns)
    messages = [*overlap_prefix, *primary_messages]
    formatted = _format_messages(messages)
    parts = _split_text(formatted, max_chars=max_chars, overlap_chars=0)
    chunks: list[dict[str, Any]] = []
    message_ids = [_text(message.get("message_id")) for message in messages if _text(message.get("message_id"))]
    primary_message_ids = [
        _text(message.get("message_id")) for message in primary_messages if _text(message.get("message_id"))
    ]
    overlap_message_ids = [
        _text(message.get("message_id")) for message in overlap_prefix if _text(message.get("message_id"))
    ]
    source_id = _message_window_source_id(session_id, message_ids)
    start_order = primary_messages[0]["client_order"] if primary_messages else 0
    end_order = primary_messages[-1]["client_order"] if primary_messages else 0
    roles = sorted({_text(message.get("role")) for message in messages if _text(message.get("role"))})
    for index, part in enumerate(parts, start=0):
        ordinal = ordinal_start + index
        content = part["content"]
        content_hash = _content_hash(content)
        chunk_id = _stable_id(
            "buddy_message_window",
            session_id,
            source_id,
            str(ordinal),
            ",".join(message_ids),
            content_hash,
        )
        chunks.append(
            {
                "chunk_id": chunk_id,
                "source_kind": "buddy_message_window",
                "source_id": source_id,
                "source_revision_id": "",
                "ordinal": ordinal,
                "title": f"Conversation window {ordinal}",
                "content": content,
                "content_hash": content_hash,
                "token_estimate": _estimate_tokens(content),
                "source_locator": {
                    "session_id": session_id,
                    "message_ids": message_ids,
                    "primary_message_ids": primary_message_ids,
                    "overlap_message_ids": overlap_message_ids,
                    "start_order": start_order,
                    "end_order": end_order,
                    "part_index": index,
                    "part_count": len(parts),
                },
                "metadata": {
                    "strategy": "conversation_turn_window",
                    "session_id": session_id,
                    "message_ids": message_ids,
                    "primary_message_ids": primary_message_ids,
                    "overlap_message_ids": overlap_message_ids,
                    "roles": roles,
                    "start_order": start_order,
                    "end_order": end_order,
                    "turn_count": len(turns),
                    "message_count": len(messages),
                },
            }
        )
    return chunks


def _chunk_normalized_documents(source: dict[str, Any], limits: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    documents = _normalize_documents(source.get("documents"))
    max_chars = _bounded_int(limits.get("max_chars"), default=DEFAULT_DOCUMENT_MAX_CHARS, minimum=80, maximum=50_000)
    overlap_chars = _bounded_int(
        limits.get("overlap_chars"),
        default=DEFAULT_DOCUMENT_OVERLAP_CHARS,
        minimum=0,
        maximum=max(0, max_chars // 2),
    )
    chunks: list[dict[str, Any]] = []
    for document in documents:
        text = _normalize_document_text(document["content"])
        parts = _split_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        for index, part in enumerate(parts, start=1):
            content = part["content"]
            content_hash = _content_hash(content)
            chunk_id = _stable_id(
                "normalized_document_chunk",
                document["document_id"],
                str(index),
                str(part["start_char"]),
                str(part["end_char"]),
                content_hash,
            )
            metadata = {
                **_dict(document.get("metadata")),
                "strategy": "document_section_window",
                "document_id": document["document_id"],
                "mime_type": document["mime_type"],
                "source_path": document["source_path"],
            }
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "source_kind": "normalized_document_chunk",
                    "source_id": document["document_id"],
                    "source_revision_id": _text(document.get("source_revision_id")),
                    "ordinal": index,
                    "title": document["title"] or document["document_id"],
                    "content": content,
                    "content_hash": content_hash,
                    "token_estimate": _estimate_tokens(content),
                    "source_locator": {
                        "document_id": document["document_id"],
                        "source_path": document["source_path"],
                        "start_char": part["start_char"],
                        "end_char": part["end_char"],
                        "part_index": index - 1,
                        "part_count": len(parts),
                    },
                    "metadata": metadata,
                }
            )
    return chunks, {
        "document_count": len(documents),
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
    }


def _normalize_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        content = _text(item.get("content"))
        if not content:
            continue
        role = _text(item.get("role")) or "message"
        messages.append(
            {
                "message_id": _text(item.get("message_id")) or f"message_{index + 1}",
                "role": role,
                "content": content,
                "client_order": _numeric(item.get("client_order"), fallback=float(index + 1)),
                "created_at": _text(item.get("created_at")),
                "metadata": _dict(item.get("metadata")),
            }
        )
    return sorted(messages, key=lambda message: (float(message["client_order"]), message["message_id"]))


def _message_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in messages:
        role = _text(message.get("role"))
        if role == "user" and current:
            turns.append(current)
            current = [message]
        else:
            current.append(message)
    if current:
        turns.append(current)
    return turns


def _format_messages(messages: list[dict[str, Any]]) -> str:
    return "\n".join(f"{_text(message.get('role')) or 'message'}: {_text(message.get('content'))}" for message in messages)


def _normalize_documents(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    documents: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        content = _text(item.get("content"))
        if not content:
            continue
        document_id = _text(item.get("document_id")) or _text(item.get("doc_id")) or f"document_{index + 1}"
        documents.append(
            {
                "document_id": document_id,
                "title": _text(item.get("title")) or document_id,
                "source_path": _text(item.get("source_path")),
                "mime_type": _text(item.get("mime_type")) or "text/plain",
                "content": content,
                "source_revision_id": _text(item.get("source_revision_id")),
                "metadata": _dict(item.get("metadata")),
            }
        )
    return documents


def _split_text(text: str, *, max_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    normalized = _normalize_document_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [{"content": normalized, "start_char": 0, "end_char": len(normalized)}]

    parts: list[dict[str, Any]] = []
    cursor = 0
    text_length = len(normalized)
    min_break = max(1, max_chars // 2)
    overlap = min(max(overlap_chars, 0), max(0, max_chars // 2))

    while cursor < text_length:
        end = min(cursor + max_chars, text_length)
        if end < text_length:
            break_at = _best_break(normalized, cursor + min_break, end)
            if break_at > cursor:
                end = break_at
        content = normalized[cursor:end].strip()
        if content:
            parts.append({"content": content, "start_char": cursor, "end_char": end})
        if end >= text_length:
            break
        cursor = max(end - overlap, cursor + 1)
    return parts


def _best_break(text: str, start: int, end: int) -> int:
    candidates = [
        text.rfind("\n\n", start, end),
        text.rfind("\n", start, end),
        text.rfind(". ", start, end),
        text.rfind("。", start, end),
        text.rfind(" ", start, end),
    ]
    best = max(candidates)
    if best == -1:
        return -1
    if text.startswith("\n\n", best):
        return best + 2
    if text.startswith(". ", best):
        return best + 2
    return best + 1


def _normalize_document_text(text: Any) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in raw.split("\n")]
    collapsed = "\n".join(lines)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def _message_window_source_id(session_id: str, message_ids: list[str]) -> str:
    if message_ids:
        return f"{session_id}:{message_ids[0]}:{message_ids[-1]}" if session_id else f"{message_ids[0]}:{message_ids[-1]}"
    return session_id or "message_window"


def _succeeded(source_kind: str, strategy: str, chunks: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "source_kind": source_kind,
        "strategy": strategy,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "report": {
            **report,
            "chunk_count": len(chunks),
        },
    }


def _failed(
    error_type: str,
    error: str,
    *,
    source_kind: str = "",
    strategy: str = "",
) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_type": error_type,
        "error": error,
        "source_kind": source_kind,
        "strategy": strategy,
        "chunk_count": 0,
        "chunks": [],
        "report": {},
    }


def _stable_id(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"source_chunker:{kind}:{digest[:16]}"


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _estimate_tokens(content: str) -> int:
    return max(1, (len(content) + 3) // 4) if content.strip() else 0


def _flatten(turns: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [message for turn in turns for message in turn]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _numeric(value: Any, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


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
    print(json.dumps(source_chunker(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
