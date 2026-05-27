import assert from "node:assert/strict";
import test from "node:test";

import type { ScheduledGraphJob, ScheduledGraphJobRun } from "@/types/scheduler";

import {
  buildOfficialSchedulerEnableRecommendations,
  buildDefaultScheduledGraphJobDraft,
  buildScheduledGraphJobPayload,
  buildSchedulerOverview,
  formatSchedule,
  sortScheduledGraphJobRuns,
  sortScheduledGraphJobs,
} from "./schedulerPageModel.ts";

test("buildSchedulerOverview summarizes total, enabled, disabled, and official jobs", () => {
  const jobs = [
    createJob("official_embedding_maintenance", true, "official_seed"),
    createJob("official_buddy_capability_curator", false, "official_seed"),
    createJob("user_job", false, "user"),
  ];

  assert.deepEqual(buildSchedulerOverview(jobs), [
    { key: "total", label: "全部任务", value: 3 },
    { key: "enabled", label: "已启用", value: 1 },
    { key: "disabled", label: "已停用", value: 2 },
    { key: "official", label: "官方任务", value: 2 },
  ]);
});

test("buildOfficialSchedulerEnableRecommendations highlights official maintenance jobs by enabled state", () => {
  const jobs = [
    createJob("user_job", false, "user"),
    createJob("official_buddy_capability_curator", false, "official_seed"),
    createJob("official_embedding_maintenance", true, "official_seed"),
  ];

  assert.deepEqual(buildOfficialSchedulerEnableRecommendations(jobs), [
    {
      job_id: "official_buddy_capability_curator",
      title: "能力整理",
      description: "周期性检查能力目录、使用记录和改进候选，生成可审查整理报告。",
      enabled: false,
      template_id: "official_buddy_capability_curator",
      schedule: "每 1 小时",
      action: "enable",
    },
    {
      job_id: "official_embedding_maintenance",
      title: "Embedding 维护",
      description: "定期处理待生成的向量任务，让记忆和检索索引保持可召回。",
      enabled: true,
      template_id: "official_embedding_maintenance",
      schedule: "每 1 小时",
      action: "run",
    },
  ]);
});

test("formatSchedule renders common interval expressions", () => {
  assert.equal(formatSchedule({ schedule_kind: "interval", schedule_expr: "PT168H" }), "每 7 天");
  assert.equal(formatSchedule({ schedule_kind: "interval", schedule_expr: "PT1H" }), "每 1 小时");
  assert.equal(formatSchedule({ schedule_kind: "interval", schedule_expr: "30m" }), "每 30 分钟");
  assert.equal(formatSchedule({ schedule_kind: "manual", schedule_expr: "" }), "手动");
});

test("sortScheduledGraphJobs keeps enabled jobs first and then template order", () => {
  const jobs = [
    createJob("z_disabled", false, "user"),
    createJob("a_enabled", true, "user"),
    { ...createJob("b_enabled", true, "user"), template_id: "aaa_template" },
  ];

  assert.deepEqual(sortScheduledGraphJobs(jobs).map((job) => job.job_id), ["b_enabled", "a_enabled", "z_disabled"]);
});

test("sortScheduledGraphJobRuns orders newest run history first", () => {
  const runs = [
    createJobRun("run_old", "2026-05-27T00:00:00Z"),
    createJobRun("run_new", "2026-05-27T01:00:00Z"),
  ];

  assert.deepEqual(sortScheduledGraphJobRuns(runs).map((run) => run.job_run_id), ["run_new", "run_old"]);
});

test("buildScheduledGraphJobPayload parses input bindings and normalizes manual schedules", () => {
  assert.deepEqual(
    buildScheduledGraphJobPayload({
      ...buildDefaultScheduledGraphJobDraft("template_1"),
      name: " Daily job ",
      schedule_kind: "manual",
      schedule_expr: "PT24H",
      input_bindings_json: '{"prompt":"run"}',
      delivery_target_json: '{"kind":"local_audit","label":"Curator report"}',
      enabled: true,
    }),
    {
      name: "Daily job",
      template_id: "template_1",
      input_bindings: { prompt: "run" },
      delivery_target: { kind: "local_audit", label: "Curator report" },
      schedule_kind: "manual",
      schedule_expr: "",
      timezone: "UTC",
      enabled: true,
      metadata: { source: "user" },
    },
  );
});

test("buildScheduledGraphJobPayload rejects non-object JSON input bindings", () => {
  assert.throws(
    () =>
      buildScheduledGraphJobPayload({
        ...buildDefaultScheduledGraphJobDraft("template_1"),
        input_bindings_json: "[]",
      }),
    /输入绑定必须是 JSON object/,
  );
});

test("buildScheduledGraphJobPayload rejects non-object JSON delivery targets", () => {
  assert.throws(
    () =>
      buildScheduledGraphJobPayload({
        ...buildDefaultScheduledGraphJobDraft("template_1"),
        delivery_target_json: "[]",
      }),
    /投递目标必须是 JSON object/,
  );
});

function createJob(jobId: string, enabled: boolean, source: string): ScheduledGraphJob {
  return {
    job_id: jobId,
    name: jobId,
    template_id: jobId,
    input_bindings: {},
    schedule_kind: "interval",
    schedule_expr: "PT1H",
    timezone: "UTC",
    enabled,
    last_run_id: "",
    next_run_at: "",
    runtime_overrides: {},
    delivery_target: {},
    retry_policy: {},
    metadata: { source },
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
  };
}

function createJobRun(jobRunId: string, createdAt: string): ScheduledGraphJobRun {
  return {
    job_run_id: jobRunId,
    job_id: "job_1",
    run_id: jobRunId,
    trigger_reason: "manual",
    status: "completed",
    error: "",
    started_at: createdAt,
    completed_at: createdAt,
    metadata: {},
    created_at: createdAt,
    updated_at: createdAt,
  };
}
