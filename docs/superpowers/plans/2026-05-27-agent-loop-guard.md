# Agent Loop Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为官方 Buddy 主循环补齐 Hermes 风格 Agent loop 基础鲁棒性：循环预算、能力调用预算、失败分类、标准 stop reason、RunDetail 诊断和 Buddy 胶囊展示。

**Architecture:** 保持 TooGraph 图优先架构。新增一个确定性 Tool `agent_loop_guard`，让 `buddy_autonomous_loop` 在每次动态能力执行后显式检查预算和失败状态，并把判断写入 schema-backed state；运行详情和 Buddy 胶囊从 run record/state 重新组装诊断展示。运行时只补通用 stop reason 派生和 API 字段，避免把 Buddy 专用策略埋进后端。

**Tech Stack:** Python Tool runtime、Node System graph template JSON、FastAPI/Pydantic run schemas、SQLite-backed run store、Vue 3 + TypeScript + Element Plus、Node test runner、pytest。

---

## Scope

本计划实现 `docs/hermes-agent-capability-parity-roadmap.md` 的 Phase A / P0 能力：

- `agent_loop_control` 标准 state。
- `agent_loop_guard` 官方 Tool。
- 官方 `buddy_autonomous_loop` 在 capability 执行后接入 guard。
- 标准 stop reason 写入 run record。
- RunDetail 增加 Agent Diagnostic 初版。
- Buddy 胶囊展示 stop reason、loop count、capability budget。

本计划不处理 Phase B 之后的长期事项，例如 embedding 召回升级、scheduler、delegation、curator、自我改进 pipeline、provider fallback 体系和完整 eval 平台。这些已经在 `docs/hermes-agent-capability-parity-roadmap.md` 中作为独立差距记录。

## Stop Reason Contract

统一 stop reason 使用以下值：

```python
STANDARD_AGENT_STOP_REASONS = {
    "completed",
    "needs_user_clarification",
    "max_iterations_reached",
    "capability_budget_exhausted",
    "permission_required",
    "provider_failed",
    "tool_failed",
    "graph_validation_failed",
    "context_budget_exhausted",
}
```

`agent_loop_guard` 只写入与图内循环相关的 stop reason：

- `max_iterations_reached`
- `capability_budget_exhausted`
- `permission_required`
- `provider_failed`
- `tool_failed`
- `context_budget_exhausted`

运行最终归档时，后端通用 resolver 负责把图 state、cycle summary、permission metadata、run status 和 errors 合成 API 顶层 `stop_reason`：

- 完成且图内没有明确停止原因：`completed`
- 等待权限：`permission_required`
- condition loopLimit：`max_iterations_reached`
- graph validator/runtime structural error：`graph_validation_failed`
- provider/model 相关错误：`provider_failed`
- Tool/Action/capability 相关错误：`tool_failed`

## File Map

Create:

- `tool/official/agent_loop_guard/tool.json`：官方 Tool manifest。
- `tool/official/agent_loop_guard/run.py`：确定性 guard 逻辑，可被 Tool runtime 和单元测试直接导入。
- `backend/tests/test_agent_loop_guard_tool.py`：Tool catalog、预算、失败、权限、上下文耗尽测试。
- `backend/app/core/runtime/agent_stop_reason.py`：标准 stop reason 常量和 run-level 派生函数。
- `frontend/src/pages/agentDiagnosticModel.ts`：RunDetail/Buddy 共用的 Agent Diagnostic 解析模型。
- `frontend/src/pages/agentDiagnosticModel.test.ts`：前端诊断模型测试。

Modify:

- `graph_template/official/buddy_autonomous_loop/template.json`：新增 state、guard Tool 节点、guard condition、guard stop finalizer 节点和边。
- `backend/tests/test_template_layouts.py`：更新官方主循环 contract 测试。
- `scripts/capability-selector-loop.test.mjs`：确认主循环保留完整 capability loop，并接入 guard。
- `backend/app/core/langgraph/finalization.py`：完成/失败归档前解析 `stop_reason`。
- `backend/app/core/runtime/run_artifacts.py`：把 `stop_reason` 写入 artifacts。
- `backend/app/core/storage/graph_run_db_store.py`：把 `stop_reason` 放入 `detail_json` 并从 run state 读回。
- `backend/app/core/schemas/run.py`：给 `RunSummary`/`RunDetail` 增加 `stop_reason`。
- `frontend/src/types/run.ts`：同步 `stop_reason` 类型。
- `frontend/src/pages/runDetailModel.ts`：导出 Agent Diagnostic display model。
- `frontend/src/pages/RunDetailPage.vue`：展示 Agent Diagnostic 面板。
- `frontend/src/buddy/buddyOutputTrace.ts`：把 guard 诊断附加到对应胶囊记录。
- `frontend/src/buddy/buddyOutputTrace.test.ts`：验证 output-boundary 胶囊规则不变，且 guard 诊断能显示。

## Data Contract

新增 state：

```json
{
  "agent_loop_control": {
    "version": 1,
    "iteration_index": 0,
    "max_iterations": 6,
    "capability_call_count": 0,
    "max_capability_calls": 4,
    "failure_count_by_key": {},
    "last_stop_reason": "",
    "retry_budget": 1,
    "warnings": []
  },
  "agent_loop_report": {
    "version": 1,
    "decision": "continue",
    "stop_reason": "",
    "iteration_index": 0,
    "capability_call_count": 0,
    "max_iterations": 6,
    "max_capability_calls": 4,
    "selected_capability_key": "",
    "selected_capability_kind": "none",
    "last_result_status": "",
    "warnings": []
  },
  "agent_loop_stop_reason": "",
  "agent_loop_should_continue": true,
  "agent_loop_should_retry": false
}
```

`agent_loop_guard` 输出字段：

```json
{
  "status": "succeeded",
  "agent_loop_control": {},
  "agent_loop_report": {},
  "agent_loop_stop_reason": "",
  "agent_loop_should_continue": true,
  "agent_loop_should_retry": false,
  "reason": "continue"
}
```

---

### Task 1: Add `agent_loop_guard` Tool Contract And Tests

**Files:**

- Create: `tool/official/agent_loop_guard/tool.json`
- Create: `tool/official/agent_loop_guard/run.py`
- Create: `backend/tests/test_agent_loop_guard_tool.py`

- [ ] **Step 1: Write the failing Tool test**

Create `backend/tests/test_agent_loop_guard_tool.py` with:

```python
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOOL_DIR = REPO_ROOT / "tool" / "official" / "agent_loop_guard"

sys.path.insert(0, str(BACKEND_ROOT))


def _load_guard_tool_module():
    script_path = TOOL_DIR / "run.py"
    spec = importlib.util.spec_from_file_location("agent_loop_guard_tool", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load agent_loop_guard tool module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentLoopGuardToolTests(unittest.TestCase):
    def test_official_catalog_exposes_agent_loop_guard_tool(self) -> None:
        from app.graph_tools.definitions import list_tool_catalog
        from app.graph_tools.registry import get_tool_registry

        catalog = {tool.tool_key: tool for tool in list_tool_catalog(include_disabled=True)}
        definition = catalog.get("agent_loop_guard")

        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "Agent Loop Guard")
        self.assertIn("capability budget", definition.description)
        self.assertIn("agent_loop_control", [field.key for field in definition.input_schema])
        self.assertIn("agent_loop_report", [field.key for field in definition.output_schema])
        self.assertIn("agent_loop_guard", get_tool_registry(include_disabled=True).keys())

    def test_guard_initializes_control_and_allows_first_successful_call(self) -> None:
        module = _load_guard_tool_module()

        result = module.agent_loop_guard(
            {
                "selected_capability": {"kind": "tool", "toolKey": "buddy_session_recall"},
                "capability_result": {"kind": "result_package", "status": "succeeded", "outputs": {"answer": {"value": "ok"}}},
            }
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(result["agent_loop_should_continue"])
        self.assertFalse(result["agent_loop_should_retry"])
        self.assertEqual(result["agent_loop_stop_reason"], "")
        self.assertEqual(result["agent_loop_control"]["iteration_index"], 1)
        self.assertEqual(result["agent_loop_control"]["capability_call_count"], 1)
        self.assertEqual(result["agent_loop_report"]["decision"], "continue")
        self.assertEqual(result["agent_loop_report"]["selected_capability_key"], "buddy_session_recall")

    def test_guard_stops_when_capability_budget_is_reached(self) -> None:
        module = _load_guard_tool_module()

        result = module.agent_loop_guard(
            {
                "agent_loop_control": {
                    "version": 1,
                    "iteration_index": 3,
                    "max_iterations": 6,
                    "capability_call_count": 3,
                    "max_capability_calls": 4,
                    "failure_count_by_key": {},
                    "last_stop_reason": "",
                    "retry_budget": 1,
                    "warnings": [],
                },
                "selected_capability": {"kind": "action", "actionKey": "expensive_action"},
                "capability_result": {"kind": "result_package", "status": "succeeded", "outputs": {"value": {"value": "done"}}},
            }
        )

        self.assertFalse(result["agent_loop_should_continue"])
        self.assertFalse(result["agent_loop_should_retry"])
        self.assertEqual(result["agent_loop_stop_reason"], "capability_budget_exhausted")
        self.assertEqual(result["agent_loop_report"]["decision"], "stop")
        self.assertEqual(result["agent_loop_control"]["capability_call_count"], 4)

    def test_guard_allows_one_retry_then_stops_repeated_failure(self) -> None:
        module = _load_guard_tool_module()

        first = module.agent_loop_guard(
            {
                "agent_loop_control": {"retry_budget": 1, "max_iterations": 6, "max_capability_calls": 4},
                "selected_capability": {"kind": "tool", "toolKey": "search_tool"},
                "capability_result": {"status": "failed", "error_type": "tool_runtime_error", "error": "boom"},
            }
        )
        second = module.agent_loop_guard(
            {
                "agent_loop_control": first["agent_loop_control"],
                "selected_capability": {"kind": "tool", "toolKey": "search_tool"},
                "capability_result": {"status": "failed", "error_type": "tool_runtime_error", "error": "boom again"},
            }
        )

        self.assertTrue(first["agent_loop_should_continue"])
        self.assertTrue(first["agent_loop_should_retry"])
        self.assertEqual(first["agent_loop_report"]["decision"], "retry")
        self.assertFalse(second["agent_loop_should_continue"])
        self.assertFalse(second["agent_loop_should_retry"])
        self.assertEqual(second["agent_loop_stop_reason"], "tool_failed")
        self.assertEqual(second["agent_loop_control"]["failure_count_by_key"]["tool:search_tool"], 2)

    def test_guard_maps_permission_provider_and_context_failures(self) -> None:
        module = _load_guard_tool_module()

        permission = module.agent_loop_guard(
            {
                "selected_capability": {"kind": "action", "actionKey": "write_file"},
                "capability_result": {"status": "permission_required"},
            }
        )
        provider = module.agent_loop_guard(
            {
                "selected_capability": {"kind": "action", "actionKey": "model_backed_action"},
                "capability_result": {"status": "failed", "error_type": "provider_timeout"},
            }
        )
        context = module.agent_loop_guard(
            {
                "selected_capability": {"kind": "tool", "toolKey": "history_loader"},
                "capability_result": {"status": "succeeded"},
                "context_budget_report": {"reason": "overflow_recovery", "should_compact": False},
            }
        )

        self.assertEqual(permission["agent_loop_stop_reason"], "permission_required")
        self.assertEqual(provider["agent_loop_report"]["last_result_stop_reason"], "provider_failed")
        self.assertEqual(context["agent_loop_stop_reason"], "context_budget_exhausted")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing Tool test**

Run:

```bash
python -m pytest backend/tests/test_agent_loop_guard_tool.py -q
```

Expected: fail because `tool/official/agent_loop_guard/run.py` and manifest do not exist.

- [ ] **Step 3: Add the Tool manifest**

Create `tool/official/agent_loop_guard/tool.json`:

```json
{
  "schemaVersion": "toograph.tool/v1",
  "toolKey": "agent_loop_guard",
  "name": "Agent Loop Guard",
  "description": "A deterministic Agent loop guard that updates iteration and capability budget state, classifies capability failures, and emits standard stop reasons.",
  "version": "0.1.0",
  "timeoutSeconds": 30,
  "permissions": [],
  "runtime": {
    "type": "python",
    "entrypoint": "run.py",
    "timeoutSeconds": 30
  },
  "inputSchema": [
    {
      "key": "agent_loop_control",
      "name": "Agent Loop Control",
      "valueType": "json",
      "description": "Current loop counters, budgets, retry budget, failure counts, and warnings."
    },
    {
      "key": "capability_trace",
      "name": "Capability Trace",
      "valueType": "json",
      "description": "LLM-maintained capability trace from the Buddy loop."
    },
    {
      "key": "selected_capability",
      "name": "Selected Capability",
      "valueType": "capability",
      "description": "The capability that was just executed."
    },
    {
      "key": "capability_result",
      "name": "Capability Result",
      "valueType": "result_package",
      "description": "The raw structured result package from the latest capability execution."
    },
    {
      "key": "context_budget_report",
      "name": "Context Budget Report",
      "valueType": "json",
      "description": "Latest context pressure report, if available."
    }
  ],
  "outputSchema": [
    {
      "key": "agent_loop_control",
      "name": "Updated Agent Loop Control",
      "valueType": "json",
      "description": "Updated loop counters, budgets, retry state, failure counts, and warnings."
    },
    {
      "key": "agent_loop_report",
      "name": "Agent Loop Report",
      "valueType": "json",
      "description": "Human-readable audit report for RunDetail and Buddy capsules."
    },
    {
      "key": "agent_loop_stop_reason",
      "name": "Agent Loop Stop Reason",
      "valueType": "text",
      "description": "A standard stop reason, or empty string when the loop may continue."
    },
    {
      "key": "agent_loop_should_continue",
      "name": "Should Continue",
      "valueType": "boolean",
      "description": "True when the graph should continue to context pressure check and the next selector round."
    },
    {
      "key": "agent_loop_should_retry",
      "name": "Should Retry",
      "valueType": "boolean",
      "description": "True when the latest failure is still inside retry budget."
    },
    {
      "key": "reason",
      "name": "Reason",
      "valueType": "text",
      "description": "Short guard decision reason."
    }
  ]
}
```

- [ ] **Step 4: Add the deterministic Tool implementation**

Create `tool/official/agent_loop_guard/run.py`:

```python
from __future__ import annotations

import json
import sys
from typing import Any


DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_CAPABILITY_CALLS = 4
DEFAULT_RETRY_BUDGET = 1

STANDARD_AGENT_STOP_REASONS = {
    "completed",
    "needs_user_clarification",
    "max_iterations_reached",
    "capability_budget_exhausted",
    "permission_required",
    "provider_failed",
    "tool_failed",
    "graph_validation_failed",
    "context_budget_exhausted",
}


def agent_loop_guard(payload: dict[str, Any] | None) -> dict[str, Any]:
    inputs = payload if isinstance(payload, dict) else {}
    selected_capability = _record(inputs.get("selected_capability"))
    capability_result = _record(inputs.get("capability_result"))
    context_budget_report = _record(inputs.get("context_budget_report"))
    previous_control = _record(inputs.get("agent_loop_control"))

    control = _normalize_control(previous_control)
    control["iteration_index"] += 1
    control["capability_call_count"] += 1

    capability_kind = _normalize_text(selected_capability.get("kind")) or "none"
    capability_key = _capability_key(selected_capability, capability_kind)
    result_status = _result_status(capability_result)
    result_stop_reason = _classify_result_stop_reason(capability_result, capability_kind)
    context_stop_reason = _classify_context_stop_reason(context_budget_report)
    stop_reason = context_stop_reason or result_stop_reason
    should_retry = False
    decision = "continue"
    warnings = list(control.get("warnings") if isinstance(control.get("warnings"), list) else [])

    if result_stop_reason in {"provider_failed", "tool_failed"}:
        failure_count_by_key = _record(control.get("failure_count_by_key"))
        failure_count = int(failure_count_by_key.get(capability_key) or 0) + 1
        failure_count_by_key[capability_key] = failure_count
        control["failure_count_by_key"] = failure_count_by_key
        should_retry = failure_count <= control["retry_budget"]
        decision = "retry" if should_retry else "stop"
        if should_retry:
            stop_reason = ""
        else:
            stop_reason = result_stop_reason
    elif capability_key != "none:none":
        control["failure_count_by_key"] = _record(control.get("failure_count_by_key"))

    if not stop_reason and control["iteration_index"] >= control["max_iterations"]:
        stop_reason = "max_iterations_reached"
        decision = "stop"
    if not stop_reason and control["capability_call_count"] >= control["max_capability_calls"]:
        stop_reason = "capability_budget_exhausted"
        decision = "stop"
    if stop_reason == "permission_required":
        decision = "stop"
        should_retry = False
    if stop_reason == "context_budget_exhausted":
        decision = "stop"
        should_retry = False

    if stop_reason and stop_reason not in STANDARD_AGENT_STOP_REASONS:
        warnings.append(f"Unknown stop reason normalized to tool_failed: {stop_reason}")
        stop_reason = "tool_failed"

    control["last_stop_reason"] = stop_reason
    control["warnings"] = _dedupe_texts(warnings)
    should_continue = not bool(stop_reason)

    report = {
        "version": 1,
        "decision": decision,
        "stop_reason": stop_reason,
        "iteration_index": control["iteration_index"],
        "max_iterations": control["max_iterations"],
        "capability_call_count": control["capability_call_count"],
        "max_capability_calls": control["max_capability_calls"],
        "selected_capability_kind": capability_kind,
        "selected_capability_key": capability_key.split(":", 1)[1] if ":" in capability_key else capability_key,
        "selected_capability_ref": capability_key,
        "last_result_status": result_status,
        "last_result_stop_reason": result_stop_reason,
        "context_stop_reason": context_stop_reason,
        "retry_budget": control["retry_budget"],
        "warnings": control["warnings"],
    }
    return {
        "status": "succeeded",
        "agent_loop_control": control,
        "agent_loop_report": report,
        "agent_loop_stop_reason": stop_reason,
        "agent_loop_should_continue": should_continue,
        "agent_loop_should_retry": should_retry,
        "reason": decision,
    }


def _normalize_control(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "iteration_index": _non_negative_int(value.get("iteration_index"), 0),
        "max_iterations": _positive_int(value.get("max_iterations"), DEFAULT_MAX_ITERATIONS),
        "capability_call_count": _non_negative_int(value.get("capability_call_count"), 0),
        "max_capability_calls": _positive_int(value.get("max_capability_calls"), DEFAULT_MAX_CAPABILITY_CALLS),
        "failure_count_by_key": _record(value.get("failure_count_by_key")),
        "last_stop_reason": _normalize_text(value.get("last_stop_reason")),
        "retry_budget": _non_negative_int(value.get("retry_budget"), DEFAULT_RETRY_BUDGET),
        "warnings": _dedupe_texts(value.get("warnings") if isinstance(value.get("warnings"), list) else []),
    }


def _classify_result_stop_reason(result: dict[str, Any], capability_kind: str) -> str:
    status = _result_status(result)
    error_type = _normalize_text(result.get("error_type") or result.get("errorType"))
    if status in {"permission_required", "awaiting_permission", "awaiting_human"}:
        return "permission_required"
    if status not in {"failed", "error"} and not error_type:
        return ""
    if any(token in error_type for token in ("provider", "model", "llm", "openai", "api_timeout", "rate_limit")):
        return "provider_failed"
    if capability_kind in {"tool", "action", "subgraph"}:
        return "tool_failed"
    return "tool_failed"


def _classify_context_stop_reason(report: dict[str, Any]) -> str:
    reason = _normalize_text(report.get("reason"))
    should_compact = report.get("should_compact")
    if reason == "overflow_recovery" and should_compact is False:
        return "context_budget_exhausted"
    return ""


def _result_status(result: dict[str, Any]) -> str:
    status = _normalize_text(result.get("status"))
    if status:
        return status
    outputs = result.get("outputs")
    if isinstance(outputs, dict) and outputs:
        return "succeeded"
    return ""


def _capability_key(capability: dict[str, Any], capability_kind: str) -> str:
    key = (
        _normalize_text(capability.get("actionKey"))
        or _normalize_text(capability.get("action_key"))
        or _normalize_text(capability.get("toolKey"))
        or _normalize_text(capability.get("tool_key"))
        or _normalize_text(capability.get("subgraphKey"))
        or _normalize_text(capability.get("subgraph_key"))
        or _normalize_text(capability.get("key"))
        or "none"
    )
    return f"{capability_kind}:{key}"


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _dedupe_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


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
    print(json.dumps(agent_loop_guard(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run Tool tests**

Run:

```bash
python -m pytest backend/tests/test_agent_loop_guard_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Tool contract**

Run:

```bash
git add tool/official/agent_loop_guard backend/tests/test_agent_loop_guard_tool.py
git commit -m "新增Agent循环守卫工具"
```

---

### Task 2: Add Run-Level Stop Reason Resolver

**Files:**

- Create: `backend/app/core/runtime/agent_stop_reason.py`
- Modify: `backend/app/core/langgraph/finalization.py`
- Modify: `backend/app/core/runtime/run_artifacts.py`
- Modify: `backend/app/core/storage/graph_run_db_store.py`
- Modify: `backend/app/core/schemas/run.py`
- Test: `backend/tests/test_run_agent_stop_reason.py`

- [ ] **Step 1: Write resolver tests**

Create `backend/tests/test_run_agent_stop_reason.py`:

```python
from __future__ import annotations

from app.core.runtime.agent_stop_reason import resolve_agent_stop_reason, set_agent_stop_reason


def test_resolve_agent_stop_reason_prefers_explicit_graph_state() -> None:
    run_state = {
        "status": "completed",
        "state_values": {"agent_loop_stop_reason": "capability_budget_exhausted"},
        "cycle_summary": {"stop_reason": "completed"},
    }

    assert resolve_agent_stop_reason(run_state) == "capability_budget_exhausted"


def test_resolve_agent_stop_reason_maps_cycle_limit() -> None:
    run_state = {
        "status": "completed",
        "state_values": {},
        "cycle_summary": {"stop_reason": "max_iterations_exceeded"},
    }

    assert resolve_agent_stop_reason(run_state) == "max_iterations_reached"


def test_resolve_agent_stop_reason_maps_permission_metadata() -> None:
    run_state = {
        "status": "awaiting_human",
        "metadata": {"pending_permission_approval": {"capability_key": "write_file"}},
    }

    assert resolve_agent_stop_reason(run_state) == "permission_required"


def test_resolve_agent_stop_reason_classifies_provider_and_graph_failures() -> None:
    provider_state = {"status": "failed", "errors": ["OpenAI provider timeout while calling model"]}
    graph_state = {"status": "failed", "errors": ["Graph validation failed: missing node"]}

    assert resolve_agent_stop_reason(provider_state) == "provider_failed"
    assert resolve_agent_stop_reason(graph_state) == "graph_validation_failed"


def test_set_agent_stop_reason_stores_value_on_run_state() -> None:
    run_state = {"status": "completed", "state_values": {}}

    set_agent_stop_reason(run_state)

    assert run_state["stop_reason"] == "completed"
```

- [ ] **Step 2: Run failing resolver tests**

Run:

```bash
python -m pytest backend/tests/test_run_agent_stop_reason.py -q
```

Expected: fail because `backend/app/core/runtime/agent_stop_reason.py` does not exist.

- [ ] **Step 3: Implement resolver**

Create `backend/app/core/runtime/agent_stop_reason.py`:

```python
from __future__ import annotations

from typing import Any


STANDARD_AGENT_STOP_REASONS = {
    "completed",
    "needs_user_clarification",
    "max_iterations_reached",
    "capability_budget_exhausted",
    "permission_required",
    "provider_failed",
    "tool_failed",
    "graph_validation_failed",
    "context_budget_exhausted",
}

_CYCLE_STOP_REASON_MAP = {
    "completed": "completed",
    "max_iterations_exceeded": "max_iterations_reached",
    "no_state_change": "max_iterations_reached",
}


def resolve_agent_stop_reason(run_state: dict[str, Any]) -> str:
    state_values = _record(run_state.get("state_values"))
    explicit = _normalize_stop_reason(state_values.get("agent_loop_stop_reason"))
    if explicit:
        return explicit

    metadata = _record(run_state.get("metadata"))
    if _record(metadata.get("pending_permission_approval")):
        return "permission_required"
    pending_subgraph = _record(metadata.get("pending_subgraph_breakpoint"))
    pending_subgraph_metadata = _record(pending_subgraph.get("metadata"))
    if _record(pending_subgraph_metadata.get("pending_permission_approval")):
        return "permission_required"

    cycle_summary = _record(run_state.get("cycle_summary"))
    cycle_reason = _CYCLE_STOP_REASON_MAP.get(_text(cycle_summary.get("stop_reason")))
    if cycle_reason:
        return cycle_reason

    status = _text(run_state.get("status"))
    errors = " ".join(_text(error) for error in run_state.get("errors", []) if _text(error)).lower()
    if status == "failed":
        if any(token in errors for token in ("provider", "model", "openai", "rate limit", "timeout")):
            return "provider_failed"
        if any(token in errors for token in ("validation", "missing node", "graph")):
            return "graph_validation_failed"
        return "tool_failed"
    if status == "awaiting_human":
        return "permission_required"
    if status == "completed":
        return "completed"
    return ""


def set_agent_stop_reason(run_state: dict[str, Any]) -> None:
    stop_reason = resolve_agent_stop_reason(run_state)
    if stop_reason:
        run_state["stop_reason"] = stop_reason


def _normalize_stop_reason(value: Any) -> str:
    text = _text(value)
    return text if text in STANDARD_AGENT_STOP_REASONS else ""


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
```

- [ ] **Step 4: Wire resolver into finalization**

Modify `backend/app/core/langgraph/finalization.py`:

```python
from app.core.runtime.agent_stop_reason import set_agent_stop_reason
```

In `finalize_completed_langgraph_state`, call `set_agent_stop_reason_func` after `finalize_cycle_summary_func` and before `refresh_run_artifacts_func`:

```python
def finalize_completed_langgraph_state(
    ...
    finalize_cycle_summary_func: Callable[..., None] = finalize_langgraph_cycle_summary,
    set_agent_stop_reason_func: Callable[..., None] = set_agent_stop_reason,
    sync_checkpoint_metadata_func: Callable[..., None] = sync_checkpoint_metadata,
    ...
) -> dict[str, Any]:
    ...
    finalize_cycle_summary_func(state, cycle_tracker, active_edge_ids)
    set_agent_stop_reason_func(state)
    sync_checkpoint_metadata_func(state, checkpoint_saver, checkpoint_lookup_config)
    refresh_run_artifacts_func(state, node_outputs, active_edge_ids, started_perf=started_perf)
```

In `finalize_failed_langgraph_state`, call `set_agent_stop_reason_func` before `refresh_run_artifacts_func`:

```python
def finalize_failed_langgraph_state(
    ...
    set_run_status_func: Callable[..., None] = set_run_status,
    set_agent_stop_reason_func: Callable[..., None] = set_agent_stop_reason,
    sync_checkpoint_metadata_func: Callable[..., None] = sync_checkpoint_metadata,
    ...
) -> dict[str, Any]:
    ...
    set_run_status_func(state, "failed")
    state.setdefault("errors", []).append(error)
    set_agent_stop_reason_func(state)
    sync_checkpoint_metadata_func(state, checkpoint_saver, checkpoint_lookup_config)
```

- [ ] **Step 5: Persist `stop_reason` through artifacts and detail JSON**

Modify `backend/app/core/runtime/run_artifacts.py` so `refresh_run_artifacts` includes:

```python
"stop_reason": str(state.get("stop_reason") or ""),
```

inside `state["artifacts"]`.

Modify `backend/app/core/storage/graph_run_db_store.py`:

```python
DETAIL_KEYS = (
    "max_revision_round",
    "stop_reason",
    ...
)
```

And in `_build_run_state`, after `final_score`:

```python
"stop_reason": state.get("stop_reason") or artifact_payload.get("stop_reason") or "",
```

- [ ] **Step 6: Expose stop reason in Pydantic schema**

Modify `backend/app/core/schemas/run.py`:

```python
class RunSummary(BaseModel):
    ...
    final_score: float | None = None
    stop_reason: str = ""
```

`RunDetail` inherits this field.

- [ ] **Step 7: Run backend resolver and run route tests**

Run:

```bash
python -m pytest backend/tests/test_run_agent_stop_reason.py backend/tests/test_routes_runs.py backend/tests/test_graph_run_db_store.py -q
```

Expected: pass.

- [ ] **Step 8: Commit stop reason plumbing**

Run:

```bash
git add backend/app/core/runtime/agent_stop_reason.py backend/app/core/langgraph/finalization.py backend/app/core/runtime/run_artifacts.py backend/app/core/storage/graph_run_db_store.py backend/app/core/schemas/run.py backend/tests/test_run_agent_stop_reason.py
git commit -m "标准化图运行停止原因"
```

---

### Task 3: Wire Guard Into Official Buddy Main Loop

**Files:**

- Modify: `graph_template/official/buddy_autonomous_loop/template.json`
- Modify: `backend/tests/test_template_layouts.py`
- Modify: `scripts/capability-selector-loop.test.mjs`

- [ ] **Step 1: Update template layout test first**

In `backend/tests/test_template_layouts.py::test_buddy_autonomous_loop_contract`, update expected metadata:

```python
self.assertEqual(
    template["metadata"]["requiredTools"],
    ["buddy_history_context_loader", "buddy_context_pressure_check", "agent_loop_guard"],
)
```

Update expected states by adding:

```python
"agent_loop_control",
"agent_loop_report",
"agent_loop_stop_reason",
"agent_loop_should_continue",
"agent_loop_should_retry",
```

Add expected state types:

```python
"agent_loop_control": "json",
"agent_loop_report": "json",
"agent_loop_stop_reason": "text",
"agent_loop_should_continue": "boolean",
"agent_loop_should_retry": "boolean",
```

Add binding assertions:

```python
self.assertEqual(states["agent_loop_control"]["binding"]["toolKey"], "agent_loop_guard")
self.assertEqual(states["agent_loop_control"]["binding"]["nodeId"], "guard_agent_loop")
self.assertEqual(states["agent_loop_report"]["binding"]["fieldKey"], "agent_loop_report")
self.assertEqual(states["agent_loop_stop_reason"]["binding"]["fieldKey"], "agent_loop_stop_reason")
self.assertEqual(states["agent_loop_should_continue"]["binding"]["fieldKey"], "agent_loop_should_continue")
self.assertEqual(states["agent_loop_should_retry"]["binding"]["fieldKey"], "agent_loop_should_retry")
```

Update expected node set by adding:

```python
"guard_agent_loop",
"agent_loop_continue_condition",
"finalize_guard_stop",
```

Add node assertions:

```python
self.assertEqual(nodes["guard_agent_loop"]["kind"], "tool")
self.assertEqual(nodes["guard_agent_loop"]["config"]["toolKey"], "agent_loop_guard")
self.assertEqual(nodes["agent_loop_continue_condition"]["kind"], "condition")
self.assertEqual(nodes["finalize_guard_stop"]["kind"], "agent")
self.assertIn({"state": "agent_loop_control", "required": False}, _read_contracts(nodes["reply_and_select_capability"]["reads"]))
self.assertIn({"state": "agent_loop_report", "required": False}, _read_contracts(nodes["reply_and_select_capability"]["reads"]))
self.assertIn({"state": "agent_loop_report", "required": True}, _read_contracts(nodes["finalize_guard_stop"]["reads"]))
self.assertEqual(nodes["finalize_guard_stop"]["writes"], [{"state": "public_response", "mode": "replace"}])
```

Update expected edges:

```python
self.assertEqual(
    template["edges"],
    [
        {"source": "input_user_message", "target": "load_history_context"},
        {"source": "load_history_context", "target": "check_context_pressure"},
        {"source": "input_buddy_context", "target": "check_context_pressure"},
        {"source": "check_context_pressure", "target": "context_pressure_condition"},
        {"source": "run_context_compaction", "target": "reply_and_select_capability"},
        {"source": "execute_capability", "target": "guard_agent_loop"},
        {"source": "guard_agent_loop", "target": "agent_loop_continue_condition"},
        {"source": "finalize_guard_stop", "target": "output_161c76f3"},
        {"source": "reply_and_select_capability", "target": "output_161c76f3"},
        {"source": "reply_and_select_capability", "target": "condition_93972e3f"},
    ],
)
```

Update conditional edges by adding:

```python
{
    "source": "agent_loop_continue_condition",
    "branches": {
        "true": "check_context_pressure",
        "false": "finalize_guard_stop",
        "exhausted": "finalize_guard_stop",
    },
}
```

- [ ] **Step 2: Run failing template test**

Run:

```bash
python -m pytest backend/tests/test_template_layouts.py::OfficialTemplateLayoutTests::test_buddy_autonomous_loop_contract -q
```

Expected: fail until template is updated.

- [ ] **Step 3: Update template state schema**

Modify `graph_template/official/buddy_autonomous_loop/template.json` state schema with these entries:

```json
"agent_loop_control": {
  "name": "Agent 循环控制",
  "description": "由 agent_loop_guard 维护的循环预算、能力调用次数、失败计数、重试预算和停止原因。",
  "type": "json",
  "value": {
    "version": 1,
    "iteration_index": 0,
    "max_iterations": 6,
    "capability_call_count": 0,
    "max_capability_calls": 4,
    "failure_count_by_key": {},
    "last_stop_reason": "",
    "retry_budget": 1,
    "warnings": []
  },
  "color": "#9333ea",
  "binding": {
    "kind": "tool_output",
    "actionKey": "",
    "toolKey": "agent_loop_guard",
    "nodeId": "guard_agent_loop",
    "fieldKey": "agent_loop_control",
    "managed": true
  }
},
"agent_loop_report": {
  "name": "Agent 循环诊断",
  "description": "agent_loop_guard 输出的本轮循环诊断，用于 RunDetail 和 Buddy 胶囊展示。",
  "type": "json",
  "value": {},
  "color": "#7c3aed",
  "binding": {
    "kind": "tool_output",
    "actionKey": "",
    "toolKey": "agent_loop_guard",
    "nodeId": "guard_agent_loop",
    "fieldKey": "agent_loop_report",
    "managed": true
  }
},
"agent_loop_stop_reason": {
  "name": "Agent 停止原因",
  "description": "agent_loop_guard 产出的标准停止原因；为空表示当前循环可继续。",
  "type": "text",
  "value": "",
  "color": "#be123c",
  "binding": {
    "kind": "tool_output",
    "actionKey": "",
    "toolKey": "agent_loop_guard",
    "nodeId": "guard_agent_loop",
    "fieldKey": "agent_loop_stop_reason",
    "managed": true
  }
},
"agent_loop_should_continue": {
  "name": "Agent 循环继续",
  "description": "为 true 时能力结果回到上下文压力检查；为 false 时进入停止说明。",
  "type": "boolean",
  "value": true,
  "color": "#16a34a",
  "binding": {
    "kind": "tool_output",
    "actionKey": "",
    "toolKey": "agent_loop_guard",
    "nodeId": "guard_agent_loop",
    "fieldKey": "agent_loop_should_continue",
    "managed": true
  }
},
"agent_loop_should_retry": {
  "name": "Agent 可重试",
  "description": "为 true 时最近一次能力失败仍在重试预算内，后续选择节点可据此重试或降级。",
  "type": "boolean",
  "value": false,
  "color": "#f59e0b",
  "binding": {
    "kind": "tool_output",
    "actionKey": "",
    "toolKey": "agent_loop_guard",
    "nodeId": "guard_agent_loop",
    "fieldKey": "agent_loop_should_retry",
    "managed": true
  }
}
```

- [ ] **Step 4: Update template metadata**

Set:

```json
"templateVersion": "2026-05-27-agent-loop-guard",
"requiredTools": [
  "buddy_history_context_loader",
  "buddy_context_pressure_check",
  "agent_loop_guard"
]
```

- [ ] **Step 5: Add guard Tool node**

Add node `guard_agent_loop`:

```json
"guard_agent_loop": {
  "kind": "tool",
  "name": "Agent 循环守卫",
  "description": "在每次动态能力执行后更新循环预算、失败计数和停止原因。",
  "ui": {
    "position": {
      "x": 5480,
      "y": 452
    },
    "collapsed": false,
    "size": null
  },
  "reads": [
    {
      "state": "agent_loop_control",
      "required": false,
      "binding": {
        "kind": "tool_input",
        "actionKey": "",
        "toolKey": "agent_loop_guard",
        "fieldKey": "agent_loop_control",
        "managed": true
      }
    },
    {
      "state": "capability_trace",
      "required": false,
      "binding": {
        "kind": "tool_input",
        "actionKey": "",
        "toolKey": "agent_loop_guard",
        "fieldKey": "capability_trace",
        "managed": true
      }
    },
    {
      "state": "selected_capability",
      "required": false,
      "binding": {
        "kind": "tool_input",
        "actionKey": "",
        "toolKey": "agent_loop_guard",
        "fieldKey": "selected_capability",
        "managed": true
      }
    },
    {
      "state": "capability_result",
      "required": false,
      "binding": {
        "kind": "tool_input",
        "actionKey": "",
        "toolKey": "agent_loop_guard",
        "fieldKey": "capability_result",
        "managed": true
      }
    },
    {
      "state": "context_budget_report",
      "required": false,
      "binding": {
        "kind": "tool_input",
        "actionKey": "",
        "toolKey": "agent_loop_guard",
        "fieldKey": "context_budget_report",
        "managed": true
      }
    }
  ],
  "writes": [
    {
      "state": "agent_loop_control",
      "mode": "replace"
    },
    {
      "state": "agent_loop_report",
      "mode": "replace"
    },
    {
      "state": "agent_loop_stop_reason",
      "mode": "replace"
    },
    {
      "state": "agent_loop_should_continue",
      "mode": "replace"
    },
    {
      "state": "agent_loop_should_retry",
      "mode": "replace"
    }
  ],
  "config": {
    "toolKey": "agent_loop_guard"
  }
}
```

- [ ] **Step 6: Add guard condition and stop finalizer**

Add node `agent_loop_continue_condition`:

```json
"agent_loop_continue_condition": {
  "kind": "condition",
  "name": "Agent 循环是否继续",
  "description": "根据 agent_loop_guard 的结果决定继续下一轮上下文压力检查或进入停止说明。",
  "ui": {
    "position": {
      "x": 6180,
      "y": 529
    },
    "collapsed": false,
    "size": null
  },
  "reads": [
    {
      "state": "agent_loop_should_continue",
      "required": true,
      "binding": null
    }
  ],
  "writes": [],
  "config": {
    "branches": [
      "true",
      "false",
      "exhausted"
    ],
    "loopLimit": 6,
    "branchMapping": {
      "true": "true",
      "false": "false"
    },
    "rule": {
      "source": "$state.agent_loop_should_continue",
      "operator": "==",
      "value": true
    }
  }
}
```

Add node `finalize_guard_stop`:

```json
"finalize_guard_stop": {
  "kind": "agent",
  "name": "生成循环停止说明",
  "description": "当循环守卫要求停止时，把停止原因、能力结果和预算状态整理成用户可见回复。",
  "ui": {
    "position": {
      "x": 6900,
      "y": 220
    },
    "collapsed": false,
    "size": {
      "width": 520,
      "height": 460
    }
  },
  "reads": [
    {
      "state": "user_message",
      "required": true,
      "binding": null
    },
    {
      "state": "agent_loop_report",
      "required": true,
      "binding": null
    },
    {
      "state": "agent_loop_control",
      "required": false,
      "binding": null
    },
    {
      "state": "capability_result",
      "required": false,
      "binding": null
    },
    {
      "state": "capability_trace",
      "required": false,
      "binding": null
    }
  ],
  "writes": [
    {
      "state": "public_response",
      "mode": "replace"
    }
  ],
  "config": {
    "actionKey": "",
    "actionBindings": [],
    "suspendedFreeWrites": [],
    "actionInstructionBlocks": {},
    "taskInstruction": "读取 user_message、agent_loop_report、agent_loop_control、capability_result 和 capability_trace。根据 agent_loop_report.stop_reason 生成一段完整的用户可见回复：说明当前已完成的工作、停止原因、可用结果和下一步建议。回复只面向本轮用户请求，不发起能力调用。",
    "modelSource": "global",
    "model": "",
    "thinkingMode": "low",
    "temperature": 0.2
  }
}
```

- [ ] **Step 7: Update selector node inputs**

Add these reads to `reply_and_select_capability`:

```json
{
  "state": "agent_loop_control",
  "required": false,
  "binding": null
},
{
  "state": "agent_loop_report",
  "required": false,
  "binding": null
}
```

Append this sentence to `reply_and_select_capability.config.taskInstruction`:

```text
agent_loop_control 和 agent_loop_report 是循环预算与失败诊断上下文；若 agent_loop_report.decision=retry，结合 capability_result 判断重试同一能力、选择替代能力或结束回复。
```

- [ ] **Step 8: Update edges**

Change normal edges so `execute_capability` flows to `guard_agent_loop`, then to `agent_loop_continue_condition`:

```json
[
  { "source": "input_user_message", "target": "load_history_context" },
  { "source": "load_history_context", "target": "check_context_pressure" },
  { "source": "input_buddy_context", "target": "check_context_pressure" },
  { "source": "check_context_pressure", "target": "context_pressure_condition" },
  { "source": "run_context_compaction", "target": "reply_and_select_capability" },
  { "source": "execute_capability", "target": "guard_agent_loop" },
  { "source": "guard_agent_loop", "target": "agent_loop_continue_condition" },
  { "source": "finalize_guard_stop", "target": "output_161c76f3" },
  { "source": "reply_and_select_capability", "target": "output_161c76f3" },
  { "source": "reply_and_select_capability", "target": "condition_93972e3f" }
]
```

Add conditional edge:

```json
{
  "source": "agent_loop_continue_condition",
  "branches": {
    "true": "check_context_pressure",
    "false": "finalize_guard_stop",
    "exhausted": "finalize_guard_stop"
  }
}
```

- [ ] **Step 9: Update capability loop script test**

In `scripts/capability-selector-loop.test.mjs`, assert:

```js
assert.equal(template.nodes.guard_agent_loop.kind, "tool");
assert.equal(template.nodes.guard_agent_loop.config.toolKey, "agent_loop_guard");
assert.equal(template.nodes.agent_loop_continue_condition.kind, "condition");
assert.deepEqual(
  template.conditional_edges.find((edge) => edge.source === "agent_loop_continue_condition").branches,
  {
    true: "check_context_pressure",
    false: "finalize_guard_stop",
    exhausted: "finalize_guard_stop",
  },
);
```

- [ ] **Step 10: Run template and capability loop tests**

Run:

```bash
python -m pytest backend/tests/test_template_layouts.py::OfficialTemplateLayoutTests::test_buddy_autonomous_loop_contract -q
node scripts/capability-selector-loop.test.mjs
```

Expected: pass.

- [ ] **Step 11: Commit template wiring**

Run:

```bash
git add graph_template/official/buddy_autonomous_loop/template.json backend/tests/test_template_layouts.py scripts/capability-selector-loop.test.mjs
git commit -m "接入伙伴主循环循环守卫"
```

---

### Task 4: Add Agent Diagnostic Model For RunDetail

**Files:**

- Create: `frontend/src/pages/agentDiagnosticModel.ts`
- Create: `frontend/src/pages/agentDiagnosticModel.test.ts`
- Modify: `frontend/src/types/run.ts`
- Modify: `frontend/src/pages/runDetailModel.ts`
- Modify: `frontend/src/pages/RunDetailPage.vue`
- Modify: `frontend/src/pages/RunDetailPage.structure.test.ts`

- [ ] **Step 1: Add frontend type field**

Modify `frontend/src/types/run.ts` in `RunSummary`:

```ts
  stop_reason?: string | null;
```

- [ ] **Step 2: Write diagnostic model tests**

Create `frontend/src/pages/agentDiagnosticModel.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import type { RunDetail } from "../types/run.ts";

import { buildAgentDiagnostic } from "./agentDiagnosticModel.ts";

function createRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    run_id: "run_1",
    graph_id: "graph_1",
    graph_name: "Buddy",
    status: "completed",
    runtime_backend: "langgraph",
    lifecycle: { updated_at: "2026-05-27T00:00:00Z", resume_count: 0 },
    checkpoint_metadata: { available: false },
    revision_round: 0,
    started_at: "2026-05-27T00:00:00Z",
    stop_reason: "",
    metadata: {},
    selected_actions: [],
    action_outputs: [],
    selected_tools: [],
    tool_outputs: [],
    selected_capabilities: [],
    capability_outputs: [],
    evaluation_result: {},
    memory_summary: "",
    final_result: "",
    node_status_map: {},
    node_executions: [],
    warnings: [],
    errors: [],
    output_previews: [],
    artifacts: { state_values: {}, node_outputs: {}, activity_events: [] },
    state_snapshot: { values: {}, last_writers: {} },
    graph_snapshot: {},
    cycle_summary: { has_cycle: false, iteration_count: 0, max_iterations: 0, stop_reason: null },
    ...overrides,
  } as RunDetail;
}

test("buildAgentDiagnostic reads loop report from run state values", () => {
  const diagnostic = buildAgentDiagnostic(
    createRun({
      stop_reason: "capability_budget_exhausted",
      artifacts: {
        state_values: {
          agent_loop_report: {
            decision: "stop",
            stop_reason: "capability_budget_exhausted",
            iteration_index: 4,
            max_iterations: 6,
            capability_call_count: 4,
            max_capability_calls: 4,
            selected_capability_ref: "tool:search",
            warnings: ["budget reached"],
          },
        },
      },
    }),
  );

  assert.equal(diagnostic.visible, true);
  assert.equal(diagnostic.stopReason, "capability_budget_exhausted");
  assert.equal(diagnostic.iterationLabel, "4 / 6");
  assert.equal(diagnostic.capabilityBudgetLabel, "4 / 4");
  assert.deepEqual(diagnostic.badges, ["stop: capability_budget_exhausted", "decision: stop", "capability: tool:search"]);
  assert.deepEqual(diagnostic.warnings, ["budget reached"]);
});

test("buildAgentDiagnostic falls back to cycle summary", () => {
  const diagnostic = buildAgentDiagnostic(
    createRun({
      cycle_summary: {
        has_cycle: true,
        iteration_count: 5,
        max_iterations: 5,
        stop_reason: "max_iterations_exceeded",
      },
    }),
  );

  assert.equal(diagnostic.visible, true);
  assert.equal(diagnostic.stopReason, "max_iterations_reached");
  assert.equal(diagnostic.iterationLabel, "5 / 5");
});
```

- [ ] **Step 3: Implement diagnostic model**

Create `frontend/src/pages/agentDiagnosticModel.ts`:

```ts
import type { RunDetail } from "../types/run.ts";

export type AgentDiagnostic = {
  visible: boolean;
  stopReason: string;
  decision: string;
  iterationLabel: string;
  capabilityBudgetLabel: string;
  selectedCapabilityRef: string;
  warnings: string[];
  badges: string[];
};

export function buildAgentDiagnostic(run: RunDetail): AgentDiagnostic {
  const stateValues = recordFromUnknown(run.artifacts?.state_values);
  const report = recordFromUnknown(stateValues.agent_loop_report);
  const cycleSummary = run.cycle_summary ?? run.artifacts?.cycle_summary;
  const rawStopReason =
    normalizeStopReason(run.stop_reason) ||
    normalizeStopReason(report.stop_reason) ||
    normalizeCycleStopReason(cycleSummary?.stop_reason);
  const iterationIndex = numberFromUnknown(report.iteration_index) ?? numberFromUnknown(cycleSummary?.iteration_count);
  const maxIterations = numberFromUnknown(report.max_iterations) ?? numberFromUnknown(cycleSummary?.max_iterations);
  const capabilityCallCount = numberFromUnknown(report.capability_call_count);
  const maxCapabilityCalls = numberFromUnknown(report.max_capability_calls);
  const decision = textFromUnknown(report.decision);
  const selectedCapabilityRef = textFromUnknown(report.selected_capability_ref);
  const warnings = Array.isArray(report.warnings) ? report.warnings.map(textFromUnknown).filter(Boolean) : [];
  const badges = [
    rawStopReason ? `stop: ${rawStopReason}` : "",
    decision ? `decision: ${decision}` : "",
    selectedCapabilityRef ? `capability: ${selectedCapabilityRef}` : "",
  ].filter(Boolean);

  return {
    visible: Boolean(rawStopReason || decision || iterationIndex !== null || capabilityCallCount !== null || warnings.length > 0),
    stopReason: rawStopReason,
    decision,
    iterationLabel: formatBudget(iterationIndex, maxIterations),
    capabilityBudgetLabel: formatBudget(capabilityCallCount, maxCapabilityCalls),
    selectedCapabilityRef,
    warnings,
    badges,
  };
}

function normalizeCycleStopReason(value: unknown) {
  const text = textFromUnknown(value);
  if (text === "max_iterations_exceeded" || text === "no_state_change") {
    return "max_iterations_reached";
  }
  return normalizeStopReason(text);
}

function normalizeStopReason(value: unknown) {
  const text = textFromUnknown(value);
  return text || "";
}

function formatBudget(value: number | null, max: number | null) {
  if (value === null && max === null) {
    return "";
  }
  return `${value ?? "?"} / ${max === -1 ? "unlimited" : max ?? "?"}`;
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textFromUnknown(value: unknown) {
  return typeof value === "string" ? value.trim() : value === null || value === undefined ? "" : String(value).trim();
}

function numberFromUnknown(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
```

- [ ] **Step 4: Re-export from run detail model**

Modify `frontend/src/pages/runDetailModel.ts`:

```ts
export { buildAgentDiagnostic, type AgentDiagnostic } from "./agentDiagnosticModel.ts";
```

- [ ] **Step 5: Add RunDetail structure test**

In `frontend/src/pages/RunDetailPage.structure.test.ts`, add:

```ts
test("RunDetailPage renders Agent Diagnostic from model", () => {
  const source = readFileSync(new URL("./RunDetailPage.vue", import.meta.url), "utf8");
  assert.match(source, /buildAgentDiagnostic/);
  assert.match(source, /run-detail__agent-diagnostic/);
  assert.match(source, /agentDiagnostic\.stopReason/);
});
```

- [ ] **Step 6: Render diagnostic panel**

Modify `frontend/src/pages/RunDetailPage.vue` script imports:

```ts
import { buildAgentDiagnostic } from "./agentDiagnosticModel";
```

Add computed:

```ts
const agentDiagnostic = computed(() => (run.value ? buildAgentDiagnostic(run.value) : null));
```

Add panel near the cycle summary panel:

```vue
<article v-if="agentDiagnostic?.visible" class="run-detail__panel run-detail__agent-diagnostic">
  <div class="run-detail__panel-heading">
    <div>
      <span class="run-detail__section-kicker">{{ t("runDetail.agentDiagnostic") }}</span>
      <h3>{{ agentDiagnostic.stopReason || t("runDetail.agentRunning") }}</h3>
    </div>
  </div>
  <div class="run-detail__badges">
    <span v-for="badge in agentDiagnostic.badges" :key="badge">{{ badge }}</span>
    <span v-if="agentDiagnostic.iterationLabel">{{ t("common.iterations", { count: agentDiagnostic.iterationLabel }) }}</span>
    <span v-if="agentDiagnostic.capabilityBudgetLabel">capabilities {{ agentDiagnostic.capabilityBudgetLabel }}</span>
  </div>
  <p v-for="warning in agentDiagnostic.warnings" :key="warning" class="run-detail__muted">{{ warning }}</p>
</article>
```

Add i18n keys where RunDetail keys live:

```ts
agentDiagnostic: "Agent Diagnostic",
agentRunning: "Running",
```

- [ ] **Step 7: Run frontend model and structure tests**

Run:

```bash
node --test frontend/src/pages/agentDiagnosticModel.test.ts frontend/src/pages/RunDetailPage.structure.test.ts
```

Expected: pass.

- [ ] **Step 8: Commit RunDetail diagnostic**

Run:

```bash
git add frontend/src/types/run.ts frontend/src/pages/agentDiagnosticModel.ts frontend/src/pages/agentDiagnosticModel.test.ts frontend/src/pages/runDetailModel.ts frontend/src/pages/RunDetailPage.vue frontend/src/pages/RunDetailPage.structure.test.ts
git commit -m "展示Agent循环诊断"
```

---

### Task 5: Surface Loop Diagnostics In Buddy Capsules

**Files:**

- Modify: `frontend/src/buddy/buddyOutputTrace.ts`
- Modify: `frontend/src/buddy/buddyOutputTrace.test.ts`

- [ ] **Step 1: Write Buddy capsule test**

Add to `frontend/src/buddy/buddyOutputTrace.test.ts`:

```ts
test("buildBuddyOutputTraceStateFromRunDetail attaches agent loop diagnostics without creating extra capsules", () => {
  const graph = {
    nodes: {
      reply_and_select_capability: { kind: "agent", name: "回复并判断是否调用能力" },
      execute_capability: { kind: "agent", name: "动态能力执行" },
      guard_agent_loop: { kind: "tool", name: "Agent 循环守卫" },
      finalize_guard_stop: { kind: "agent", name: "生成循环停止说明" },
      output_161c76f3: { kind: "output", name: "模型整理回复" },
    },
    edges: [
      { source: "reply_and_select_capability", target: "execute_capability" },
      { source: "execute_capability", target: "guard_agent_loop" },
      { source: "guard_agent_loop", target: "finalize_guard_stop" },
      { source: "finalize_guard_stop", target: "output_161c76f3" },
    ],
  };
  const plan = buildBuddyOutputTracePlan(graph as never);
  const run = {
    run_id: "run_guard",
    status: "completed",
    node_executions: [
      createExecution("reply_and_select_capability", "agent"),
      createExecution("execute_capability", "agent"),
      createExecution("guard_agent_loop", "tool", {
        outputs: {
          agent_loop_report: {
            decision: "stop",
            stop_reason: "capability_budget_exhausted",
            iteration_index: 4,
            max_iterations: 6,
            capability_call_count: 4,
            max_capability_calls: 4,
          },
        },
      }),
      createExecution("finalize_guard_stop", "agent"),
    ],
    artifacts: {
      state_values: {
        agent_loop_report: {
          decision: "stop",
          stop_reason: "capability_budget_exhausted",
          iteration_index: 4,
          max_iterations: 6,
          capability_call_count: 4,
          max_capability_calls: 4,
        },
      },
      output_previews: [{ node_id: "output_161c76f3", source_kind: "state", source_key: "public_response", display_mode: "markdown", persist_enabled: false, persist_format: "md", value: "done" }],
    },
  } as Partial<RunDetail> as RunDetail;

  const state = buildBuddyOutputTraceStateFromRunDetail(run, plan, graph as never);
  const segments = listBuddyOutputTraceSegmentsForDisplay(state, { visibleOutputNodeIds: new Set(["output_161c76f3"]) });

  assert.equal(segments.length, 1);
  assert.ok(segments[0].records.some((record) => record.artifactLabels.includes("stop: capability_budget_exhausted")));
  assert.ok(segments[0].records.some((record) => record.artifactLabels.includes("capabilities: 4 / 4")));
});
```

- [ ] **Step 2: Run failing Buddy capsule test**

Run:

```bash
node --test frontend/src/buddy/buddyOutputTrace.test.ts
```

Expected: fail because guard outputs are not summarized into artifact labels yet.

- [ ] **Step 3: Add guard artifact label extraction**

Modify `frontend/src/buddy/buddyOutputTrace.ts` where node completion payload is built from `NodeExecutionDetail`. Add a helper:

```ts
function buildAgentLoopArtifactLabels(execution: NodeExecutionDetail) {
  const outputs = recordFromUnknown(execution.artifacts?.outputs);
  const report = recordFromUnknown(outputs.agent_loop_report);
  const stopReason = normalizeText(report.stop_reason);
  const decision = normalizeText(report.decision);
  const capabilityCallCount = normalizeNumber(report.capability_call_count);
  const maxCapabilityCalls = normalizeNumber(report.max_capability_calls);
  return [
    stopReason ? `stop: ${stopReason}` : "",
    decision ? `decision: ${decision}` : "",
    capabilityCallCount !== null || maxCapabilityCalls !== null
      ? `capabilities: ${capabilityCallCount ?? "?"} / ${maxCapabilityCalls ?? "?"}`
      : "",
  ].filter(Boolean);
}
```

When creating node-completed trace payload, append these labels to existing artifact labels:

```ts
artifactLabels: [
  ...existingArtifactLabels,
  ...buildAgentLoopArtifactLabels(execution),
],
```

Use the local variable name that already holds artifact labels in `appendExecutionTimelineItems`; keep the current output-boundary segmentation logic unchanged.

- [ ] **Step 4: Run Buddy capsule test**

Run:

```bash
node --test frontend/src/buddy/buddyOutputTrace.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit Buddy capsule diagnostics**

Run:

```bash
git add frontend/src/buddy/buddyOutputTrace.ts frontend/src/buddy/buddyOutputTrace.test.ts
git commit -m "在伙伴胶囊展示循环诊断"
```

---

### Task 6: Add Main Loop Eval Coverage

**Files:**

- Create or modify: `graph_template/official/buddy_autonomous_loop/eval_cases.json`
- Modify: `backend/tests/test_template_layouts.py`

- [ ] **Step 1: Add eval case file**

If `graph_template/official/buddy_autonomous_loop/eval_cases.json` does not exist, create:

```json
{
  "schemaVersion": "toograph.eval-cases/v1",
  "templateId": "buddy_autonomous_loop",
  "cases": [
    {
      "caseId": "capability-budget-exhausted",
      "name": "能力调用预算耗尽",
      "input": {
        "user_message": "连续查找资料直到没有更多信息。"
      },
      "expected": {
        "stateKeys": [
          "agent_loop_control",
          "agent_loop_report",
          "agent_loop_stop_reason"
        ],
        "stopReasons": [
          "capability_budget_exhausted",
          "max_iterations_reached",
          "completed"
        ]
      }
    },
    {
      "caseId": "capability-failure-classified",
      "name": "能力失败被分类",
      "input": {
        "user_message": "调用一个不可用能力并解释失败原因。"
      },
      "expected": {
        "stateKeys": [
          "agent_loop_report"
        ],
        "stopReasons": [
          "tool_failed",
          "provider_failed",
          "completed"
        ]
      }
    }
  ]
}
```

- [ ] **Step 2: Add layout test for eval case availability**

In `backend/tests/test_template_layouts.py`, add:

```python
def test_buddy_autonomous_loop_has_agent_loop_eval_cases(self) -> None:
    eval_path = REPO_ROOT / "graph_template" / "official" / "buddy_autonomous_loop" / "eval_cases.json"
    payload = json.loads(eval_path.read_text(encoding="utf-8"))

    self.assertEqual(payload["schemaVersion"], "toograph.eval-cases/v1")
    self.assertEqual(payload["templateId"], "buddy_autonomous_loop")
    case_ids = {case["caseId"] for case in payload["cases"]}
    self.assertIn("capability-budget-exhausted", case_ids)
    self.assertIn("capability-failure-classified", case_ids)
```

- [ ] **Step 3: Run eval layout test**

Run:

```bash
python -m pytest backend/tests/test_template_layouts.py::OfficialTemplateLayoutTests::test_buddy_autonomous_loop_has_agent_loop_eval_cases -q
```

Expected: pass.

- [ ] **Step 4: Commit eval cases**

Run:

```bash
git add graph_template/official/buddy_autonomous_loop/eval_cases.json backend/tests/test_template_layouts.py
git commit -m "补充伙伴主循环循环守卫评测用例"
```

---

### Task 7: Full Verification And Restart

**Files:** no new files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
python -m pytest \
  backend/tests/test_agent_loop_guard_tool.py \
  backend/tests/test_run_agent_stop_reason.py \
  backend/tests/test_template_layouts.py::OfficialTemplateLayoutTests::test_buddy_autonomous_loop_contract \
  backend/tests/test_template_layouts.py::OfficialTemplateLayoutTests::test_buddy_autonomous_loop_has_agent_loop_eval_cases \
  backend/tests/test_routes_runs.py \
  backend/tests/test_graph_run_db_store.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run focused frontend/script tests**

Run:

```bash
node scripts/capability-selector-loop.test.mjs
node --test frontend/src/pages/agentDiagnosticModel.test.ts frontend/src/pages/RunDetailPage.structure.test.ts frontend/src/buddy/buddyOutputTrace.test.ts
```

Expected: pass.

- [ ] **Step 3: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: `vue-tsc --noEmit && vite build` succeeds.

- [ ] **Step 4: Restart TooGraph**

Run from repo root:

```bash
npm start
```

Expected: server starts on `http://127.0.0.1:3477`; if an existing TooGraph owns the port, startup releases it and reuses the default port.

- [ ] **Step 5: Manual browser check**

Open:

```text
http://127.0.0.1:3477
```

Check:

- Official Buddy template loads.
- Buddy binding page still only binds current user message.
- Running the official Buddy loop records `agent_loop_control` and `agent_loop_report` after a capability call.
- RunDetail shows Agent Diagnostic.
- Buddy visible output capsules are still segmented only by output boundaries.

- [ ] **Step 6: Final commit**

If verification required small fixes after prior commits, commit them:

```bash
git add backend frontend graph_template scripts tool
git commit -m "完成Agent循环守卫接入验证"
```

---

## Self-Review

Spec coverage:

- `agent_loop_control` state: Task 3.
- `agent_loop_guard` Tool: Task 1.
- Buddy main loop guard wiring: Task 3.
- Standard stop reasons in run record: Task 2.
- RunDetail diagnostic: Task 4.
- Buddy capsule display: Task 5.
- Eval coverage: Task 6.
- Verification and restart: Task 7.

Placeholder scan:

- 本文不包含待填写占位符、延后实现标记或未命名文件路径。

Type consistency:

- Tool output fields、state keys、frontend diagnostic keys 使用同一组名称：`agent_loop_control`、`agent_loop_report`、`agent_loop_stop_reason`、`agent_loop_should_continue`、`agent_loop_should_retry`。
- Backend top-level API 字段统一为 `stop_reason`；frontend 类型同步为 `stop_reason?: string | null`。

Execution handoff:

- 推荐使用 `superpowers:subagent-driven-development` 执行本计划，每个 Task 一个干净 subagent，主会话在每个 commit 后 review。
- 也可以使用 `superpowers:executing-plans` 在当前会话逐项执行，Task 3 和 Task 4 之间需要一次人工检查，因为模板 JSON 与 UI 展示同时影响用户可见行为。
