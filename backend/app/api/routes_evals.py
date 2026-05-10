from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.evaluator import store


router = APIRouter(prefix="/api/evals", tags=["evals"])


@router.get("/suites")
def list_eval_suites() -> list[dict[str, Any]]:
    return store.list_eval_suites()


@router.post("/suites")
def create_eval_suite(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.create_eval_suite(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/suites/{suite_id}/cases")
def list_eval_cases(suite_id: str) -> list[dict[str, Any]]:
    try:
        return store.list_eval_cases(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Eval suite '{suite_id}' does not exist.") from exc


@router.post("/suites/{suite_id}/cases")
def create_eval_case(suite_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.create_eval_case(suite_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Eval suite '{suite_id}' does not exist.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/runs")
def create_eval_run(payload: dict[str, Any]) -> dict[str, Any]:
    suite_id = str(payload.get("suite_id") or "").strip()
    if not suite_id:
        raise HTTPException(status_code=422, detail="suite_id is required.")
    try:
        return store.create_eval_run(
            suite_id,
            requested_by=str(payload.get("requested_by") or ""),
            metadata=dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Eval suite '{suite_id}' does not exist.") from exc


@router.get("/runs/{eval_run_id}")
def get_eval_run(eval_run_id: str) -> dict[str, Any]:
    try:
        return store.load_eval_run(eval_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Eval run '{eval_run_id}' does not exist.") from exc


@router.post("/runs/{eval_run_id}/cases/{case_id}/result")
def record_eval_case_result(eval_run_id: str, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return store.record_eval_case_result(eval_run_id, case_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Eval case result '{case_id}' does not exist.") from exc
