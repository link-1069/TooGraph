import type { RunDetail, RunSummary } from "../types/run.ts";

export const CURATOR_REPORT_TEMPLATE_ID = "buddy_capability_curator";

export type CuratorReportMetric = {
  key: string;
  labelKey: string;
  value: number | string;
};

export type CuratorReportListItem = {
  runId: string;
  graphName: string;
  status: string;
  startedAt: string;
  completedAt: string;
  durationMs: number | null;
};

export type CuratorReportDetail = CuratorReportListItem & {
  reportMarkdown: string;
  healthReport: Record<string, unknown>;
  improvementCandidates: unknown[];
  schedulerRecommendation: Record<string, unknown>;
  candidateCount: number;
  healthScore: string;
};

export function buildCuratorReportItems(runs: RunSummary[]): CuratorReportListItem[] {
  return runs
    .filter((run) => run.template_id === CURATOR_REPORT_TEMPLATE_ID)
    .map((run) => ({
      runId: run.run_id,
      graphName: run.graph_name,
      status: run.status,
      startedAt: run.started_at,
      completedAt: run.completed_at ?? "",
      durationMs: run.duration_ms ?? null,
    }))
    .sort((left, right) => compareIsoDesc(left.startedAt, right.startedAt));
}

export function buildCuratorReportOverview(runs: RunSummary[]): CuratorReportMetric[] {
  const items = buildCuratorReportItems(runs);
  return [
    { key: "total", labelKey: "curatorReports.total", value: items.length },
    {
      key: "completed",
      labelKey: "curatorReports.completed",
      value: items.filter((item) => item.status === "completed").length,
    },
    {
      key: "failed",
      labelKey: "curatorReports.failed",
      value: items.filter((item) => item.status === "failed").length,
    },
    {
      key: "latest",
      labelKey: "curatorReports.latest",
      value: items[0]?.runId ?? "",
    },
  ];
}

export function buildCuratorReportDetail(run: RunDetail): CuratorReportDetail {
  const healthReport = recordValue(readCuratorState(run, "capability_health_report"));
  const improvementCandidates = arrayValue(readCuratorState(run, "improvement_candidates"));
  const schedulerRecommendation = recordValue(readCuratorState(run, "scheduler_recommendation"));
  return {
    runId: run.run_id,
    graphName: run.graph_name,
    status: run.status,
    startedAt: run.started_at,
    completedAt: run.completed_at ?? "",
    durationMs: run.duration_ms ?? null,
    reportMarkdown: stringValue(readCuratorState(run, "curator_report")),
    healthReport,
    improvementCandidates,
    schedulerRecommendation,
    candidateCount: improvementCandidates.length,
    healthScore: stringValue(
      healthReport.score ?? healthReport.health_score ?? healthReport.overall_score ?? "",
    ),
  };
}

function readCuratorState(run: RunDetail, stateKey: string): unknown {
  const value = run.state_snapshot?.values?.[stateKey];
  if (hasMeaningfulValue(value)) {
    return value;
  }
  return run.output_previews?.find((preview) => preview.source_key === stateKey)?.value;
}

function compareIsoDesc(left: string, right: string): number {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
}

function hasMeaningfulValue(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return true;
}

function stringValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
