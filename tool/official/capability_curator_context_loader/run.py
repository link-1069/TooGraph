from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any


DEFAULT_SCOPE = {
    "capability_kinds": ["action", "tool", "subgraph", "template"],
    "lookback_days": 30,
    "candidate_limit": 50,
    "usage_limit": 200,
    "include_official": True,
    "include_user": True,
    "focus": ["failure_rate", "duplicate_capabilities", "missing_tests", "missing_docs", "stale_capabilities"],
}


def capability_curator_context_loader(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    try:
        _ensure_backend_path()
        repo_root = _repo_root()
        scope = _normalize_scope(inputs.get("curator_scope"))
        catalog_snapshot = _build_catalog_snapshot(repo_root, scope)
        usage_snapshot = _build_usage_snapshot(scope)
        eval_snapshot = _build_eval_snapshot(repo_root, scope)
        candidates_snapshot = _build_existing_candidates_snapshot(scope)
        report = {
            "scope": "capability_curator",
            "source_counts": {
                "actions": catalog_snapshot["counts"]["actions"],
                "tools": catalog_snapshot["counts"]["tools"],
                "templates": catalog_snapshot["counts"]["templates"],
                "usage_events": usage_snapshot["counts"]["events"],
                "official_template_eval_suites": eval_snapshot["counts"]["official_template_eval_suites"],
                "existing_candidates": candidates_snapshot["counts"]["total"],
            },
            "warnings": [
                *catalog_snapshot.get("warnings", []),
                *usage_snapshot.get("warnings", []),
                *eval_snapshot.get("warnings", []),
                *candidates_snapshot.get("warnings", []),
            ],
        }
        return {
            "status": "succeeded",
            "curator_scope": scope,
            "capability_catalog_snapshot": catalog_snapshot,
            "capability_usage_snapshot": usage_snapshot,
            "eval_snapshot": eval_snapshot,
            "existing_candidates_snapshot": candidates_snapshot,
            "curator_context_report": report,
        }
    except Exception as exc:
        warning = {"type": "capability_curator_context_load_failed", "message": str(exc)}
        return {
            "status": "failed",
            "error_type": "capability_curator_context_load_failed",
            "error": str(exc),
            "curator_scope": _normalize_scope(inputs.get("curator_scope")),
            "capability_catalog_snapshot": _empty_catalog_snapshot([warning]),
            "capability_usage_snapshot": _empty_usage_snapshot([warning]),
            "eval_snapshot": _empty_eval_snapshot([warning]),
            "existing_candidates_snapshot": _empty_candidates_snapshot([warning]),
            "curator_context_report": {
                "scope": "capability_curator",
                "source_counts": {},
                "warnings": [warning],
            },
        }


def _build_catalog_snapshot(repo_root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    source_roots = _selected_source_roots(scope)
    actions = _discover_action_items(repo_root, source_roots)
    tools = _discover_tool_items(repo_root, source_roots)
    templates = _discover_template_items(repo_root, source_roots)
    warnings: list[dict[str, str]] = []
    return {
        "kind": "capability_catalog_snapshot",
        "actions": actions,
        "tools": tools,
        "templates": templates,
        "counts": {
            "actions": len(actions),
            "tools": len(tools),
            "templates": len(templates),
            "subgraphs": sum(1 for item in templates if item.get("capability_discoverable") is True),
        },
        "warnings": warnings,
    }


def _discover_action_items(repo_root: Path, source_roots: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in source_roots:
        for manifest in _iter_manifests(repo_root / "action" / source, "action.json"):
            payload = _read_json(manifest)
            key = _text(payload.get("actionKey") or payload.get("action_key") or manifest.parent.name)
            if not key:
                continue
            items.append(
                {
                    "kind": "action",
                    "key": key,
                    "name": _text(payload.get("name") or key),
                    "description": _text(payload.get("description")),
                    "source": source,
                    "source_path": _relative_path(repo_root, manifest),
                    "permissions": _text_list(payload.get("permissions")),
                    "version": _text(payload.get("version")),
                    "runtime": _runtime_summary(payload.get("runtime")),
                    "input_schema": _schema_summary(payload.get("stateInputSchema") or payload.get("state_input_schema")),
                    "output_schema": _schema_summary(payload.get("stateOutputSchema") or payload.get("state_output_schema")),
                    "eval_status": _eval_status(repo_root, manifest.parent / "eval_cases.json"),
                }
            )
    return sorted(items, key=lambda item: (item["source"], item["key"]))


def _discover_tool_items(repo_root: Path, source_roots: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in source_roots:
        for manifest in _iter_manifests(repo_root / "tool" / source, "tool.json"):
            payload = _read_json(manifest)
            key = _text(payload.get("toolKey") or payload.get("tool_key") or manifest.parent.name)
            if not key:
                continue
            items.append(
                {
                    "kind": "tool",
                    "key": key,
                    "name": _text(payload.get("name") or key),
                    "description": _text(payload.get("description")),
                    "source": source,
                    "source_path": _relative_path(repo_root, manifest),
                    "permissions": _text_list(payload.get("permissions")),
                    "version": _text(payload.get("version")),
                    "runtime": _runtime_summary(payload.get("runtime")),
                    "input_schema": _schema_summary(payload.get("inputSchema") or payload.get("input_schema")),
                    "output_schema": _schema_summary(payload.get("outputSchema") or payload.get("output_schema")),
                    "eval_status": _eval_status(repo_root, manifest.parent / "eval_cases.json"),
                }
            )
    return sorted(items, key=lambda item: (item["source"], item["key"]))


def _discover_template_items(repo_root: Path, source_roots: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in source_roots:
        for manifest in _iter_manifests(repo_root / "graph_template" / source, "template.json"):
            payload = _read_json(manifest)
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            key = _text(payload.get("template_id") or manifest.parent.name)
            if not key:
                continue
            eval_path = manifest.parent / _text(metadata.get("evalCases") or payload.get("evalCases") or "eval_cases.json")
            items.append(
                {
                    "kind": "template",
                    "key": key,
                    "name": _text(payload.get("label") or key),
                    "description": _text(payload.get("description")),
                    "source": source,
                    "source_path": _relative_path(repo_root, manifest),
                    "status": "active",
                    "capability_discoverable": _template_capability_discoverable(metadata),
                    "role": _text(metadata.get("role")),
                    "category": _text(metadata.get("category")),
                    "origin": _text(metadata.get("origin")),
                    "required_actions": _text_list(metadata.get("requiredActions")),
                    "required_tools": _text_list(metadata.get("requiredTools")),
                    "permissions": _text_list(metadata.get("permissions")),
                    "eval_status": _eval_status(repo_root, eval_path),
                }
            )
    return sorted(items, key=lambda item: (item["source"], item["key"]))


def _build_usage_snapshot(scope: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded_int(scope.get("usage_limit"), default=200, minimum=1, maximum=1000)
    lookback_days = _bounded_int(scope.get("lookback_days"), default=30, minimum=1, maximum=3650)
    warnings: list[dict[str, str]] = []
    try:
        from app.core.storage import database

        if not database.DB_PATH.exists():
            return _empty_usage_snapshot([])
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat().replace("+00:00", "Z")
        connection = sqlite3.connect(database.DB_PATH)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT event_id, invocation_id, run_id, node_id, capability_kind, capability_key,
                       selected_reason, status, latency_ms, error_type, error_message,
                       permission_result, summary, detail_json, created_at
                FROM capability_usage_events
                WHERE created_at >= ?
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
        finally:
            connection.close()
    except Exception as exc:
        return _empty_usage_snapshot([{"type": "usage_snapshot_failed", "message": str(exc)}])
    events = [_usage_event_from_row(row) for row in rows]
    by_capability = _group_usage_events(events)
    return {
        "kind": "capability_usage_snapshot",
        "lookback_days": lookback_days,
        "events": events,
        "by_capability": by_capability,
        "counts": {
            "events": len(events),
            "capabilities": len(by_capability),
            "failed_events": sum(1 for event in events if not _status_succeeded(event.get("status"))),
        },
        "warnings": warnings,
    }


def _build_eval_snapshot(repo_root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    _ = scope
    suites: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for eval_path in sorted((repo_root / "graph_template" / "official").glob("*/eval_cases.json")):
        try:
            payload = _read_json(eval_path)
            cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
            template_id = _text(payload.get("template_id") or eval_path.parent.name)
            suites.append(
                {
                    "template_id": template_id,
                    "suite": _text(payload.get("suite") or template_id),
                    "case_count": len(cases),
                    "case_ids": [_text(case.get("case_id")) for case in cases if isinstance(case, dict)],
                    "source_path": _relative_path(repo_root, eval_path),
                }
            )
        except Exception as exc:
            warnings.append({"type": "eval_snapshot_parse_failed", "message": f"{eval_path}: {exc}"})
    return {
        "kind": "eval_snapshot",
        "official_template_eval_suites": suites,
        "counts": {
            "official_template_eval_suites": len(suites),
            "official_template_eval_cases": sum(item.get("case_count", 0) for item in suites),
        },
        "warnings": warnings,
    }


def _build_existing_candidates_snapshot(scope: dict[str, Any]) -> dict[str, Any]:
    limit = _bounded_int(scope.get("candidate_limit"), default=50, minimum=1, maximum=500)
    try:
        from app.buddy import store

        candidates = store.list_improvement_candidates()[:limit]
    except Exception as exc:
        return _empty_candidates_snapshot([{"type": "candidate_snapshot_failed", "message": str(exc)}])
    trimmed = [_candidate_summary(candidate) for candidate in candidates]
    counts_by_status = dict(Counter(_text(candidate.get("status") or "unknown") for candidate in trimmed))
    return {
        "kind": "existing_candidates_snapshot",
        "candidates": trimmed,
        "counts": {
            "total": len(trimmed),
        },
        "counts_by_status": counts_by_status,
        "warnings": [],
    }


def _usage_event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": _text(row["event_id"]),
        "invocation_id": _text(row["invocation_id"]),
        "run_id": _text(row["run_id"]),
        "node_id": _text(row["node_id"]),
        "capability_kind": _text(row["capability_kind"]),
        "capability_key": _text(row["capability_key"]),
        "selected_reason": _text(row["selected_reason"]),
        "status": _text(row["status"]),
        "latency_ms": row["latency_ms"],
        "error_type": _text(row["error_type"]),
        "error_message": _text(row["error_message"]),
        "permission_result": _text(row["permission_result"]),
        "summary": _text(row["summary"]),
        "detail": _json_loads(row["detail_json"], {}),
        "created_at": _text(row["created_at"]),
    }


def _group_usage_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        capability_id = f"{event.get('capability_kind')}:{event.get('capability_key')}"
        record = grouped.setdefault(
            capability_id,
            {
                "capability_kind": event.get("capability_kind"),
                "capability_key": event.get("capability_key"),
                "event_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "recent_events": [],
            },
        )
        record["event_count"] += 1
        if _status_succeeded(event.get("status")):
            record["success_count"] += 1
        else:
            record["failure_count"] += 1
        if len(record["recent_events"]) < 5:
            record["recent_events"].append(
                {
                    "event_id": event.get("event_id"),
                    "run_id": event.get("run_id"),
                    "status": event.get("status"),
                    "error_type": event.get("error_type"),
                    "created_at": event.get("created_at"),
                }
            )
    for record in grouped.values():
        total = record["event_count"]
        record["success_rate"] = record["success_count"] / total if total else 0
    return grouped


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _text(candidate.get("candidate_id")),
        "kind": _text(candidate.get("kind")),
        "status": _text(candidate.get("status")),
        "status_reason": _text(candidate.get("status_reason")),
        "source_run_id": _text(candidate.get("source_run_id")),
        "review_id": _text(candidate.get("review_id")),
        "review_run_id": _text(candidate.get("review_run_id")),
        "target_ref": candidate.get("target_ref") if isinstance(candidate.get("target_ref"), dict) else {},
        "evidence_refs": candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else [],
        "risk_level": _text(candidate.get("risk_level")),
        "expected_benefit": _text(candidate.get("expected_benefit")),
        "proposed_change_summary": _text(candidate.get("proposed_change_summary")),
        "approval_required": bool(candidate.get("approval_required")),
        "validation_run_id": _text(candidate.get("validation_run_id")),
        "applied_revision_id": _text(candidate.get("applied_revision_id")),
        "updated_at": _text(candidate.get("updated_at")),
    }


def _normalize_scope(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_SCOPE)
    for key in ("include_official", "include_user"):
        if key in source:
            result[key] = _bool(source.get(key), default=bool(result[key]))
    for key, default, minimum, maximum in (
        ("lookback_days", 30, 1, 3650),
        ("candidate_limit", 50, 1, 500),
        ("usage_limit", 200, 1, 1000),
    ):
        result[key] = _bounded_int(source.get(key), default=default, minimum=minimum, maximum=maximum)
    if isinstance(source.get("capability_kinds"), list):
        result["capability_kinds"] = _text_list(source.get("capability_kinds")) or result["capability_kinds"]
    if isinstance(source.get("focus"), list):
        result["focus"] = _text_list(source.get("focus")) or result["focus"]
    return result


def _selected_source_roots(scope: dict[str, Any]) -> list[str]:
    roots: list[str] = []
    if scope.get("include_official") is not False:
        roots.append("official")
    if scope.get("include_user") is not False:
        roots.append("user")
    return roots or ["official"]


def _iter_manifests(root: Path, filename: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path / filename for path in root.iterdir() if (path / filename).is_file())


def _eval_status(repo_root: Path, eval_path: Path) -> dict[str, Any]:
    if not eval_path.exists():
        return {"has_cases": False, "case_count": 0, "source": ""}
    try:
        payload = _read_json(eval_path)
        cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
        return {"has_cases": bool(cases), "case_count": len(cases), "source": _relative_path(repo_root, eval_path)}
    except Exception as exc:
        return {"has_cases": False, "case_count": 0, "source": _relative_path(repo_root, eval_path), "error": str(exc)}


def _template_capability_discoverable(metadata: dict[str, Any]) -> bool:
    if metadata.get("visible") is False or metadata.get("internal") is True:
        return False
    return metadata.get("capabilityDiscoverableDefault") is not False


def _runtime_summary(value: Any) -> dict[str, Any]:
    runtime = value if isinstance(value, dict) else {}
    return {
        "type": _text(runtime.get("type") or "none"),
        "entrypoint": _text(runtime.get("entrypoint")),
        "timeout_seconds": _bounded_int(runtime.get("timeoutSeconds") or runtime.get("timeout_seconds"), default=30, minimum=1, maximum=3600),
    }


def _schema_summary(value: Any) -> list[dict[str, str]]:
    fields = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = _text(field.get("key"))
        if not key:
            continue
        result.append(
            {
                "key": key,
                "name": _text(field.get("name") or key),
                "value_type": _text(field.get("valueType") or field.get("value_type") or "text"),
                "description": _text(field.get("description")),
            }
        )
    return result


def _empty_catalog_snapshot(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {"kind": "capability_catalog_snapshot", "actions": [], "tools": [], "templates": [], "counts": {"actions": 0, "tools": 0, "templates": 0, "subgraphs": 0}, "warnings": warnings}


def _empty_usage_snapshot(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {"kind": "capability_usage_snapshot", "lookback_days": 0, "events": [], "by_capability": {}, "counts": {"events": 0, "capabilities": 0, "failed_events": 0}, "warnings": warnings}


def _empty_eval_snapshot(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {"kind": "eval_snapshot", "official_template_eval_suites": [], "counts": {"official_template_eval_suites": 0, "official_template_eval_cases": 0}, "warnings": warnings}


def _empty_candidates_snapshot(warnings: list[dict[str, str]]) -> dict[str, Any]:
    return {"kind": "existing_candidates_snapshot", "candidates": [], "counts": {"total": 0}, "counts_by_status": {}, "warnings": warnings}


def _ensure_backend_path() -> None:
    backend_path = _repo_root() / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))


def _repo_root() -> Path:
    return Path(os.environ.get("TOOGRAPH_REPO_ROOT") or Path(__file__).resolve().parents[3]).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _json_loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _status_succeeded(status: Any) -> bool:
    return _text(status).lower() in {"succeeded", "success", "completed", "ok"}


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "failed", "error_type": "invalid_json", "error": str(exc)}, ensure_ascii=False))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"status": "failed", "error_type": "invalid_input", "error": "stdin must be a JSON object."}, ensure_ascii=False))
        return
    print(json.dumps(capability_curator_context_loader(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
