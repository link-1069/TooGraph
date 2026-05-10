from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.core.model_catalog import get_default_text_model_ref, normalize_model_ref
from app.tools.model_provider_client import chat_with_model_ref_with_meta


LLM_JUDGE_SYSTEM_PROMPT = "\n".join(
    [
        "You are TooGraph's evaluation judge.",
        "Assess one graph-run result against the provided rubric and expected outcome.",
        "Use only the supplied case, output, artifacts, and rubric.",
        "Return only a JSON object. Do not add markdown or prose.",
    ]
)

LLM_JUDGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["passed", "failed", "error"]},
        "score": {"type": "number"},
        "message": {"type": "string"},
        "verdict": {"type": "string"},
        "reason": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "issues": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "object", "additionalProperties": True},
    },
    "required": ["status", "score", "message"],
    "additionalProperties": True,
}


def create_llm_judge_runner(
    *,
    get_default_text_model_ref_func: Callable[..., str] = get_default_text_model_ref,
    chat_with_model_ref_with_meta_func: Callable[..., tuple[str, dict[str, Any]]] = chat_with_model_ref_with_meta,
) -> Callable[..., dict[str, Any]]:
    return lambda **kwargs: run_llm_judge(
        **kwargs,
        get_default_text_model_ref_func=get_default_text_model_ref_func,
        chat_with_model_ref_with_meta_func=chat_with_model_ref_with_meta_func,
    )


def run_llm_judge(
    *,
    case: dict[str, Any],
    check: dict[str, Any],
    final_output: dict[str, Any],
    artifacts: dict[str, Any],
    get_default_text_model_ref_func: Callable[..., str] = get_default_text_model_ref,
    chat_with_model_ref_with_meta_func: Callable[..., tuple[str, dict[str, Any]]] = chat_with_model_ref_with_meta,
) -> dict[str, Any]:
    requested_model_ref = _text(check.get("model_ref")) or _text(check.get("model"))
    model_ref = requested_model_ref or _text(get_default_text_model_ref_func(force_refresh=True))
    if not model_ref:
        return {
            "status": "skipped",
            "score": None,
            "message": "No default text model is configured for LLM judge checks.",
            "actual": {},
            "details": {"reason": "missing_model_ref"},
        }
    model_ref = normalize_model_ref(model_ref, default_provider="local")

    user_prompt = _build_judge_user_prompt(case=case, check=check, final_output=final_output, artifacts=artifacts)
    try:
        content, meta = chat_with_model_ref_with_meta_func(
            model_ref=model_ref,
            system_prompt=LLM_JUDGE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=_float_value(check.get("temperature"), default=0.0),
            max_tokens=_int_value(check.get("max_tokens"), default=700),
            thinking_enabled=False,
            thinking_level="off",
            structured_output_schema=LLM_JUDGE_OUTPUT_SCHEMA,
        )
    except Exception as exc:
        return {
            "status": "error",
            "score": None,
            "message": f"LLM judge request failed: {exc}",
            "actual": {"error": str(exc)},
            "details": {"model_ref": model_ref, "requested_model_ref": requested_model_ref},
        }

    parsed = _parse_json_object(content)
    if not parsed:
        return {
            "status": "error",
            "score": None,
            "message": "LLM judge returned a non-JSON response.",
            "actual": {"raw_output": _truncate_text(content, 2000)},
            "details": {
                "model_ref": model_ref,
                "requested_model_ref": requested_model_ref,
                "model_meta": _safe_model_meta(meta),
            },
        }

    details = _as_dict(parsed.get("details"))
    details.update(
        {
            "model_ref": model_ref,
            "requested_model_ref": requested_model_ref,
            "model_meta": _safe_model_meta(meta),
            "raw_judgment": parsed,
        }
    )
    actual = {
        key: parsed.get(key)
        for key in ("verdict", "reason", "strengths", "issues")
        if parsed.get(key) not in (None, "", [], {})
    }
    return {
        "status": _text(parsed.get("status")) or _status_from_score(parsed.get("score"), check),
        "score": parsed.get("score"),
        "message": _text(parsed.get("message")) or _text(parsed.get("reason")) or "LLM judge completed.",
        "actual": actual,
        "details": details,
    }


def _build_judge_user_prompt(
    *,
    case: dict[str, Any],
    check: dict[str, Any],
    final_output: dict[str, Any],
    artifacts: dict[str, Any],
) -> str:
    payload = {
        "task": "Judge whether the graph-run result satisfies the evaluation rubric.",
        "output_contract": {
            "status": "passed, failed, or error",
            "score": "0.0 to 1.0",
            "message": "one concise explanation for the evaluation result",
            "verdict": "short verdict label",
            "reason": "specific reason grounded in the supplied output",
            "strengths": "array of strengths",
            "issues": "array of issues",
        },
        "case": {
            "case_id": case.get("case_id"),
            "name": case.get("name"),
            "description": case.get("description"),
            "input_values": case.get("input_values") if isinstance(case.get("input_values"), dict) else {},
            "expected": case.get("expected") if isinstance(case.get("expected"), dict) else {},
        },
        "check": {
            "name": check.get("name"),
            "rubric": check.get("rubric"),
            "criteria": check.get("criteria"),
            "target": check.get("target") or "final_output",
            "min_score": check.get("min_score") if check.get("min_score") is not None else check.get("threshold"),
        },
        "final_output": final_output,
        "artifacts": artifacts,
    }
    return _truncate_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), 24000)


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"^\s*```(?:json)?\s*\n?", "", str(content or ""))
    cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned).strip()
    candidates = [cleaned]
    json_start = cleaned.find("{")
    json_end = cleaned.rfind("}")
    if json_start != -1 and json_end > json_start:
        candidates.append(cleaned[json_start : json_end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _status_from_score(value: Any, check: dict[str, Any]) -> str:
    score = _optional_float(value)
    if score is None:
        return "error"
    threshold = _optional_float(check.get("min_score"))
    if threshold is None:
        threshold = _optional_float(check.get("threshold"))
    if threshold is None:
        threshold = 0.5
    return "passed" if score >= threshold else "failed"


def _safe_model_meta(meta: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in meta.items():
        if key.lower() in {"request", "response", "request_raw", "response_raw", "messages", "headers"}:
            continue
        safe[key] = value
    return safe


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _int_value(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _float_value(value: Any, *, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
