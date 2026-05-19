import type {
  BuddyOutputTraceRecord,
  BuddyOutputTraceRecordStatus,
  BuddyOutputTraceSegment,
  BuddyOutputTraceStatus,
} from "./buddyOutputTrace.ts";
import type { VirtualOperationGraphRevision } from "../lib/virtual-operation-activity.ts";
import type { RunDetail, RunTreeNode } from "../types/run.ts";

export type BuddyOutputTraceTreeRowKind = "root" | "subgraph" | "node" | "activity";

export type BuddyOutputTraceTreePlaybackTarget = {
  kind: "run" | "subgraph";
  nodeId: string | null;
};

export type BuddyOutputTraceTreeRow = {
  rowId: string;
  kind: BuddyOutputTraceTreeRowKind;
  label: string;
  depth: number;
  status: BuddyOutputTraceStatus | BuddyOutputTraceRecordStatus;
  startedAtMs: number | null;
  completedAtMs: number | null;
  durationMs: number | null;
  record: BuddyOutputTraceRecord | null;
  playbackTarget: BuddyOutputTraceTreePlaybackTarget | null;
  artifactLabels: string[];
  evidenceRunId: string | null;
  graphRevision: VirtualOperationGraphRevision | null;
};

export function buildBuddyOutputTraceTreeRows(
  segment: BuddyOutputTraceSegment,
  options: {
    rootLabel: string;
    runTree?: RunTreeNode | null;
    childRunDetailsByRunId?: Record<string, RunDetail | undefined>;
  },
): BuddyOutputTraceTreeRow[] {
  const subgraphLabelById = buildSubgraphLabelById(segment.records);
  const childRunIdByParentNodeId = buildChildRunIdByParentNodeId(options.runTree);
  const dynamicRunNodeByRunId = buildDynamicRunNodeByRunId(options.runTree);
  const dynamicRunIdsWithRecordedChildren = buildDynamicRunIdsWithRecordedChildren(segment.records);
  const rows: BuddyOutputTraceTreeRow[] = [];

  for (const record of segment.records) {
    const subgraphHeaderId = record.aggregateSubgraphNodeId?.trim();
    const isSubgraphHeader = Boolean(subgraphHeaderId);
    const dynamicRunNode = resolveDynamicRunNodeForRecord(record, dynamicRunNodeByRunId);
    const dynamicDepth = dynamicRunNode ? 1 : null;
    const depth = normalizeTreeDepth(record.treeDepth) ?? dynamicDepth ?? (isSubgraphHeader ? 0 : record.subgraphNodeId ? 1 : 0);
    const evidenceRunId = isSubgraphHeader
      ? childRunIdByParentNodeId[subgraphHeaderId || ""] ?? normalizeText(record.triggeredRunId)
      : normalizeText(record.triggeredRunId);
    rows.push({
      rowId: record.recordId,
      kind: resolveTreeRowKind(record, isSubgraphHeader, dynamicRunNode),
      label: resolveTreeRecordLabel(record, subgraphLabelById, options.childRunDetailsByRunId ?? {}, dynamicRunNode),
      depth,
      status: record.status,
      startedAtMs: record.startedAtMs,
      completedAtMs: record.completedAtMs,
      durationMs: record.durationMs,
      record,
      playbackTarget: null,
      artifactLabels: filterVisibleArtifactLabels(record.artifactLabels ?? []),
      evidenceRunId: evidenceRunId || null,
      graphRevision: record.graphRevision ?? null,
    });
    if (dynamicRunNode && evidenceRunId && !dynamicRunIdsWithRecordedChildren.has(evidenceRunId)) {
      rows.push(...buildDynamicRunDetailChildRows(record, options.childRunDetailsByRunId?.[evidenceRunId], depth + 1));
    }
  }

  return rows;
}

function filterVisibleArtifactLabels(labels: string[]) {
  return labels.filter((label) => !normalizeText(label).toLowerCase().startsWith("run:"));
}

function buildSubgraphLabelById(records: BuddyOutputTraceRecord[]) {
  const labelById: Record<string, string> = {};
  for (const record of records) {
    const subgraphId = record.aggregateSubgraphNodeId?.trim();
    if (subgraphId) {
      labelById[subgraphId] = record.label.trim();
    }
  }
  return labelById;
}

function resolveTreeRecordLabel(
  record: BuddyOutputTraceRecord,
  subgraphLabelById: Record<string, string>,
  childRunDetailsByRunId: Record<string, RunDetail | undefined>,
  dynamicRunNode: RunTreeNode | null = null,
) {
  if (dynamicRunNode && record.kind === "activity") {
    return normalizeText(dynamicRunNode.graph_name) || resolveLastPathPart(record.label.trim());
  }
  const dynamicRunId = normalizeText(record.dynamicCapabilityRunId);
  const dynamicNodeLabel = dynamicRunId && record.nodeId
    ? resolveRunDetailNodeLabel(childRunDetailsByRunId[dynamicRunId], record.nodeId)
    : "";
  if (dynamicNodeLabel) {
    return dynamicNodeLabel;
  }
  const label = record.label.trim();
  if (normalizeTreeDepth(record.treeDepth) !== null) {
    return resolveLastPathPart(label);
  }
  if (!record.subgraphNodeId) {
    return label;
  }
  const subgraphLabel = subgraphLabelById[record.subgraphNodeId]?.trim();
  if (!subgraphLabel) {
    return label;
  }
  const prefix = `${subgraphLabel} / `;
  return label.startsWith(prefix) ? label.slice(prefix.length).trim() || label : label;
}

function resolveTreeRowKind(
  record: BuddyOutputTraceRecord,
  isSubgraphHeader: boolean,
  dynamicRunNode: RunTreeNode | null = null,
): BuddyOutputTraceTreeRowKind {
  if (isSubgraphHeader) {
    return "subgraph";
  }
  if (
    record.kind === "activity" &&
    normalizeText(record.triggeredRunId) &&
    (normalizeTreeDepth(record.treeDepth) !== null || dynamicRunNode)
  ) {
    return "subgraph";
  }
  return record.kind === "activity" ? "activity" : "node";
}

function buildDynamicRunDetailChildRows(
  parentRecord: BuddyOutputTraceRecord,
  childRunDetail: RunDetail | null | undefined,
  depth: number,
): BuddyOutputTraceTreeRow[] {
  if (!childRunDetail) {
    return [];
  }
  return (childRunDetail.node_executions ?? []).flatMap((execution, index) => {
    const nodeId = normalizeText(execution.node_id);
    const nodeType = normalizeText(execution.node_type);
    if (!nodeId || nodeType === "input" || nodeType === "output") {
      return [];
    }
    const startedAtMs = parseEventEpochMs(execution.started_at);
    const completedAtMs = parseEventEpochMs(execution.finished_at);
    const durationMs = normalizeDurationMs(execution.duration_ms) ?? resolveDurationMs(startedAtMs, completedAtMs);
    return [{
      rowId: `${parentRecord.recordId}:child:${nodeId}:${index}`,
      kind: nodeType === "subgraph" ? "subgraph" as const : "node" as const,
      label: resolveRunDetailNodeLabel(childRunDetail, nodeId) || humanizeRuntimeKey(nodeId),
      depth,
      status: normalizeExecutionStatus(execution.status),
      startedAtMs,
      completedAtMs,
      durationMs,
      record: null,
      playbackTarget: null,
      artifactLabels: [],
      evidenceRunId: null,
      graphRevision: null,
    }];
  });
}

function buildDynamicRunIdsWithRecordedChildren(records: BuddyOutputTraceRecord[]) {
  const result = new Set<string>();
  for (const record of records) {
    const depth = normalizeTreeDepth(record.treeDepth);
    const runId = normalizeText(record.dynamicCapabilityRunId);
    if (runId && depth !== null && depth > 1) {
      result.add(runId);
    }
  }
  return result;
}

function normalizeTreeDepth(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.round(value) : null;
}

function resolveLastPathPart(label: string) {
  const parts = label.split("/").map((part) => part.trim()).filter(Boolean);
  return parts[parts.length - 1] || label;
}

function resolveRunDetailNodeLabel(runDetail: RunDetail | null | undefined, nodeId: string) {
  const graphSnapshot = runDetail?.graph_snapshot;
  const nodes = graphSnapshot && typeof graphSnapshot === "object"
    ? (graphSnapshot as { nodes?: Record<string, { name?: unknown; description?: unknown }> }).nodes
    : null;
  const node = nodes?.[nodeId];
  return normalizeText(node?.name) || normalizeText(node?.description);
}

function buildChildRunIdByParentNodeId(runTree: RunTreeNode | null | undefined) {
  const result: Record<string, string> = {};
  if (!runTree) {
    return result;
  }
  const stack = [...(runTree.children ?? [])];
  while (stack.length > 0) {
    const node = stack.shift();
    if (!node) {
      continue;
    }
    const parentNodeId = normalizeText(node.parent_node_id);
    const runId = normalizeText(node.run_id);
    if (parentNodeId && runId && !result[parentNodeId]) {
      result[parentNodeId] = runId;
    }
    stack.push(...(node.children ?? []));
  }
  return result;
}

function buildDynamicRunNodeByRunId(runTree: RunTreeNode | null | undefined) {
  const result: Record<string, RunTreeNode> = {};
  if (!runTree) {
    return result;
  }
  const stack = [...(runTree.children ?? [])];
  while (stack.length > 0) {
    const node = stack.shift();
    if (!node) {
      continue;
    }
    const runId = normalizeText(node.run_id);
    if (runId && normalizeText(node.invocation_kind) === "dynamic_subgraph_capability") {
      result[runId] = node;
    }
    stack.push(...(node.children ?? []));
  }
  return result;
}

function resolveDynamicRunNodeForRecord(
  record: BuddyOutputTraceRecord,
  dynamicRunNodeByRunId: Record<string, RunTreeNode>,
) {
  if (record.kind !== "activity") {
    return null;
  }
  const runId = normalizeText(record.triggeredRunId);
  const node = runId ? dynamicRunNodeByRunId[runId] ?? null : null;
  if (!node) {
    return null;
  }
  const parentNodeId = normalizeText(node.parent_node_id);
  return parentNodeId && parentNodeId === normalizeText(record.nodeId) ? node : null;
}

function parseEventEpochMs(value: unknown) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }
  const epochMs = Date.parse(value);
  return Number.isFinite(epochMs) ? epochMs : null;
}

function normalizeDurationMs(value: unknown) {
  const durationMs = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(durationMs) && durationMs >= 0 ? Math.round(durationMs) : null;
}

function resolveDurationMs(startedAtMs: number | null, completedAtMs: number | null) {
  return typeof startedAtMs === "number" && typeof completedAtMs === "number"
    ? Math.max(0, Math.round(completedAtMs - startedAtMs))
    : null;
}

function normalizeExecutionStatus(value: unknown): BuddyOutputTraceRecordStatus {
  const status = normalizeText(value).toLowerCase();
  return status === "failed" || status === "error" ? "failed" : "completed";
}

function normalizeText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function humanizeRuntimeKey(value: string) {
  return value
    .trim()
    .replace(/^state_/, "State ")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}
