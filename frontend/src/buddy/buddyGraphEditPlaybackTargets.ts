import type { GraphEditPlaybackStep } from "../editor/workspace/graphEditPlaybackModel.ts";
import {
  BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_RETRY_MS,
  BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_WAIT_MS,
  resolveAliasedGraphEditPlaybackStep,
  resolveAliasedGraphEditPlaybackTarget,
  type GraphEditPlaybackUiState,
} from "./buddyGraphEditPlaybackBridge.ts";
import type { PageOperationRetryRecord } from "./pageOperationResume.ts";

type GraphEditPlaybackAffordance = {
  element: HTMLElement;
};

type GraphEditPlaybackStepElementResolver<TToken> = {
  step: GraphEditPlaybackStep;
  playbackState: GraphEditPlaybackUiState;
  token: TToken | null;
  resolveAffordance: (targetId: string) => GraphEditPlaybackAffordance | null;
  isInterrupted: (token: TToken | null) => boolean;
  waitForRetry: (timeoutMs: number) => Promise<void>;
  recordRetry: (token: TToken | null, record: PageOperationRetryRecord) => void;
};

export async function resolveGraphEditPlaybackStepElementWithRetry<TToken>({
  step,
  playbackState,
  token,
  resolveAffordance,
  isInterrupted,
  waitForRetry,
  recordRetry,
}: GraphEditPlaybackStepElementResolver<TToken>) {
  const startedAt = Date.now();
  const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
  const deadlineMs = Date.now() + BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_WAIT_MS;
  let attempts = 0;
  while (!isInterrupted(token) && Date.now() <= deadlineMs) {
    attempts += 1;
    const targetElement = resolveGraphEditPlaybackStepElement(step, playbackState, resolveAffordance);
    if (targetElement) {
      recordRetry(token, buildGraphEditPlaybackRetryRecord("graph_edit_step", targetId, attempts, "resolved", startedAt));
      return targetElement;
    }
    await waitForRetry(BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_RETRY_MS);
  }
  const targetElement = resolveGraphEditPlaybackStepElement(step, playbackState, resolveAffordance);
  recordRetry(
    token,
    buildGraphEditPlaybackRetryRecord(
      "graph_edit_step",
      targetId,
      attempts,
      isInterrupted(token) ? "interrupted" : targetElement ? "resolved" : "missing",
      startedAt,
    ),
  );
  if (isInterrupted(token)) {
    return null;
  }
  return targetElement;
}

function resolveGraphEditPlaybackStepElement(
  step: GraphEditPlaybackStep,
  playbackState: GraphEditPlaybackUiState,
  resolveAffordance: (targetId: string) => GraphEditPlaybackAffordance | null,
): HTMLElement | null {
  const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
  const exactAffordance = resolveAffordance(targetId);
  if (exactAffordance) {
    return exactAffordance.element;
  }
  if (targetId.startsWith("editor.canvas.")) {
    return resolveAffordance(targetId)?.element ?? resolveGraphEditPlaybackStepFallbackElement(step, playbackState, resolveAffordance);
  }
  const nodeId = resolveGraphEditPlaybackTargetNodeId(targetId);
  if (nodeId) {
    return resolveAffordance(`editor.canvas.node.${nodeId}`)?.element ?? null;
  }
  return resolveGraphEditPlaybackStepFallbackElement(step, playbackState, resolveAffordance);
}

function resolveGraphEditPlaybackStepFallbackElement(
  step: GraphEditPlaybackStep,
  playbackState: GraphEditPlaybackUiState,
  resolveAffordance: (targetId: string) => GraphEditPlaybackAffordance | null,
): HTMLElement | null {
  const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
  if (targetId === "editor.canvas.empty.createFirstNode") {
    return resolveAffordance("editor.canvas.surface")?.element ?? null;
  }
  if ((step.kind === "move_virtual_cursor" || step.kind === "open_node_creation_menu") && targetId === "editor.canvas.surface") {
    return resolveAffordance("editor.canvas.surface")?.element ?? null;
  }
  return null;
}

function resolveGraphEditPlaybackTargetNodeId(targetId: string): string {
  return targetId.match(/^editor\.canvas\.node\.([^.]+)/)?.[1] ?? "";
}

export function shouldSkipGraphEditPlaybackConnectionStep(
  step: GraphEditPlaybackStep,
  playbackState: GraphEditPlaybackUiState,
  hasAffordanceElement: (targetId: string) => boolean,
) {
  const edgeTargetId =
    step.kind === "drag_state_edge_to_node"
      ? resolveGraphEditPlaybackDataEdgeTarget(step, playbackState)
      : step.kind === "draw_flow_edge"
        ? resolveGraphEditPlaybackFlowEdgeTarget(step, playbackState)
        : "";
  return Boolean(edgeTargetId && hasAffordanceElement(edgeTargetId));
}

function resolveGraphEditPlaybackDataEdgeTarget(step: GraphEditPlaybackStep, playbackState: GraphEditPlaybackUiState) {
  const resolvedStep = resolveAliasedGraphEditPlaybackStep(step, playbackState);
  if (resolvedStep.kind !== "drag_state_edge_to_node" || !resolvedStep.sourceNodeId || !resolvedStep.nodeId) {
    return "";
  }
  const stateKey = resolvedStep.sourceStateKey || resolvedStep.stateKey || "";
  if (!stateKey) {
    return "";
  }
  return `editor.canvas.edge.data:${resolvedStep.sourceNodeId}:${stateKey}->${resolvedStep.nodeId}`;
}

function resolveGraphEditPlaybackFlowEdgeTarget(step: GraphEditPlaybackStep, playbackState: GraphEditPlaybackUiState) {
  const resolvedStep = resolveAliasedGraphEditPlaybackStep(step, playbackState);
  if (resolvedStep.kind !== "draw_flow_edge" || !resolvedStep.sourceNodeId || !resolvedStep.nodeId) {
    return "";
  }
  return `editor.canvas.edge.flow:${resolvedStep.sourceNodeId}->${resolvedStep.nodeId}`;
}

function buildGraphEditPlaybackRetryRecord(
  kind: "graph_edit_step",
  targetId: string,
  attempts: number,
  status: PageOperationRetryRecord["status"],
  startedAt: number,
): PageOperationRetryRecord {
  return {
    kind,
    target_id: targetId,
    attempts: Math.max(1, attempts),
    status,
    elapsed_ms: Math.max(0, Date.now() - startedAt),
  };
}
