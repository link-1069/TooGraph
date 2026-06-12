from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any


ACTIVE_REVIEW_STATUSES = {"queued", "running", "paused", "awaiting_human", "completed"}
EXCLUDED_TEMPLATE_IDS = {"buddy_autonomous_review", "buddy_context_compaction"}
EXCLUDED_METADATA_ROLES = {"buddy_background_review", "buddy_autonomous_review", "buddy_context_compaction"}
DEFAULT_TEMPLATE_ID = "buddy_autonomous_review"


def buddy_review_source_selector(payload: dict[str, Any] | None, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    invocation_context = _resolve_invocation_context(context)
    runtime_context = _dict(invocation_context.get("runtime_context"))
    mode = _text(inputs.get("mode")) or "auto_unreviewed"
    review_run_id = _text(invocation_context.get("run_id"))
    existing_review_id = _text(runtime_context.get("buddy_background_review_id"))
    if mode not in {"auto_unreviewed", "explicit"}:
        return _failed("unsupported_mode", f"Unsupported selection mode: {mode}")
    if not review_run_id:
        return _failed("missing_review_run_id", "Current graph run_id is required to claim a Buddy review source.")

    try:
        _ensure_backend_path()
        from app.buddy import store as buddy_store
        from app.core.storage.run_store import list_run_summaries, load_run
    except Exception as exc:
        return _failed("backend_import_failed", str(exc))

    skipped_reviewed = _reviewed_source_run_ids(buddy_store)

    if mode == "explicit":
        selected_source_run_id = _text(inputs.get("source_run_id"))
        if not selected_source_run_id:
            return _failed("missing_source_run_id", "source_run_id is required in explicit mode.")
        try:
            source_run = load_run(selected_source_run_id)
        except Exception as exc:
            return _failed("source_run_load_failed", str(exc), selected_source_run_id=selected_source_run_id)
        if not _is_reviewable_buddy_source_run(source_run):
            return _failed(
                "source_run_not_reviewable",
                "source_run_id must refer to a completed visible Buddy run.",
                selected_source_run_id=selected_source_run_id,
            )
    else:
        summaries = list_run_summaries()
        candidates = [
            run
            for run in sorted(summaries, key=_run_sort_key)
            if _is_reviewable_buddy_source_run(run)
            and _text(run.get("run_id")) not in skipped_reviewed
            and _text(run.get("run_id")) != review_run_id
        ]
        if not candidates:
            report = {
                "selection_mode": mode,
                "skipped_reason": "no_unreviewed_completed_buddy_run",
                "skipped_reviewed_source_run_ids": sorted(skipped_reviewed),
                "candidate_count": 0,
            }
            return {
                "status": "succeeded",
                "has_source_run": False,
                "selected_source_run_id": "",
                "review_id": "",
                "selection_report": report,
                "result": "No unreviewed completed Buddy run was found.",
            }
        selected_source_run_id = _text(candidates[0].get("run_id"))

    try:
        if existing_review_id:
            review = buddy_store.get_background_review_run(existing_review_id)
            review = buddy_store.mark_background_review_run_started(
                _text(review.get("review_id")),
                review_run_id=review_run_id,
            )
        else:
            review = buddy_store.create_background_review_run(
                source_run_id=selected_source_run_id,
                review_run_id=review_run_id,
                template_id=DEFAULT_TEMPLATE_ID,
                trigger_reason="scheduled_auto_select" if mode == "auto_unreviewed" else "explicit_source_run",
                metadata={"selection_mode": mode},
            )
            review = buddy_store.mark_background_review_run_started(
                _text(review.get("review_id")),
                review_run_id=review_run_id,
            )
    except Exception as exc:
        return _failed("review_claim_failed", str(exc), selected_source_run_id=selected_source_run_id)

    report = {
        "selection_mode": mode,
        "selected_source_run_id": selected_source_run_id,
        "review_run_id": review_run_id,
        "review_id": _text(review.get("review_id")),
        "existing_review_id": existing_review_id,
        "skipped_reviewed_source_run_ids": sorted(skipped_reviewed),
    }
    return {
        "status": "succeeded",
        "has_source_run": True,
        "selected_source_run_id": selected_source_run_id,
        "review_id": _text(review.get("review_id")),
        "selection_report": report,
        "result": f"Selected Buddy source run {selected_source_run_id} for background review.",
    }


def _reviewed_source_run_ids(buddy_store: Any) -> set[str]:
    return {
        _text(record.get("source_run_id"))
        for record in buddy_store.list_background_review_runs()
        if _text(record.get("source_run_id")) and _text(record.get("status")) in ACTIVE_REVIEW_STATUSES
    }


def _is_reviewable_buddy_source_run(run: dict[str, Any]) -> bool:
    if _text(run.get("status")) != "completed":
        return False
    run_id = _text(run.get("run_id"))
    if not run_id:
        return False
    template_id = _text(run.get("template_id"))
    if template_id in EXCLUDED_TEMPLATE_IDS:
        return False
    metadata = _dict(run.get("metadata"))
    role = _text(metadata.get("role"))
    if role in EXCLUDED_METADATA_ROLES:
        return False
    runtime_context = _dict(metadata.get("runtime_context"))
    return (
        _text(metadata.get("origin")) == "buddy"
        or bool(_text(metadata.get("buddy_template_id")))
        or bool(_text(runtime_context.get("buddy_session_id")))
    )


def _run_sort_key(run: dict[str, Any]) -> tuple[str, str]:
    return (
        _text(run.get("started_at")) or _text(_dict(run.get("lifecycle")).get("updated_at")),
        _text(run.get("run_id")),
    )


def _failed(error_type: str, error: str, *, selected_source_run_id: str = "") -> dict[str, Any]:
    return {
        "status": "failed",
        "has_source_run": False,
        "selected_source_run_id": selected_source_run_id,
        "review_id": "",
        "selection_report": {
            "selection_mode": "",
            "selected_source_run_id": selected_source_run_id,
            "error_type": error_type,
            "error": error,
        },
        "error_type": error_type,
        "error": error,
        "result": f"Buddy review source selection failed: {error}",
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_invocation_context(explicit_context: dict[str, Any] | None) -> dict[str, Any]:
    context = dict(explicit_context) if isinstance(explicit_context, dict) else {}
    runtime_context: dict[str, Any] = {}
    runtime_context.update(_read_runtime_context_from_environment())
    nested = context.get("runtime_context")
    if isinstance(nested, dict):
        runtime_context.update(nested)
    action_nested = context.get("action_runtime_context")
    if isinstance(action_nested, dict):
        runtime_context.update(action_nested)
    if runtime_context:
        context["runtime_context"] = runtime_context
        context["action_runtime_context"] = runtime_context
    review_run_id = (
        _text(context.get("run_id"))
        or _text(runtime_context.get("run_id"))
        or _text(os.environ.get("TOOGRAPH_ACTION_RUN_ID"))
    )
    if review_run_id:
        context["run_id"] = review_run_id
    return context


def _read_runtime_context_from_environment() -> dict[str, Any]:
    inline_context = _decode_json_object(_text(os.environ.get("TOOGRAPH_ACTION_RUNTIME_CONTEXT")))
    if inline_context:
        return inline_context
    file_path = _text(os.environ.get("TOOGRAPH_ACTION_RUNTIME_CONTEXT_FILE"))
    if not file_path:
        return {}
    try:
        return _decode_json_object(Path(file_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _decode_json_object(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ensure_backend_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    backend_path = repo_root / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


if __name__ == "__main__":
    raw_payload = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(buddy_review_source_selector(raw_payload), ensure_ascii=False))
