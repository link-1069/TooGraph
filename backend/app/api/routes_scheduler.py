from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.scheduler import runner, store


router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/jobs")
def list_scheduled_graph_jobs(include_disabled: bool = Query(default=False)) -> list[dict[str, Any]]:
    return store.list_scheduled_graph_jobs(include_disabled=include_disabled)


@router.post("/jobs")
def create_scheduled_graph_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.create_scheduled_graph_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/due")
def list_due_scheduled_graph_jobs(now: str = Query(default=""), limit: int = Query(default=25, ge=1, le=100)) -> list[dict[str, Any]]:
    try:
        return store.list_due_scheduled_graph_jobs(now=now or None, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/run-due")
def run_due_scheduled_graph_jobs(
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    try:
        return runner.run_due_scheduled_graph_jobs(
            background_tasks=background_tasks,
            now=str(request_payload.get("now") or "") or None,
            limit=int(request_payload.get("limit") or 25),
            requested_by=str(request_payload.get("requested_by") or "scheduler"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_scheduled_graph_job(job_id: str) -> dict[str, Any]:
    try:
        return store.load_scheduled_graph_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Scheduled graph job '{job_id}' does not exist.") from exc


@router.patch("/jobs/{job_id}/enabled")
def set_scheduled_graph_job_enabled(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.set_scheduled_graph_job_enabled(job_id, payload.get("enabled") is not False)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Scheduled graph job '{job_id}' does not exist.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/runs")
def list_scheduled_graph_job_runs(job_id: str) -> list[dict[str, Any]]:
    try:
        store.load_scheduled_graph_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Scheduled graph job '{job_id}' does not exist.") from exc
    return store.list_scheduled_graph_job_runs(job_id=job_id)


@router.post("/jobs/{job_id}/run")
def run_scheduled_graph_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    try:
        return runner.start_scheduled_graph_job_run(
            job_id,
            background_tasks=background_tasks,
            trigger_reason=str(request_payload.get("trigger_reason") or "manual"),
            requested_by=str(request_payload.get("requested_by") or ""),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Scheduled graph job '{job_id}' does not exist.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
