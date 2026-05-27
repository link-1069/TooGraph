import assert from "node:assert/strict";
import test from "node:test";

import type { RunDetail, RunSummary } from "../types/run.ts";

import {
  buildCuratorReportDetail,
  buildCuratorReportItems,
  buildCuratorReportOverview,
  CURATOR_REPORT_TEMPLATE_ID,
} from "./curatorReportsPageModel.ts";

function runSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run_curator_1",
    graph_id: "graph_curator",
    graph_name: "能力库整理",
    template_id: CURATOR_REPORT_TEMPLATE_ID,
    template_version: "1",
    status: "completed",
    runtime_backend: "langgraph",
    lifecycle: { updated_at: "", resume_count: 0 },
    checkpoint_metadata: { available: false },
    revision_round: 0,
    started_at: "2026-05-27T00:00:00Z",
    completed_at: "2026-05-27T00:01:00Z",
    duration_ms: 60000,
    ...overrides,
  };
}

function runDetail(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    ...runSummary(),
    metadata: {},
    children: [],
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
    subgraph_status_map: {},
    node_executions: [],
    warnings: [],
    errors: [],
    output_previews: [],
    artifacts: {},
    state_snapshot: {
      values: {
        curator_report: "## 能力健康\n需要补齐测试。",
        capability_health_report: { score: 82, missing_tests: ["action.demo"] },
        improvement_candidates: [{ candidate_id: "cand_a" }, { candidate_id: "cand_b" }],
        scheduler_recommendation: { cadence: "daily", ready: true },
      },
      last_writers: {},
    },
    graph_snapshot: {},
    run_snapshots: [],
    ...overrides,
  };
}

test("curator report page model sorts curator runs and builds overview metrics", () => {
  const runs = [
    runSummary({ run_id: "run_old", status: "failed", started_at: "2026-05-27T00:00:00Z" }),
    runSummary({ run_id: "run_new", status: "completed", started_at: "2026-05-27T00:02:00Z" }),
    runSummary({ run_id: "run_other", template_id: "buddy_autonomous_loop", started_at: "2026-05-27T00:03:00Z" }),
  ];

  assert.deepEqual(buildCuratorReportItems(runs).map((item) => item.runId), ["run_new", "run_old"]);
  assert.deepEqual(buildCuratorReportOverview(runs), [
    { key: "total", labelKey: "curatorReports.total", value: 2 },
    { key: "completed", labelKey: "curatorReports.completed", value: 1 },
    { key: "failed", labelKey: "curatorReports.failed", value: 1 },
    { key: "latest", labelKey: "curatorReports.latest", value: "run_new" },
  ]);
});

test("curator report page model extracts report state from run detail", () => {
  const detail = buildCuratorReportDetail(runDetail());

  assert.equal(detail.runId, "run_curator_1");
  assert.equal(detail.reportMarkdown, "## 能力健康\n需要补齐测试。");
  assert.equal(detail.candidateCount, 2);
  assert.deepEqual(detail.healthReport, { score: 82, missing_tests: ["action.demo"] });
  assert.deepEqual(detail.schedulerRecommendation, { cadence: "daily", ready: true });
});
