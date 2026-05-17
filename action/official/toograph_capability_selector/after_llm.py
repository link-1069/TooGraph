from __future__ import annotations

import json
import sys
from typing import Any


SUPPORTED_KINDS = {"action", "subgraph", "tool"}
PAGE_REQUEST_KEYWORDS = (
    "打开",
    "跳转",
    "页面",
    "界面",
    "ui",
    "按钮",
    "点击",
    "当前图",
    "编辑图",
    "知识库页面",
)
RESEARCH_KEYWORDS = (
    "新闻",
    "最新",
    "研究",
    "联网",
    "搜索",
    "资料",
    "调研",
    "竞品",
    "政策",
    "引用",
)


def toograph_capability_selector(**action_inputs: Any) -> dict[str, Any]:
    requirement = _text(
        action_inputs.get("requirement")
        or action_inputs.get("user_message")
        or action_inputs.get("query")
    )
    candidates = _normalize_candidates(action_inputs.get("capability_candidates"))
    selected = _select_candidate(requirement, candidates)
    if not selected:
        return {
            "capability": {
                "kind": "none",
                "reason": "没有找到适合该请求的已启用能力。",
            },
            "found": False,
        }
    return {
        "capability": selected,
        "found": True,
    }


def _select_candidate(requirement: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_requirement = requirement.lower()
    if _is_page_request(normalized_requirement):
        page_candidate = _find_by_key(candidates, "toograph_page_operation_workflow")
        if page_candidate:
            return page_candidate

    scored = [
        (_score_candidate(normalized_requirement, candidate), index, candidate)
        for index, candidate in enumerate(candidates)
        if candidate.get("kind") in SUPPORTED_KINDS and candidate.get("key")
    ]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return _public_capability(scored[0][2])


def _score_candidate(requirement: str, candidate: dict[str, Any]) -> int:
    text = " ".join(
        _text(candidate.get(key)).lower()
        for key in ("key", "name", "description", "when_to_use", "whenToUse")
    )
    score = 0
    if candidate.get("kind") == "subgraph":
        score += 2
    for keyword in RESEARCH_KEYWORDS:
        if keyword.lower() in requirement and keyword.lower() in text:
            score += 8
    for token in _tokens(requirement):
        if len(token) >= 2 and token in text:
            score += 2
    if "news" in text and ("新闻" in requirement or "news" in requirement):
        score += 10
    if "research" in text and any(keyword in requirement for keyword in ("研究", "调研", "搜索", "联网")):
        score += 8
    if candidate.get("key") == "advanced_web_research_loop" and any(
        keyword in requirement for keyword in ("新闻", "最新", "研究", "联网", "搜索", "调研")
    ):
        score += 20
    if candidate.get("key") == "toograph_page_operation_workflow" and not _is_page_request(requirement):
        score -= 20
    return score


def _is_page_request(requirement: str) -> bool:
    return any(keyword.lower() in requirement for keyword in PAGE_REQUEST_KEYWORDS)


def _find_by_key(candidates: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for candidate in candidates:
        if candidate.get("key") == key and candidate.get("kind") in SUPPORTED_KINDS:
            return _public_capability(candidate)
    return None


def _normalize_candidates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        return []
    items: list[dict[str, Any]] = []
    for section in ("templates", "subgraphs", "actions", "tools"):
        raw_items = value.get(section)
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            candidate = dict(raw_item)
            if section in {"templates", "subgraphs"}:
                candidate["kind"] = "subgraph"
            items.append(candidate)
    return items


def _public_capability(candidate: dict[str, Any]) -> dict[str, Any]:
    capability = {
        "kind": _text(candidate.get("kind")),
        "key": _text(candidate.get("key")),
    }
    name = _text(candidate.get("name") or candidate.get("label"))
    if name:
        capability["name"] = name
    return capability


def _tokens(value: str) -> list[str]:
    return [token for token in value.replace("_", " ").replace("-", " ").split() if token]


def _text(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    print(json.dumps(toograph_capability_selector(**payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
