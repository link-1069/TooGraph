import type { Ref } from "vue";

import type { GraphEditPlaybackStep } from "../editor/workspace/graphEditPlaybackModel.ts";
import type { BuddyVirtualOperation } from "../stores/buddyMascotDebug.ts";
import type { BuddyPosition } from "./buddyPosition.ts";
import {
  BUDDY_GRAPH_EDIT_PLAYBACK_VIEWPORT_SETTLE_MS,
  BUDDY_GRAPH_EDIT_PLAYBACK_VISIBLE_MARGIN_PX,
  createGraphEditPlaybackUiState,
  dispatchGraphEditPlaybackApplyCommand,
  requestGraphEditPlaybackEnsureVisible,
  requestGraphEditPlaybackPlan,
  requestGraphEditPlaybackSave,
  resolveAliasedGraphEditPlaybackStep,
  resolveAliasedGraphEditPlaybackTarget,
  setGraphEditPlaybackRunning,
  type GraphEditPlaybackUiState,
} from "./buddyGraphEditPlaybackBridge.ts";
import {
  resolveGraphEditPlaybackStepElementWithRetry,
  shouldSkipGraphEditPlaybackConnectionStep,
} from "./buddyGraphEditPlaybackTargets.ts";
import {
  buildVirtualDragPoints,
  isGraphEditPlaybackDragStep,
  listGraphEditPlaybackNodeAffordanceIds,
  listGraphEditPlaybackPortStateKeys,
  normalizeVirtualText,
  resolveGraphEditPlaybackAnchorNodeId,
  resolveGraphEditPlaybackPositionClientPoint,
  resolveGraphEditPlaybackStepDelayMs,
  shouldForceGraphEditPlaybackEmptyCanvasDrop,
} from "./buddyGraphEditPlaybackUi.ts";
import {
  hasVirtualOperationAffordanceElement,
  resolveVirtualOperationAffordance,
  resolveVirtualOperationTextInput,
} from "./buddyVirtualOperationTargets.ts";
import {
  dispatchVirtualClick,
  dispatchVirtualDoubleClick,
  dispatchVirtualPointerEvent,
  dispatchVirtualPointerTap,
} from "./buddyVirtualPointerEvents.ts";
import {
  buildGraphEditPlaybackAuditSummary,
  type GraphEditPlaybackAuditApplyResult,
  type GraphEditPlaybackAuditSummary,
} from "./graphEditPlaybackAudit.ts";
import type { PageOperationRetryRecord } from "./pageOperationResume.ts";
import type { BuddyVirtualOperationToken } from "./useBuddyVirtualOperationLifecycle.ts";
import type { BuddyVirtualOperationPlan } from "./virtualOperationProtocol.ts";

const BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS = 80;

type BuddyGraphEditPlaybackExecutorOptions = {
  activeVirtualOperationToken: Ref<BuddyVirtualOperationToken | null>;
  virtualCursorDragging: Ref<boolean>;
  isVirtualOperationInterrupted: (token: BuddyVirtualOperationToken | null) => boolean;
  waitForVirtualOperation: (timeoutMs: number, token?: BuddyVirtualOperationToken | null) => Promise<void>;
  recordVirtualOperationRetry: (token: BuddyVirtualOperationToken | null, record: PageOperationRetryRecord) => void;
  moveVirtualCursorToElement: (element: HTMLElement) => Promise<void>;
  moveVirtualCursorToClientPoint: (point: BuddyPosition, options?: { durationMs?: number }) => number;
  replaceVirtualText: (element: HTMLInputElement | HTMLTextAreaElement, text: string) => Promise<void>;
};

export function useBuddyGraphEditPlaybackExecutor({
  activeVirtualOperationToken,
  virtualCursorDragging,
  isVirtualOperationInterrupted,
  waitForVirtualOperation,
  recordVirtualOperationRetry,
  moveVirtualCursorToElement,
  moveVirtualCursorToClientPoint,
  replaceVirtualText,
}: BuddyGraphEditPlaybackExecutorOptions) {
  async function executeBuddyVirtualGraphEditOperation(
    operationPlan: BuddyVirtualOperationPlan,
    operation: BuddyVirtualOperation,
  ): Promise<GraphEditPlaybackAuditSummary> {
    if (operation.kind !== "graph_edit") {
      return buildGraphEditPlaybackAuditSummary({
        requestId: "",
        planOk: false,
        planIssues: ["Operation is not a graph_edit request."],
        commandCount: 0,
        playbackStepCount: 0,
        interrupted: false,
        applyResults: [],
      });
    }
    const token = activeVirtualOperationToken.value;
    const affordance = resolveVirtualOperationAffordance(operation.targetId);
    if (affordance) {
      await moveVirtualCursorToElement(affordance.element);
      if (isVirtualOperationInterrupted(token)) {
        return buildGraphEditPlaybackAuditSummary({
          requestId: "",
          planOk: true,
          planIssues: [],
          commandCount: 0,
          playbackStepCount: 0,
          interrupted: true,
          applyResults: [],
        });
      }
    }
    const requestId = `graph-edit-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    const response = requestGraphEditPlaybackPlan({
      requestId,
      graphEditIntents: operation.graphEditIntents,
    });
    if (!response?.ok) {
      return buildGraphEditPlaybackAuditSummary({
        requestId,
        planOk: false,
        planIssues: response?.issues.length ? response.issues : ["Graph edit playback plan request failed."],
        commandCount: response?.graphCommands.length ?? 0,
        playbackStepCount: response?.playbackSteps.length ?? 0,
        interrupted: false,
        applyResults: [],
      });
    }
    setGraphEditPlaybackRunning(true);
    const playbackState = createGraphEditPlaybackUiState();
    const applyResults: GraphEditPlaybackAuditApplyResult[] = [];
    try {
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
      if (isVirtualOperationInterrupted(token)) {
        return buildGraphEditPlaybackAuditSummary({
          requestId,
          planOk: true,
          planIssues: response.issues,
          commandCount: response.graphCommands.length,
          playbackStepCount: response.playbackSteps.length,
          interrupted: true,
          applyResults,
        });
      }
      for (let stepIndex = 0; stepIndex < response.playbackSteps.length; stepIndex += 1) {
        if (isVirtualOperationInterrupted(token)) {
          break;
        }
        const step = response.playbackSteps[stepIndex]!;
        await ensureGraphEditPlaybackStepVisible(step, playbackState);
        const targetElement = await resolveGraphEditPlaybackStepElementWithRetry({
          step,
          playbackState,
          token,
          resolveAffordance: resolveVirtualOperationAffordance,
          isInterrupted: isVirtualOperationInterrupted,
          waitForRetry: (timeoutMs) => waitForVirtualOperation(timeoutMs),
          recordRetry: recordVirtualOperationRetry,
        });
        if (isVirtualOperationInterrupted(token)) {
          break;
        }
        if (shouldSkipGraphEditPlaybackTextStep(step, response.playbackSteps, stepIndex, playbackState, targetElement)) {
          continue;
        }
        if (shouldSkipGraphEditPlaybackConnectionStep(step, playbackState, hasVirtualOperationAffordanceElement)) {
          continue;
        }
        if (isGraphEditPlaybackDragStep(step)) {
          await executeGraphEditPlaybackDragStep(step, targetElement, playbackState);
        } else if (targetElement) {
          await moveVirtualCursorToGraphEditStep(step, targetElement);
        }
        if (isVirtualOperationInterrupted(token)) {
          break;
        }
        if (step.kind === "open_node_creation_menu") {
          if (!step.sourceAnchorKind && targetElement) {
            dispatchVirtualDoubleClick(targetElement, resolveGraphEditPlaybackPositionClientPoint(
              step,
              resolveVirtualOperationAffordance("editor.canvas.surface")?.element ?? null,
            ));
          }
        } else if (step.kind === "choose_node_type" && targetElement) {
          const beforeNodeIds = listGraphEditPlaybackNodeAffordanceIds();
          dispatchVirtualClick(targetElement);
          await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
          rememberCreatedNodeAlias(step, beforeNodeIds, playbackState);
        } else if (step.kind === "open_state_panel" && targetElement) {
          dispatchVirtualClick(targetElement);
        } else if (step.kind === "focus_node_field" && targetElement) {
          await focusGraphEditPlaybackField(step, targetElement, playbackState);
        } else if (step.kind === "type_node_field" || step.kind === "type_state_field") {
          await typeGraphEditPlaybackField(step, playbackState);
        } else if (step.kind === "commit_state_field" && targetElement) {
          const beforeStateKeys = listGraphEditPlaybackPortStateKeys(step, playbackState);
          dispatchVirtualClick(targetElement);
          await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
          rememberCreatedStateAlias(step, beforeStateKeys, playbackState);
        } else if (step.kind === "apply_graph_command") {
          const applyResponse = dispatchGraphEditPlaybackApplyCommand(step, response.graphCommands, playbackState);
          applyResults.push({
            commandId: step.commandId ?? "",
            ok: applyResponse?.ok === true,
            applied: applyResponse?.applied === true,
            issues: applyResponse?.issues.length ? applyResponse.issues : applyResponse ? [] : ["Graph edit command did not return a response."],
            diff: applyResponse?.diff ?? [],
          });
        }
        await waitForVirtualOperation(resolveGraphEditPlaybackStepDelayMs(step));
      }
    } finally {
      setGraphEditPlaybackRunning(false);
    }
    virtualCursorDragging.value = false;
    const revision = await requestGraphEditPlaybackSave({
      requestId,
      runId: operationPlan.runId ?? "",
      nodeId: operationPlan.nodeId ?? operationPlan.subgraphNodeId ?? "",
      reason: operationPlan.reason,
    });
    return buildGraphEditPlaybackAuditSummary({
      requestId,
      planOk: true,
      planIssues: response.issues,
      commandCount: response.graphCommands.length,
      playbackStepCount: response.playbackSteps.length,
      interrupted: isVirtualOperationInterrupted(token),
      applyResults,
      revision,
    });
  }

  async function ensureGraphEditPlaybackStepVisible(
    step: GraphEditPlaybackStep,
    playbackState: GraphEditPlaybackUiState,
  ) {
    const resolvedStep = resolveAliasedGraphEditPlaybackStep(step, playbackState);
    const response = requestGraphEditPlaybackEnsureVisible({
      position: resolvedStep.position,
      targetId: resolvedStep.target,
      nodeId: resolvedStep.nodeId,
      margin: BUDDY_GRAPH_EDIT_PLAYBACK_VISIBLE_MARGIN_PX,
    });
    if (response?.moved) {
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_VIEWPORT_SETTLE_MS);
    }
  }

  async function executeGraphEditPlaybackDragStep(
    step: GraphEditPlaybackStep,
    targetElement: HTMLElement | null,
    playbackState: GraphEditPlaybackUiState,
  ) {
    if (!targetElement) {
      return;
    }
    const resolvedStep = resolveAliasedGraphEditPlaybackStep(step, playbackState);
    await moveVirtualCursorToGraphEditStep(resolvedStep, targetElement);
    virtualCursorDragging.value = true;
    await dispatchVirtualGraphDragPointerEvents(resolvedStep, targetElement);
    virtualCursorDragging.value = false;
  }

  async function dispatchVirtualGraphDragPointerEvents(step: GraphEditPlaybackStep, targetElement: HTMLElement) {
    const token = activeVirtualOperationToken.value;
    const pointerSurface = resolveVirtualOperationAffordance("editor.canvas.surface")?.element ?? targetElement;
    const startPoint = resolveElementCenterPoint(targetElement);
    const endPoint = resolveGraphEditPlaybackDragEndPoint(step) ?? startPoint;
    const forceEmptyCanvasDrop = shouldForceGraphEditPlaybackEmptyCanvasDrop(step);
    dispatchVirtualPointerEvent(targetElement, "pointerdown", startPoint.x, startPoint.y);
    const dragPoints = buildVirtualDragPoints(startPoint, endPoint);
    for (const point of dragPoints) {
      if (isVirtualOperationInterrupted(token)) {
        break;
      }
      dispatchVirtualPointerEvent(pointerSurface, "pointermove", point.x, point.y, { forceEmptyCanvasDrop });
      await waitForVirtualOperation(moveVirtualCursorToClientPoint(point, { durationMs: 80 }));
    }
    dispatchVirtualPointerEvent(pointerSurface, "pointerup", endPoint.x, endPoint.y, { forceEmptyCanvasDrop });
  }

  function resolveGraphEditPlaybackDragEndPoint(step: GraphEditPlaybackStep): BuddyPosition | null {
    const endTarget = typeof step.endTarget === "string" ? step.endTarget : "";
    const positionPoint = resolveGraphEditPlaybackPositionClientPoint(
      step,
      resolveVirtualOperationAffordance("editor.canvas.surface")?.element ?? null,
    );
    if (positionPoint && (!endTarget || endTarget === "editor.canvas.surface" || endTarget === "editor.canvas.empty.createFirstNode")) {
      return positionPoint;
    }
    if (endTarget) {
      const endAffordance = resolveVirtualOperationAffordance(endTarget);
      if (endAffordance) {
        return resolveElementCenterPoint(endAffordance.element);
      }
      const anchorFallbackPoint = resolveGraphEditPlaybackAnchorNodeFallbackPoint(endTarget);
      if (anchorFallbackPoint) {
        return anchorFallbackPoint;
      }
    }
    const surface = resolveVirtualOperationAffordance("editor.canvas.surface");
    return surface ? resolveElementCenterPoint(surface.element) : null;
  }

  function resolveGraphEditPlaybackAnchorNodeFallbackPoint(targetId: string) {
    const nodeId = resolveGraphEditPlaybackAnchorNodeId(targetId);
    if (!nodeId) {
      return null;
    }
    const nodeAffordance = resolveVirtualOperationAffordance(`editor.canvas.node.${nodeId}`);
    return nodeAffordance ? resolveElementCenterPoint(nodeAffordance.element) : null;
  }

  function shouldSkipGraphEditPlaybackTextStep(
    step: GraphEditPlaybackStep,
    steps: GraphEditPlaybackStep[],
    stepIndex: number,
    playbackState: GraphEditPlaybackUiState,
    targetElement: HTMLElement | null,
  ) {
    if (step.kind === "focus_node_field") {
      const nextStep = steps[stepIndex + 1];
      return Boolean(
        nextStep?.kind === "type_node_field" &&
          nextStep.target === step.target &&
          isGraphEditPlaybackTextAlreadyCurrent(nextStep, playbackState, targetElement),
      );
    }
    if (step.kind === "type_node_field") {
      return isGraphEditPlaybackTextAlreadyCurrent(step, playbackState, targetElement);
    }
    return false;
  }

  function isGraphEditPlaybackTextAlreadyCurrent(
    step: GraphEditPlaybackStep,
    playbackState: GraphEditPlaybackUiState,
    targetElement: HTMLElement | null,
  ) {
    const expectedText = normalizeVirtualText(step.value ?? "");
    const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
    const input = resolveVirtualOperationTextInput(targetId);
    if (input) {
      return normalizeVirtualText(input.value) === expectedText;
    }
    return normalizeVirtualText(targetElement?.textContent ?? "") === expectedText;
  }

  async function focusGraphEditPlaybackField(
    step: GraphEditPlaybackStep,
    targetElement: HTMLElement,
    playbackState: GraphEditPlaybackUiState,
  ) {
    const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
    if (targetId.endsWith(".title") || targetId.endsWith(".description")) {
      dispatchVirtualPointerTap(targetElement);
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
      dispatchVirtualPointerTap(targetElement);
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
    } else {
      dispatchVirtualClick(targetElement);
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
    }
    resolveVirtualOperationTextInput(targetId)?.focus();
  }

  async function typeGraphEditPlaybackField(step: GraphEditPlaybackStep, playbackState: GraphEditPlaybackUiState) {
    const targetId = resolveAliasedGraphEditPlaybackTarget(step.target, playbackState);
    const input = resolveVirtualOperationTextInput(targetId);
    if (!input) {
      return;
    }
    await moveVirtualCursorToElement(input);
    input.focus();
    await replaceVirtualText(input, step.value ?? "");
    if (targetId.endsWith(".title") || targetId.endsWith(".description")) {
      await waitForVirtualOperation(BUDDY_GRAPH_EDIT_PLAYBACK_CLICK_SETTLE_MS);
      dispatchGraphEditPlaybackTextCommit(input, targetId);
    }
  }

  async function moveVirtualCursorToGraphEditStep(step: GraphEditPlaybackStep, element: HTMLElement) {
    const positionPoint = resolveGraphEditPlaybackPositionClientPoint(
      step,
      resolveVirtualOperationAffordance("editor.canvas.surface")?.element ?? null,
    );
    if (positionPoint && (step.kind === "move_virtual_cursor" || step.kind === "open_node_creation_menu")) {
      await waitForVirtualOperation(moveVirtualCursorToClientPoint(positionPoint));
      return;
    }
    await moveVirtualCursorToElement(element);
  }

  return {
    executeBuddyVirtualGraphEditOperation,
  };
}

function dispatchGraphEditPlaybackTextCommit(element: HTMLElement, targetId: string) {
  const eventInit = {
    bubbles: true,
    cancelable: true,
    key: "Enter",
    code: "Enter",
    ctrlKey: targetId.endsWith(".description"),
    metaKey: false,
  };
  element.dispatchEvent(new KeyboardEvent("keydown", eventInit));
  element.dispatchEvent(new KeyboardEvent("keyup", eventInit));
}

function rememberCreatedNodeAlias(step: GraphEditPlaybackStep, beforeNodeIds: Set<string>, playbackState: GraphEditPlaybackUiState) {
  const plannedNodeId = step.nodeId ?? "";
  if (!plannedNodeId || playbackState.nodeIdAliases.has(plannedNodeId)) {
    return;
  }
  const createdNodeIds = [...listGraphEditPlaybackNodeAffordanceIds()].filter((nodeId) => !beforeNodeIds.has(nodeId));
  if (createdNodeIds.length === 1) {
    playbackState.nodeIdAliases.set(plannedNodeId, createdNodeIds[0]!);
  }
}

function rememberCreatedStateAlias(step: GraphEditPlaybackStep, beforeStateKeys: Set<string>, playbackState: GraphEditPlaybackUiState) {
  const plannedStateKey = step.stateKey ?? "";
  if (!plannedStateKey || playbackState.stateKeyAliases.has(plannedStateKey)) {
    return;
  }
  const createdStateKeys = [...listGraphEditPlaybackPortStateKeys(step, playbackState)].filter((stateKey) => !beforeStateKeys.has(stateKey));
  if (createdStateKeys.length === 1) {
    playbackState.stateKeyAliases.set(plannedStateKey, createdStateKeys[0]!);
  }
}

function resolveElementCenterPoint(element: HTMLElement): BuddyPosition {
  const rect = element.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}
