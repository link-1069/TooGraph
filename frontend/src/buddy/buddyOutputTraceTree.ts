import type {
  BuddyOutputTraceRecord,
  BuddyOutputTraceRecordStatus,
  BuddyOutputTraceSegment,
  BuddyOutputTraceStatus,
} from "./buddyOutputTrace.ts";
import type { VirtualOperationGraphRevision } from "../lib/virtual-operation-activity.ts";
import type { RunTreeNode } from "../types/run.ts";

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
  options: { rootLabel: string; runTree?: RunTreeNode | null },
): BuddyOutputTraceTreeRow[] {
  const subgraphLabelById = buildSubgraphLabelById(segment.records);
  const childRunIdByParentNodeId = buildChildRunIdByParentNodeId(options.runTree);
  const rows: BuddyOutputTraceTreeRow[] = [];

  for (const record of segment.records) {
    const subgraphHeaderId = record.aggregateSubgraphNodeId?.trim();
    const isSubgraphHeader = Boolean(subgraphHeaderId);
    const depth = isSubgraphHeader ? 0 : record.subgraphNodeId ? 1 : 0;
    const evidenceRunId = isSubgraphHeader
      ? childRunIdByParentNodeId[subgraphHeaderId || ""] ?? normalizeText(record.triggeredRunId)
      : normalizeText(record.triggeredRunId);
    rows.push({
      rowId: record.recordId,
      kind: isSubgraphHeader ? "subgraph" : record.kind === "activity" ? "activity" : "node",
      label: resolveTreeRecordLabel(record, subgraphLabelById),
      depth,
      status: record.status,
      startedAtMs: record.startedAtMs,
      completedAtMs: record.completedAtMs,
      durationMs: record.durationMs,
      record,
      playbackTarget: null,
      artifactLabels: record.artifactLabels ?? [],
      evidenceRunId: evidenceRunId || null,
      graphRevision: record.graphRevision ?? null,
    });
  }

  return rows;
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

function resolveTreeRecordLabel(record: BuddyOutputTraceRecord, subgraphLabelById: Record<string, string>) {
  const label = record.label.trim();
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

function normalizeText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}
