import type { ActivityEvent, NodeExecutionDetail, RunDetail, RunTreeNode } from "../types/run.ts";

import { collectLocalArtifactReferences, type LocalArtifactReference } from "../lib/localArtifactReferences.ts";
import { formatRunDuration } from "../lib/run-display-name.ts";
import { summarizeVirtualOperationActivity } from "../lib/virtual-operation-activity.ts";
import { translate } from "../i18n/index.ts";

export type RunOutputArtifactCard = {
  key: string;
  title: string;
  text: string;
  displayMode: string;
  persistLabel: string;
  fileName: string | null;
  documentRefs: ArtifactDocumentReference[];
};

export type ArtifactDocumentReference = LocalArtifactReference;

export type RunStatusFact = {
  key: string;
  label: string;
  value: string;
  tone: "default" | "status";
};

export type RunAggregatedTimelineKind = "node" | "activity" | "permission";

export type RunAggregatedTimelineItem = {
  key: string;
  kind: RunAggregatedTimelineKind;
  label: string;
  summary: string;
  status: string;
  durationMs: number | null;
  artifactLabels: string[];
  nodeId: string | null;
  subgraphNodeId: string | null;
  subgraphPath: string[];
  pathLabel: string;
  timeValue: number;
  sequence: number;
  detailText: string;
};

export type RunTreeDisplayRunRow = {
  kind: "run";
  key: string;
  runId: string;
  graphName: string;
  status: string;
  depth: number;
  href: string;
  relation: string;
  currentNodeId: string | null;
  durationLabel: string;
  labels: string[];
};

export type RunTreeDisplayBatchGroup = {
  kind: "batch_group";
  key: string;
  label: string;
  depth: number;
  count: number;
  statusSummary: string;
  rows: RunTreeDisplayRunRow[];
};

export type RunTreeDisplayItem = RunTreeDisplayRunRow | RunTreeDisplayBatchGroup;

export function formatRunArtifactValue(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  const operationReport = formatOperationReportValue(value);
  if (operationReport) {
    return operationReport;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatOperationReportValue(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return "";
  }
  const report = value as Record<string, unknown>;
  const requestId = normalizeText(report.operation_request_id);
  const status = normalizeText(report.status);
  if (!requestId || !status) {
    return "";
  }
  const targetId = normalizeText(report.target_id);
  const routeBefore = normalizeText(report.route_before);
  const routeAfter = normalizeText(report.route_after);
  const triggeredRunId = normalizeText(report.triggered_run_id);
  const triggeredRunStatus = normalizeText(report.triggered_run_status);
  return [
    status,
    targetId,
    routeBefore || routeAfter ? `${routeBefore || "?"} -> ${routeAfter || "?"}` : "",
    triggeredRunId ? `run ${triggeredRunId}${triggeredRunStatus ? ` ${triggeredRunStatus}` : ""}` : "",
  ].filter(Boolean).join(" · ");
}

export function listRunOutputArtifacts(run: RunDetail): RunOutputArtifactCard[] {
  return (run.artifacts.exported_outputs ?? []).map((output, index) => ({
    key: `${output.node_id ?? "output"}-${output.source_key}-${index}`,
    title: output.label?.trim() || output.source_key || "Output",
    text: formatRunArtifactValue(output.value),
    displayMode: output.display_mode?.trim() || "auto",
    persistLabel: output.persist_enabled ? `persist ${output.persist_format ?? "txt"}` : "preview only",
    fileName: output.saved_file?.file_name ?? null,
    documentRefs: normalizeArtifactDocumentReferences(output.value),
  }));
}

export function normalizeArtifactDocumentReferences(value: unknown): ArtifactDocumentReference[] {
  return collectLocalArtifactReferences(value);
}

function normalizeText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function buildRunStatusFacts(run: RunDetail): RunStatusFact[] {
  return [
    { key: "status", label: translate("runDetail.status"), value: run.status, tone: "status" },
    { key: "current", label: translate("runDetail.currentNode"), value: run.current_node_id?.trim() || translate("runDetail.ended"), tone: "default" },
    { key: "duration", label: translate("runDetail.duration"), value: formatRunDuration(run.duration_ms), tone: "default" },
    { key: "revision", label: translate("runDetail.revision"), value: String(run.revision_round), tone: "default" },
  ];
}

export function buildRunTreeDisplayItems(tree: RunTreeNode | null | undefined): RunTreeDisplayItem[] {
  if (!tree) {
    return [];
  }
  return buildRunTreeItemsForNode(tree, 0);
}

export function countRunTreeNodes(tree: RunTreeNode | null | undefined): number {
  if (!tree) {
    return 0;
  }
  return 1 + (tree.children ?? []).reduce((total, child) => total + countRunTreeNodes(child), 0);
}

type RunAggregatedTimelineDraft = RunAggregatedTimelineItem & {
  order: number;
};

function buildRunTreeItemsForNode(node: RunTreeNode, depth: number): RunTreeDisplayItem[] {
  const items: RunTreeDisplayItem[] = [buildRunTreeRow(node, depth)];
  const children = Array.isArray(node.children) ? node.children : [];
  const emittedBatchGroups = new Set<string>();

  for (const child of children) {
    const batchGroupId = normalizeText(child.batch_group_id);
    if (!batchGroupId) {
      items.push(...buildRunTreeItemsForNode(child, depth + 1));
      continue;
    }
    if (emittedBatchGroups.has(batchGroupId)) {
      continue;
    }
    emittedBatchGroups.add(batchGroupId);
    const groupChildren = children.filter((candidate) => normalizeText(candidate.batch_group_id) === batchGroupId);
    items.push(buildRunTreeBatchGroup(node, batchGroupId, groupChildren, depth + 1));
  }
  return items;
}

function buildRunTreeBatchGroup(
  parent: RunTreeNode,
  batchGroupId: string,
  children: RunTreeNode[],
  depth: number,
): RunTreeDisplayBatchGroup {
  const rows = children.flatMap((child) => flattenRunTreeRunRows(child, depth + 1));
  return {
    kind: "batch_group",
    key: `batch:${parent.run_id}:${batchGroupId}`,
    label: `Batch ${batchGroupId}`,
    depth,
    count: children.length,
    statusSummary: buildRunTreeStatusSummary(rows),
    rows,
  };
}

function flattenRunTreeRunRows(node: RunTreeNode, depth: number): RunTreeDisplayRunRow[] {
  return [
    buildRunTreeRow(node, depth),
    ...(node.children ?? []).flatMap((child) => flattenRunTreeRunRows(child, depth + 1)),
  ];
}

function buildRunTreeRow(node: RunTreeNode, depth: number): RunTreeDisplayRunRow {
  const runId = normalizeText(node.run_id);
  const invocationKind = normalizeText(node.invocation_kind);
  const invocationKey = normalizeText(node.invocation_key);
  const parentNodeId = normalizeText(node.parent_node_id);
  const batchItemIndex = typeof node.batch_item_index === "number" ? node.batch_item_index : null;
  const batchItemLabel = normalizeText(node.batch_item_label);
  return {
    kind: "run",
    key: `run:${runId}`,
    runId,
    graphName: normalizeText(node.graph_name) || runId || "Run",
    status: normalizeText(node.status) || "unknown",
    depth: Math.max(0, depth),
    href: `/runs/${encodeURIComponent(runId)}`,
    relation: buildRunTreeRelationLabel(invocationKind, invocationKey, parentNodeId),
    currentNodeId: normalizeText(node.current_node_id) || null,
    durationLabel: formatRunDuration(node.duration_ms),
    labels: [
      parentNodeId ? `node: ${parentNodeId}` : "",
      invocationKind ? `kind: ${invocationKind}` : "",
      invocationKey ? `capability: ${invocationKey}` : "",
      batchItemIndex !== null ? `item: ${batchItemIndex + 1}` : "",
      batchItemLabel ? `case: ${batchItemLabel}` : "",
    ].filter(Boolean),
  };
}

function buildRunTreeRelationLabel(invocationKind: string, invocationKey: string, parentNodeId: string) {
  if (!invocationKind && !invocationKey && !parentNodeId) {
    return "root";
  }
  return [
    invocationKind || "child",
    invocationKey,
    parentNodeId ? `from ${parentNodeId}` : "",
  ].filter(Boolean).join(" · ");
}

function buildRunTreeStatusSummary(rows: RunTreeDisplayRunRow[]) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
  }
  return [...counts.entries()].map(([status, count]) => `${status} ${count}`).join(" / ");
}

export function buildRunAggregatedTimeline(run: RunDetail): RunAggregatedTimelineItem[] {
  const items: RunAggregatedTimelineDraft[] = [];
  let order = 0;
  for (const execution of run.node_executions ?? []) {
    appendNodeExecutionTimelineItems(items, execution, [], null, () => {
      order += 1;
      return order;
    });
  }
  for (const [index, event] of (run.artifacts.activity_events ?? []).entries()) {
    const nextOrder = order + 1;
    order = nextOrder;
    items.push(buildActivityTimelineItem(event, index, nextOrder));
  }
  for (const permissionItem of buildPermissionTimelineItems(run)) {
    order += 1;
    items.push({ ...permissionItem, order });
  }
  return items
    .sort((left, right) => {
      if (left.timeValue !== right.timeValue) {
        return left.timeValue - right.timeValue;
      }
      if (left.sequence !== right.sequence) {
        return left.sequence - right.sequence;
      }
      return left.order - right.order;
    })
    .map(({ order: _order, ...item }) => item);
}

function appendNodeExecutionTimelineItems(
  items: RunAggregatedTimelineDraft[],
  execution: NodeExecutionDetail,
  subgraphPath: string[],
  subgraphNodeId: string | null,
  nextOrder: () => number,
) {
  const nodeId = normalizeText(execution.node_id) || null;
  const order = nextOrder();
  const normalizedPath = normalizeTimelinePath(subgraphPath);
  const label = nodeId || "node";
  items.push({
    key: `node:${normalizedPath.join("/")}:${label}:${order}`,
    kind: "node",
    label,
    summary: normalizeText(execution.output_summary) || normalizeText(execution.input_summary),
    status: normalizeText(execution.status) || "unknown",
    durationMs: normalizeNumber(execution.duration_ms),
    artifactLabels: buildNodeArtifactLabels(execution),
    nodeId,
    subgraphNodeId,
    subgraphPath: normalizedPath,
    pathLabel: buildTimelinePathLabel(normalizedPath, nodeId),
    timeValue: parseTimelineTimestamp(execution.started_at ?? execution.finished_at),
    sequence: order,
    detailText: buildNodeExecutionDetailText(execution),
    order,
  });

  const childExecutions = execution.artifacts.subgraph?.node_executions;
  if (!Array.isArray(childExecutions)) {
    return;
  }
  const childPath = nodeId ? [...normalizedPath, nodeId] : normalizedPath;
  for (const childExecution of childExecutions) {
    appendNodeExecutionTimelineItems(items, childExecution, childPath, nodeId, nextOrder);
  }
}

function buildActivityTimelineItem(event: ActivityEvent, index: number, order: number): RunAggregatedTimelineDraft {
  const nodeId = normalizeText(event.node_id) || null;
  const subgraphPath = normalizeTimelinePath(event.subgraph_path);
  const subgraphNodeId = normalizeText(event.subgraph_node_id) || subgraphPath.at(-1) || null;
  const label = buildActivityLabel(event);
  const virtualOperation = summarizeVirtualOperationActivity(event);
  return {
    key: `activity:${event.sequence ?? index + 1}:${subgraphPath.join("/")}:${nodeId ?? label}`,
    kind: "activity",
    label,
    summary: virtualOperation?.summary || normalizeText(event.summary) || label,
    status: normalizeText(event.status) || (normalizeText(event.error) ? "failed" : "recorded"),
    durationMs: normalizeNumber(event.duration_ms),
    artifactLabels: buildActivityArtifactLabels(event),
    nodeId,
    subgraphNodeId,
    subgraphPath,
    pathLabel: buildTimelinePathLabel(subgraphPath, nodeId),
    timeValue: parseTimelineTimestamp(event.created_at),
    sequence: normalizeSequence(event.sequence, index + 1),
    detailText: buildActivityDetailText(event),
    order,
  };
}

function buildActivityLabel(event: ActivityEvent) {
  const virtualOperation = summarizeVirtualOperationActivity(event);
  if (virtualOperation) {
    return virtualOperation.label;
  }
  const kind = normalizeText(event.kind);
  if (kind === "buddy_home_write") {
    return "Buddy Home writeback";
  }
  if (kind === "buddy_session_recall") {
    return "Buddy session recall";
  }
  return kind || "activity";
}

function buildPermissionTimelineItems(run: RunDetail): RunAggregatedTimelineItem[] {
  const metadata = recordFromUnknown(run.metadata);
  const items: RunAggregatedTimelineItem[] = [];
  const topLevelApproval = recordFromUnknown(metadata.pending_permission_approval);
  const topLevelNodeId = normalizeText(run.current_node_id) || null;
  const topLevelItem = buildPermissionTimelineItem(run, topLevelApproval, [], null, topLevelNodeId);
  if (topLevelItem) {
    items.push(topLevelItem);
  }

  const pendingSubgraph = recordFromUnknown(metadata.pending_subgraph_breakpoint);
  const pendingSubgraphMetadata = recordFromUnknown(pendingSubgraph.metadata);
  const subgraphApproval = recordFromUnknown(pendingSubgraphMetadata.pending_permission_approval);
  const subgraphPath = normalizeTimelinePath(pendingSubgraph.subgraph_path);
  const subgraphNodeId = normalizeText(pendingSubgraph.subgraph_node_id) || subgraphPath.at(-1) || null;
  const subgraphItem = buildPermissionTimelineItem(
    run,
    subgraphApproval,
    subgraphPath.length > 0 ? subgraphPath : subgraphNodeId ? [subgraphNodeId] : [],
    subgraphNodeId,
    normalizeText(pendingSubgraph.inner_node_id) || null,
  );
  if (subgraphItem) {
    items.push(subgraphItem);
  }
  return items;
}

function buildPermissionTimelineItem(
  run: RunDetail,
  approval: Record<string, unknown>,
  subgraphPath: string[],
  subgraphNodeId: string | null,
  nodeId: string | null,
): RunAggregatedTimelineItem | null {
  const capabilityKey = normalizeText(approval.capability_key);
  const capabilityName = normalizeText(approval.capability_name) || capabilityKey;
  const permissions = Array.isArray(approval.permissions)
    ? approval.permissions.map((permission) => normalizeText(permission)).filter(Boolean)
    : [];
  if (!capabilityKey && permissions.length === 0) {
    return null;
  }
  const label = capabilityName || "Permission approval";
  return {
    key: `permission:${subgraphPath.join("/")}:${nodeId ?? ""}:${capabilityKey || label}`,
    kind: "permission",
    label,
    summary: permissions.length > 0 ? `Requires permission: ${permissions.join(", ")}` : "Requires permission approval.",
    status: "awaiting_human",
    durationMs: null,
    artifactLabels: permissions,
    nodeId,
    subgraphNodeId,
    subgraphPath,
    pathLabel: buildTimelinePathLabel(subgraphPath, nodeId),
    timeValue: parseTimelineTimestamp(
      normalizeText(approval.created_at) || normalizeText(run.lifecycle.paused_at) || normalizeText(run.lifecycle.updated_at) || run.started_at,
    ),
    sequence: Number.MAX_SAFE_INTEGER,
    detailText: formatRunArtifactValue(approval),
  };
}

function buildNodeArtifactLabels(execution: NodeExecutionDetail) {
  const labels: string[] = [];
  const outputKeys = uniqueNonEmpty(Object.keys(recordFromUnknown(execution.artifacts.outputs)));
  if (outputKeys.length > 0) {
    labels.push(`outputs: ${outputKeys.join(", ")}`);
  }
  const writtenStateKeys = uniqueNonEmpty((execution.artifacts.state_writes ?? []).map((write) => normalizeText(write.state_key)));
  if (writtenStateKeys.length > 0) {
    labels.push(`writes: ${writtenStateKeys.join(", ")}`);
  }
  const subgraphName = normalizeText(execution.artifacts.subgraph?.name);
  if (subgraphName) {
    labels.push(`subgraph: ${subgraphName}`);
  }
  const selectedBranch = normalizeText(execution.artifacts.selected_branch);
  if (selectedBranch) {
    labels.push(`branch: ${selectedBranch}`);
  }
  const iteration = normalizeNumber(execution.artifacts.iteration);
  if (iteration !== null) {
    labels.push(`iteration: ${iteration}`);
  }
  return labels;
}

function buildActivityArtifactLabels(event: ActivityEvent) {
  const detail = recordFromUnknown(event.detail);
  const labels: string[] = [];
  const virtualOperation = summarizeVirtualOperationActivity(event);
  if (virtualOperation) {
    return virtualOperation.artifactLabels;
  }
  if (normalizeText(event.kind) === "buddy_home_write") {
    const appliedCount = normalizeNumber(detail.applied_count);
    const skippedCount = normalizeNumber(detail.skipped_count);
    const revisionIds = Array.isArray(detail.revision_ids)
      ? uniqueNonEmpty(detail.revision_ids.map((revisionId) => normalizeText(revisionId)))
      : [];
    if (appliedCount !== null) {
      labels.push(`applied: ${appliedCount}`);
    }
    if (skippedCount !== null) {
      labels.push(`skipped: ${skippedCount}`);
    }
    if (revisionIds.length > 0) {
      labels.push(`revisions: ${revisionIds.join(", ")}`);
    }
    return labels;
  }
  if (normalizeText(event.kind) === "buddy_session_recall") {
    const sessionCount = normalizeNumber(detail.session_count);
    const hitCount = normalizeNumber(detail.hit_count);
    const mode = normalizeText(detail.mode);
    if (mode) {
      labels.push(`mode: ${mode}`);
    }
    if (sessionCount !== null) {
      labels.push(`sessions: ${sessionCount}`);
    }
    if (hitCount !== null) {
      labels.push(`hits: ${hitCount}`);
    }
    const query = normalizeText(detail.query);
    if (query) {
      labels.push(`query: ${query}`);
    }
    return labels;
  }
  const actionKey = normalizeText(detail.action_key);
  if (actionKey) {
    labels.push(`action: ${actionKey}`);
  }
  const toolKey = normalizeText(detail.tool_key);
  if (toolKey) {
    labels.push(`tool: ${toolKey}`);
  }
  const path = normalizeText(detail.path);
  if (path) {
    labels.push(`path: ${path}`);
  }
  const query = normalizeText(detail.query);
  if (query) {
    labels.push(`query: ${query}`);
  }
  return labels;
}

function buildNodeExecutionDetailText(execution: NodeExecutionDetail) {
  const detail = {
    inputs: execution.artifacts.inputs,
    outputs: execution.artifacts.outputs,
    warnings: execution.warnings,
    errors: execution.errors,
  };
  return formatRunArtifactValue(detail);
}

function buildActivityDetailText(event: ActivityEvent) {
  const detail = event.detail ?? (event.error ? { error: event.error } : null);
  return formatRunArtifactValue(detail);
}

function buildTimelinePathLabel(subgraphPath: string[], nodeId: string | null) {
  const parts = [...normalizeTimelinePath(subgraphPath), normalizeText(nodeId)].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "Run";
}

function normalizeTimelinePath(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => normalizeText(item)).filter(Boolean);
}

function parseTimelineTimestamp(value: unknown) {
  const timestamp = Date.parse(normalizeText(value));
  return Number.isFinite(timestamp) ? timestamp : Number.MAX_SAFE_INTEGER;
}

function normalizeSequence(value: unknown, fallback: number) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function uniqueNonEmpty(values: string[]) {
  return [...new Set(values.map((value) => normalizeText(value)).filter(Boolean))];
}
