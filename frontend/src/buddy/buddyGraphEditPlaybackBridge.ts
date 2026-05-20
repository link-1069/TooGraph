import type { GraphEditCommand, GraphEditIntent, GraphEditPlaybackStep } from "../editor/workspace/graphEditPlaybackModel.ts";
import type { GraphPosition } from "../types/node-system.ts";
import type {
  GraphEditPlaybackAuditDiffEntry,
  GraphEditPlaybackAuditRevision,
} from "./graphEditPlaybackAudit.ts";

export const TOOGRAPH_GRAPH_EDIT_PLAYBACK_RUNNING_EVENT = "toograph:graph-edit-playback-running";
export const TOOGRAPH_GRAPH_EDIT_PLAYBACK_ENSURE_VISIBLE_EVENT = "toograph:graph-edit-playback-ensure-visible";
export const TOOGRAPH_GRAPH_EDIT_PLAYBACK_APPLY_COMMAND_EVENT = "toograph:graph-edit-playback-apply-command";
export const TOOGRAPH_GRAPH_EDIT_PLAYBACK_SAVE_EVENT = "toograph:graph-edit-playback-save-request";
export const BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_WAIT_MS = 2400;
export const BUDDY_GRAPH_EDIT_PLAYBACK_TARGET_RETRY_MS = 80;
export const BUDDY_GRAPH_EDIT_PLAYBACK_VIEWPORT_SETTLE_MS = 80;
export const BUDDY_GRAPH_EDIT_PLAYBACK_VISIBLE_MARGIN_PX = 112;

export type GraphEditPlaybackPlanRequestResponse = {
  requestId: string;
  ok: boolean;
  graphCommands: GraphEditCommand[];
  playbackSteps: GraphEditPlaybackStep[];
  issues: string[];
};

export type GraphEditPlaybackUiState = {
  nodeIdAliases: Map<string, string>;
  stateKeyAliases: Map<string, string>;
};

type GraphEditPlaybackEnsureVisibleResponse = {
  ok: boolean;
  moved: boolean;
};

type GraphEditPlaybackApplyCommandResponse = {
  ok: boolean;
  applied: boolean;
  issues: string[];
  diff?: GraphEditPlaybackAuditDiffEntry[];
};

type GraphEditPlaybackSaveResponse = {
  ok: boolean;
  graphId: string | null;
  revisionId: string | null;
  issues: string[];
};

export function createGraphEditPlaybackUiState(): GraphEditPlaybackUiState {
  return {
    nodeIdAliases: new Map(),
    stateKeyAliases: new Map(),
  };
}

export function requestGraphEditPlaybackPlan(input: { requestId: string; graphEditIntents: GraphEditIntent[] }): GraphEditPlaybackPlanRequestResponse | null {
  if (typeof window === "undefined") {
    return null;
  }
  const detail: {
    requestId: string;
    graphEditIntents: GraphEditIntent[];
    response: GraphEditPlaybackPlanRequestResponse | null;
  } = {
    requestId: input.requestId,
    graphEditIntents: input.graphEditIntents.map((intent) => ({ ...intent })),
    response: null,
  };
  window.dispatchEvent(new CustomEvent("toograph:graph-edit-playback-plan-request", { detail }));
  return detail.response;
}

export function setGraphEditPlaybackRunning(running: boolean) {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(TOOGRAPH_GRAPH_EDIT_PLAYBACK_RUNNING_EVENT, {
      detail: { running },
    }),
  );
}

export function requestGraphEditPlaybackEnsureVisible(input: {
  position?: GraphPosition;
  targetId?: string;
  nodeId?: string;
  margin?: number;
}): GraphEditPlaybackEnsureVisibleResponse | null {
  if (typeof window === "undefined") {
    return null;
  }
  const detail: {
    position?: GraphPosition;
    targetId?: string;
    nodeId?: string;
    margin?: number;
    response: GraphEditPlaybackEnsureVisibleResponse | null;
  } = {
    position: input.position,
    targetId: input.targetId,
    nodeId: input.nodeId,
    margin: input.margin,
    response: null,
  };
  window.dispatchEvent(new CustomEvent(TOOGRAPH_GRAPH_EDIT_PLAYBACK_ENSURE_VISIBLE_EVENT, { detail }));
  return detail.response;
}

export function dispatchGraphEditPlaybackApplyCommand(
  step: GraphEditPlaybackStep,
  graphCommands: GraphEditCommand[],
  playbackState: GraphEditPlaybackUiState,
): GraphEditPlaybackApplyCommandResponse | null {
  if (typeof window === "undefined") {
    return null;
  }
  const commandId = step.commandId ?? step.commandIds?.[0] ?? "";
  const command = graphCommands.find((candidate) => candidate.commandId === commandId) ?? null;
  if (!command) {
    return null;
  }
  const detail: {
    command: GraphEditCommand;
    response: GraphEditPlaybackApplyCommandResponse | null;
  } = {
    command: resolveAliasedGraphEditPlaybackCommand(command, playbackState),
    response: null,
  };
  window.dispatchEvent(new CustomEvent(TOOGRAPH_GRAPH_EDIT_PLAYBACK_APPLY_COMMAND_EVENT, { detail }));
  return detail.response;
}

export async function requestGraphEditPlaybackSave(input: {
  requestId: string;
  runId: string;
  nodeId: string;
  reason: string;
}): Promise<GraphEditPlaybackAuditRevision> {
  if (typeof window === "undefined") {
    return {
      status: "failed",
      graphId: null,
      revisionId: null,
      issues: ["Graph edit revision save requires a browser window."],
    };
  }
  const detail: {
    requestId: string;
    runId: string;
    nodeId: string;
    reason: string;
    response: GraphEditPlaybackSaveResponse | Promise<GraphEditPlaybackSaveResponse> | null;
  } = {
    requestId: input.requestId,
    runId: input.runId,
    nodeId: input.nodeId,
    reason: input.reason,
    response: null,
  };
  window.dispatchEvent(new CustomEvent(TOOGRAPH_GRAPH_EDIT_PLAYBACK_SAVE_EVENT, { detail }));
  const response = isGraphEditPlaybackSaveResponsePromise(detail.response) ? await detail.response : detail.response;
  if (!response) {
    return {
      status: "failed",
      graphId: null,
      revisionId: null,
      issues: ["Graph edit revision save did not return a response."],
    };
  }
  if (!response.ok) {
    return {
      status: "failed",
      graphId: response.graphId ?? null,
      revisionId: response.revisionId ?? null,
      issues: response.issues.length ? response.issues : ["Graph edit revision save failed."],
    };
  }
  return {
    status: "saved",
    graphId: response.graphId,
    revisionId: response.revisionId,
    issues: response.issues,
  };
}

function isGraphEditPlaybackSaveResponsePromise(
  response: GraphEditPlaybackSaveResponse | Promise<GraphEditPlaybackSaveResponse> | null,
): response is Promise<GraphEditPlaybackSaveResponse> {
  return Boolean(response && typeof (response as Promise<GraphEditPlaybackSaveResponse>).then === "function");
}

export function resolveAliasedGraphEditPlaybackStep(step: GraphEditPlaybackStep, playbackState: GraphEditPlaybackUiState): GraphEditPlaybackStep {
  return {
    ...step,
    target: resolveAliasedGraphEditPlaybackTarget(step.target, playbackState),
    endTarget: step.endTarget ? resolveAliasedGraphEditPlaybackTarget(step.endTarget, playbackState) : undefined,
    nodeId: step.nodeId ? playbackState.nodeIdAliases.get(step.nodeId) ?? step.nodeId : undefined,
    stateKey: step.stateKey ? playbackState.stateKeyAliases.get(step.stateKey) ?? step.stateKey : undefined,
    sourceNodeId: step.sourceNodeId ? playbackState.nodeIdAliases.get(step.sourceNodeId) ?? step.sourceNodeId : undefined,
    sourceStateKey: step.sourceStateKey ? playbackState.stateKeyAliases.get(step.sourceStateKey) ?? step.sourceStateKey : undefined,
  };
}

function resolveAliasedGraphEditPlaybackCommand(command: GraphEditCommand, playbackState: GraphEditPlaybackUiState): GraphEditCommand {
  switch (command.kind) {
    case "create_node":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
        creationSource: command.creationSource
          ? {
              ...command.creationSource,
              sourceNodeId: resolveGraphEditPlaybackNodeAlias(command.creationSource.sourceNodeId, playbackState),
              ...(command.creationSource.kind === "state"
                ? { stateKey: resolveGraphEditPlaybackStateAlias(command.creationSource.stateKey, playbackState) }
                : {}),
            }
          : null,
      };
    case "update_node":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
    case "move_node":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
    case "create_state":
      return {
        ...command,
        stateKey: resolveGraphEditPlaybackStateAlias(command.stateKey, playbackState),
        targetNodeId: command.targetNodeId ? resolveGraphEditPlaybackNodeAlias(command.targetNodeId, playbackState) : undefined,
      };
    case "update_state":
      return {
        ...command,
        stateKey: resolveGraphEditPlaybackStateAlias(command.stateKey, playbackState),
      };
    case "update_input_config":
    case "update_output_config":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
    case "bind_state":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
        stateKey: resolveGraphEditPlaybackStateAlias(command.stateKey, playbackState),
        sourceNodeId: command.sourceNodeId ? resolveGraphEditPlaybackNodeAlias(command.sourceNodeId, playbackState) : undefined,
      };
    case "connect_nodes":
      return {
        ...command,
        sourceNodeId: resolveGraphEditPlaybackNodeAlias(command.sourceNodeId, playbackState),
        targetNodeId: resolveGraphEditPlaybackNodeAlias(command.targetNodeId, playbackState),
      };
    case "connect_route":
      return {
        ...command,
        sourceNodeId: resolveGraphEditPlaybackNodeAlias(command.sourceNodeId, playbackState),
        targetNodeId: resolveGraphEditPlaybackNodeAlias(command.targetNodeId, playbackState),
      };
    case "select_action":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
    case "delete_node":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
    case "restore_node":
      return {
        ...command,
        nodeId: resolveGraphEditPlaybackNodeAlias(command.nodeId, playbackState),
      };
  }
}

function resolveGraphEditPlaybackNodeAlias(nodeId: string, playbackState: GraphEditPlaybackUiState) {
  return playbackState.nodeIdAliases.get(nodeId) ?? nodeId;
}

function resolveGraphEditPlaybackStateAlias(stateKey: string, playbackState: GraphEditPlaybackUiState) {
  return playbackState.stateKeyAliases.get(stateKey) ?? stateKey;
}

export function resolveAliasedGraphEditPlaybackTarget(targetId: string, playbackState: GraphEditPlaybackUiState) {
  let resolvedTargetId = targetId;
  for (const [plannedNodeId, actualNodeId] of playbackState.nodeIdAliases) {
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `editor.canvas.node.${plannedNodeId}`, `editor.canvas.node.${actualNodeId}`);
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `editor.canvas.anchor.${plannedNodeId}:`, `editor.canvas.anchor.${actualNodeId}:`);
  }
  for (const [plannedStateKey, actualStateKey] of playbackState.stateKeyAliases) {
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `:state-out:${plannedStateKey}`, `:state-out:${actualStateKey}`);
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `:state-in:${plannedStateKey}`, `:state-in:${actualStateKey}`);
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `.port.input.${plannedStateKey}`, `.port.input.${actualStateKey}`);
    resolvedTargetId = replaceAllLiteral(resolvedTargetId, `.port.output.${plannedStateKey}`, `.port.output.${actualStateKey}`);
  }
  return resolvedTargetId;
}

function replaceAllLiteral(value: string, search: string, replacement: string) {
  return value.split(search).join(replacement);
}
