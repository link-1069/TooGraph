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

test("buildAgentDiagnostic hides completed-only runs without loop evidence", () => {
  const diagnostic = buildAgentDiagnostic(createRun({ stop_reason: "completed" }));

  assert.equal(diagnostic.visible, false);
  assert.equal(diagnostic.stopReason, "completed");
});
