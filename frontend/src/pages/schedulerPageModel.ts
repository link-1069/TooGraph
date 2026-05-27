import { translate } from "../i18n/index.ts";
import type { ScheduledGraphJob, ScheduledGraphJobCreatePayload, ScheduledGraphJobRun } from "../types/scheduler.ts";

export type ScheduledGraphJobDraft = {
  name: string;
  template_id: string;
  schedule_kind: string;
  schedule_expr: string;
  timezone: string;
  enabled: boolean;
  input_bindings_json: string;
  delivery_target_json: string;
};

export type SchedulerOverviewItem = {
  key: string;
  label: string;
  value: number;
};

export type OfficialSchedulerEnableRecommendation = {
  job_id: string;
  title: string;
  description: string;
  enabled: boolean;
  template_id: string;
  schedule: string;
  action: "enable" | "run";
};

export function buildSchedulerOverview(jobs: ScheduledGraphJob[]): SchedulerOverviewItem[] {
  return [
    { key: "total", label: translate("scheduler.total"), value: jobs.length },
    { key: "enabled", label: translate("scheduler.enabled"), value: jobs.filter((job) => job.enabled).length },
    { key: "disabled", label: translate("scheduler.disabled"), value: jobs.filter((job) => !job.enabled).length },
    { key: "official", label: translate("scheduler.official"), value: jobs.filter((job) => job.metadata?.source === "official_seed").length },
  ];
}

export function buildOfficialSchedulerEnableRecommendations(
  jobs: ScheduledGraphJob[],
): OfficialSchedulerEnableRecommendation[] {
  return sortScheduledGraphJobs(jobs)
    .filter((job) => job.metadata?.source === "official_seed" || job.metadata?.source === "official")
    .sort((left, right) => Number(left.enabled) - Number(right.enabled) || left.job_id.localeCompare(right.job_id))
    .map((job) => ({
      job_id: job.job_id,
      title: officialSchedulerJobTitle(job),
      description: officialSchedulerJobDescription(job),
      enabled: job.enabled,
      template_id: job.template_id,
      schedule: formatSchedule(job),
      action: job.enabled ? "run" : "enable",
    }));
}

export function sortScheduledGraphJobs(jobs: ScheduledGraphJob[]): ScheduledGraphJob[] {
  return [...jobs].sort((left, right) => {
    if (left.enabled !== right.enabled) {
      return left.enabled ? -1 : 1;
    }
    const templateDiff = compareStableText(left.template_id, right.template_id);
    return templateDiff || left.job_id.localeCompare(right.job_id);
  });
}

export function formatSchedule(job: Pick<ScheduledGraphJob, "schedule_kind" | "schedule_expr">): string {
  if (job.schedule_kind === "manual") {
    return translate("scheduler.manual");
  }
  if (job.schedule_kind === "cron") {
    return job.schedule_expr || translate("common.none");
  }
  const seconds = intervalSeconds(job.schedule_expr);
  if (!seconds) {
    return job.schedule_expr || translate("common.none");
  }
  if (seconds % 86_400 === 0) {
    return translate("scheduler.everyDays", { count: seconds / 86_400 });
  }
  if (seconds % 3600 === 0) {
    return translate("scheduler.everyHours", { count: seconds / 3600 });
  }
  if (seconds % 60 === 0) {
    return translate("scheduler.everyMinutes", { count: seconds / 60 });
  }
  return translate("scheduler.everySeconds", { count: seconds });
}

export function normalizeJobRunStatus(status: string): string {
  return status.trim() || "queued";
}

export function sortScheduledGraphJobRuns(runs: ScheduledGraphJobRun[]): ScheduledGraphJobRun[] {
  return [...runs].sort((left, right) => {
    const createdDiff = Date.parse(right.created_at) - Date.parse(left.created_at);
    if (Number.isFinite(createdDiff) && createdDiff !== 0) {
      return createdDiff;
    }
    return right.job_run_id.localeCompare(left.job_run_id);
  });
}

export function buildDefaultScheduledGraphJobDraft(templateId = ""): ScheduledGraphJobDraft {
  return {
    name: "",
    template_id: templateId,
    schedule_kind: "interval",
    schedule_expr: "PT24H",
    timezone: "UTC",
    enabled: false,
    input_bindings_json: "{}",
    delivery_target_json: "{}",
  };
}

export function buildScheduledGraphJobPayload(draft: ScheduledGraphJobDraft): ScheduledGraphJobCreatePayload {
  const templateId = draft.template_id.trim();
  if (!templateId) {
    throw new Error(translate("scheduler.templateRequired"));
  }
  const scheduleKind = draft.schedule_kind.trim() || "manual";
  const inputBindings = parseJsonObject(draft.input_bindings_json, translate("scheduler.inputBindings"));
  const deliveryTarget = parseJsonObject(draft.delivery_target_json, translate("scheduler.deliveryTarget"));
  return {
    name: draft.name.trim(),
    template_id: templateId,
    input_bindings: inputBindings,
    delivery_target: deliveryTarget,
    schedule_kind: scheduleKind,
    schedule_expr: scheduleKind === "manual" ? "" : draft.schedule_expr.trim(),
    timezone: draft.timezone.trim() || "UTC",
    enabled: draft.enabled,
    metadata: { source: "user" },
  };
}

function officialSchedulerJobTitle(job: ScheduledGraphJob): string {
  if (job.job_id === "official_embedding_maintenance") {
    return translate("scheduler.embeddingMaintenanceTask");
  }
  if (job.job_id === "official_buddy_capability_curator") {
    return translate("scheduler.capabilityCuratorTask");
  }
  return job.name || job.job_id;
}

function officialSchedulerJobDescription(job: ScheduledGraphJob): string {
  if (job.job_id === "official_embedding_maintenance") {
    return translate("scheduler.embeddingMaintenanceDescription");
  }
  if (job.job_id === "official_buddy_capability_curator") {
    return translate("scheduler.capabilityCuratorDescription");
  }
  return translate("scheduler.officialMaintenanceDescriptionFallback");
}

function intervalSeconds(value: string): number | null {
  const normalized = value.trim();
  const shortMatch = normalized.match(/^(\d+)([smhd])$/i);
  if (shortMatch) {
    const amount = Number(shortMatch[1]);
    const unit = shortMatch[2].toLowerCase();
    if (unit === "d") return amount * 86_400;
    if (unit === "h") return amount * 3600;
    if (unit === "m") return amount * 60;
    return amount;
  }
  const isoMatch = normalized.match(/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/);
  if (!isoMatch) {
    return null;
  }
  const days = Number(isoMatch[1] || 0);
  const hours = Number(isoMatch[2] || 0);
  const minutes = Number(isoMatch[3] || 0);
  const seconds = Number(isoMatch[4] || 0);
  const total = days * 86_400 + hours * 3600 + minutes * 60 + seconds;
  return total > 0 ? total : null;
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(translate("scheduler.invalidJson", { label }));
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(translate("scheduler.invalidJsonObject", { label }));
  }
  return parsed as Record<string, unknown>;
}

function compareStableText(left: string, right: string): number {
  const leftKey = left.toLowerCase().replace(/[^a-z0-9]+/g, "");
  const rightKey = right.toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (leftKey < rightKey) {
    return -1;
  }
  if (leftKey > rightKey) {
    return 1;
  }
  return left.localeCompare(right);
}
