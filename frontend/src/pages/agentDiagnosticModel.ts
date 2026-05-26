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
  const stateValues = {
    ...recordFromUnknown(run.state_snapshot?.values),
    ...recordFromUnknown(run.artifacts?.state_values),
  };
  const report = recordFromUnknown(stateValues.agent_loop_report);
  const explicitStateStopReason = normalizeStopReason(stateValues.agent_loop_stop_reason);
  const cycleSummary = run.cycle_summary ?? run.artifacts?.cycle_summary;
  const hasCycleSummary = Boolean(cycleSummary?.has_cycle);
  const stopReason =
    normalizeStopReason(run.stop_reason) ||
    normalizeStopReason(report.stop_reason) ||
    explicitStateStopReason ||
    (hasCycleSummary ? normalizeCycleStopReason(cycleSummary?.stop_reason) : "");
  const iterationIndex = numberFromUnknown(report.iteration_index) ?? (hasCycleSummary ? numberFromUnknown(cycleSummary?.iteration_count) : null);
  const maxIterations = numberFromUnknown(report.max_iterations) ?? (hasCycleSummary ? numberFromUnknown(cycleSummary?.max_iterations) : null);
  const capabilityCallCount = numberFromUnknown(report.capability_call_count);
  const maxCapabilityCalls = numberFromUnknown(report.max_capability_calls);
  const decision = textFromUnknown(report.decision);
  const selectedCapabilityRef = textFromUnknown(report.selected_capability_ref);
  const warnings = Array.isArray(report.warnings) ? report.warnings.map(textFromUnknown).filter(Boolean) : [];
  const hasLoopEvidence = Boolean(decision || iterationIndex !== null || capabilityCallCount !== null || warnings.length > 0);
  const hasNonDefaultStopReason = Boolean(stopReason && stopReason !== "completed");
  const badges = [
    stopReason ? `stop: ${stopReason}` : "",
    decision ? `decision: ${decision}` : "",
    selectedCapabilityRef ? `capability: ${selectedCapabilityRef}` : "",
  ].filter(Boolean);

  return {
    visible: hasLoopEvidence || hasNonDefaultStopReason,
    stopReason,
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
  return textFromUnknown(value);
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
