export type DelegationWorkerDiagnostic = {
  visible: boolean;
  taskId: string;
  status: string;
  summary: string;
  outputLabels: string[];
  artifactLabels: string[];
  errorLabels: string[];
  followupLabels: string[];
  sourceRefLabels: string[];
  workerRunLabels: string[];
  workerRunLinks: DelegationWorkerRunLink[];
  budgetLabels: string[];
  capabilityLabels: string[];
  evidenceLabels: string[];
};

export type DelegationWorkerRunLink = {
  runId: string;
  label: string;
  href: string;
  status: string;
};

export function buildDelegationWorkerDiagnostic(
  value: unknown,
  options: { workerRuns?: unknown[] } = {},
): DelegationWorkerDiagnostic {
  const packageRecord = recordFromUnknown(value);
  const taskId = textFromUnknown(packageRecord.task_id ?? packageRecord.taskId);
  const status = textFromUnknown(packageRecord.status);
  const summary = textFromUnknown(packageRecord.summary);
  const outputLabels = outputLabelsFromPackage(packageRecord);
  const artifactLabels = artifactLabelsFromPackage(packageRecord);
  const errorLabels = errorLabelsFromPackage(packageRecord);
  const followupLabels = followupLabelsFromPackage(packageRecord);
  const sourceRefLabels = sourceRefLabelsFromPackage(packageRecord);
  const workerRunLinks = workerRunLinksFromPackage(packageRecord, options.workerRuns ?? []);
  const workerRunLabels = workerRunLinks.map((link) => `run: ${link.runId}${link.status ? ` ${link.status}` : ""}`);
  const budgetLabels = budgetLabelsFromPackage(packageRecord);
  const capabilityLabels = capabilityLabelsFromPackage(packageRecord);
  const evidenceLabels = [
    taskId ? `worker: ${taskId}` : "",
    status ? `status: ${status}` : "",
    ...outputLabels,
    ...workerRunLabels,
    ...budgetLabels,
    ...capabilityLabels,
  ].filter(Boolean);
  const visible = Boolean(
    taskId
    || status
    || summary
    || outputLabels.length > 0
    || artifactLabels.length > 0
    || errorLabels.length > 0
    || followupLabels.length > 0
    || sourceRefLabels.length > 0
    || workerRunLabels.length > 0
    || budgetLabels.length > 0
    || capabilityLabels.length > 0
  );

  return {
    visible,
    taskId,
    status,
    summary,
    outputLabels,
    artifactLabels,
    errorLabels,
    followupLabels,
    sourceRefLabels,
    workerRunLabels,
    workerRunLinks,
    budgetLabels,
    capabilityLabels,
    evidenceLabels,
  };
}

export function listDelegationWorkerTraceLabels(value: unknown): string[] {
  return buildDelegationWorkerDiagnostic(value).evidenceLabels;
}

function outputLabelsFromPackage(packageRecord: Record<string, unknown>) {
  const outputs = recordFromUnknown(packageRecord.outputs);
  return Object.entries(outputs)
    .map(([key, value]) => {
      const outputKey = textFromUnknown(key);
      if (!outputKey) {
        return "";
      }
      const output = recordFromUnknown(value);
      const type = textFromUnknown(output.type);
      return `output: ${outputKey}${type ? ` (${type})` : ""}`;
    })
    .filter(Boolean);
}

function artifactLabelsFromPackage(packageRecord: Record<string, unknown>) {
  return listFromUnknown(packageRecord.artifacts)
    .map((item) => {
      if (typeof item === "string") {
        return textFromUnknown(item);
      }
      const artifact = recordFromUnknown(item);
      return (
        textFromUnknown(artifact.path)
        || textFromUnknown(artifact.local_path)
        || textFromUnknown(artifact.file_name)
        || textFromUnknown(artifact.artifact_id)
        || textFromUnknown(artifact.id)
        || textFromUnknown(artifact.kind)
      );
    })
    .filter(Boolean)
    .map((label) => `artifact: ${label}`);
}

function errorLabelsFromPackage(packageRecord: Record<string, unknown>) {
  return listFromUnknown(packageRecord.errors)
    .map((item) => {
      if (typeof item === "string") {
        return textFromUnknown(item);
      }
      const error = recordFromUnknown(item);
      return (
        textFromUnknown(error.message)
        || textFromUnknown(error.error)
        || textFromUnknown(error.summary)
        || textFromUnknown(error.error_type)
        || textFromUnknown(error.type)
      );
    })
    .filter(Boolean)
    .map((label) => `error: ${label}`);
}

function followupLabelsFromPackage(packageRecord: Record<string, unknown>) {
  return listFromUnknown(packageRecord.followups)
    .map((item) => {
      if (typeof item === "string") {
        return textFromUnknown(item);
      }
      const followup = recordFromUnknown(item);
      return (
        textFromUnknown(followup.summary)
        || textFromUnknown(followup.title)
        || textFromUnknown(followup.message)
        || textFromUnknown(followup.id)
      );
    })
    .filter(Boolean)
    .map((label) => `followup: ${label}`);
}

function sourceRefLabelsFromPackage(packageRecord: Record<string, unknown>) {
  return listFromUnknown(packageRecord.source_refs ?? packageRecord.sourceRefs)
    .map((item) => {
      const ref = recordFromUnknown(item);
      const kind = textFromUnknown(ref.source_kind ?? ref.kind);
      const id = textFromUnknown(ref.source_id ?? ref.id);
      if (isRunSourceKind(kind)) {
        return "";
      }
      return kind && id ? `source: ${kind}:${id}` : "";
    })
    .filter(Boolean);
}

function workerRunLinksFromPackage(packageRecord: Record<string, unknown>, workerRuns: unknown[]) {
  const links: DelegationWorkerRunLink[] = [];
  const addRun = (runId: string, label: string = "", status: string = "") => {
    const normalizedRunId = textFromUnknown(runId);
    if (!normalizedRunId || links.some((link) => link.runId === normalizedRunId)) {
      return;
    }
    links.push({
      runId: normalizedRunId,
      label: textFromUnknown(label) || normalizedRunId,
      href: `/runs/${encodeURIComponent(normalizedRunId)}`,
      status: textFromUnknown(status),
    });
  };
  addRun(
    textFromUnknown(
      packageRecord.worker_run_id
      ?? packageRecord.workerRunId
      ?? packageRecord.child_run_id
      ?? packageRecord.childRunId
      ?? packageRecord.triggered_run_id
      ?? packageRecord.triggeredRunId,
    ),
    "",
    textFromUnknown(
      packageRecord.worker_run_status
      ?? packageRecord.workerRunStatus
      ?? packageRecord.child_run_status
      ?? packageRecord.childRunStatus
      ?? packageRecord.triggered_run_status
      ?? packageRecord.triggeredRunStatus,
    ),
  );
  for (const item of listFromUnknown(packageRecord.source_refs ?? packageRecord.sourceRefs)) {
    const ref = recordFromUnknown(item);
    const kind = textFromUnknown(ref.source_kind ?? ref.kind);
    if (isRunSourceKind(kind)) {
      addRun(textFromUnknown(ref.source_id ?? ref.id), textFromUnknown(ref.label ?? ref.name), textFromUnknown(ref.status));
    }
  }
  for (const item of workerRuns) {
    const run = recordFromUnknown(item);
    addRun(
      textFromUnknown(run.run_id ?? run.runId),
      textFromUnknown(run.graph_name ?? run.graphName ?? run.name),
      textFromUnknown(run.status),
    );
  }
  return links;
}

function isRunSourceKind(kind: string) {
  return ["graph_run", "run", "worker_run", "child_run"].includes(kind);
}

function budgetLabelsFromPackage(packageRecord: Record<string, unknown>) {
  const budget = recordFromUnknown(packageRecord.budget);
  return Object.entries(budget)
    .map(([key, value]) => {
      const budgetKey = textFromUnknown(key);
      if (!budgetKey || value === undefined || value === null || value === "") {
        return "";
      }
      return `budget: ${budgetKey}=${formatValue(value)}`;
    })
    .filter(Boolean);
}

function capabilityLabelsFromPackage(packageRecord: Record<string, unknown>) {
  return listFromUnknown(packageRecord.allowed_capabilities ?? packageRecord.allowedCapabilities)
    .map((item) => {
      const capability = recordFromUnknown(item);
      const kind = textFromUnknown(capability.kind);
      const key = textFromUnknown(capability.key ?? capability.actionKey ?? capability.toolKey ?? capability.template_id);
      return kind && key ? `capability: ${kind}:${key}` : "";
    })
    .filter(Boolean);
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function listFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function textFromUnknown(value: unknown) {
  return typeof value === "string" ? value.trim() : value === null || value === undefined ? "" : String(value).trim();
}

function formatValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
