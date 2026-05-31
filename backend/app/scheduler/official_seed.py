from __future__ import annotations

from typing import Any

from app.scheduler import store


OFFICIAL_SCHEDULED_GRAPH_JOBS: tuple[dict[str, Any], ...] = (
    {
        "job_id": "official_embedding_maintenance",
        "name": "官方 Embedding 维护",
        "template_id": "embedding_maintenance",
        "input_bindings": {
            "model_ref": "",
            "job_limit": 50,
        },
        "schedule_kind": "interval",
        "schedule_expr": "PT1H",
        "enabled": False,
        "retry_policy": {
            "max_attempts": 3,
            "delay_seconds": 300,
            "backoff_multiplier": 2,
        },
        "metadata": {
            "source": "official_seed",
            "purpose": "embedding_maintenance",
            "recommended_interval": "hourly",
        },
    },
)

DEPRECATED_OFFICIAL_SCHEDULED_GRAPH_JOB_IDS: tuple[str, ...] = (
    "official_buddy_capability_curator",
)


def seed_official_scheduled_graph_jobs(*, now: str | None = None) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    for job_id in DEPRECATED_OFFICIAL_SCHEDULED_GRAPH_JOB_IDS:
        if store.delete_scheduled_graph_job(job_id):
            removed.append({"job_id": job_id})
    for payload in OFFICIAL_SCHEDULED_GRAPH_JOBS:
        job_id = str(payload["job_id"])
        try:
            existing.append(store.load_scheduled_graph_job(job_id))
            continue
        except KeyError:
            pass
        try:
            created.append(store.create_scheduled_graph_job(dict(payload), now=now))
        except ValueError as exc:
            skipped.append({"job_id": job_id, "error": str(exc)})
    return {
        "created_count": len(created),
        "existing_count": len(existing),
        "skipped_count": len(skipped),
        "created": created,
        "existing": existing,
        "skipped": skipped,
        "removed_count": len(removed),
        "removed": removed,
    }
