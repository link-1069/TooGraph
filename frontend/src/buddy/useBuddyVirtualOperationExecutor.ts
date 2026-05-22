import { nextTick, type Ref } from "vue";

import { fetchTemplate, fetchTemplates, runGraph } from "../api/graphs.ts";
import { fetchRun, resumeRun } from "../api/runs.ts";
import { shouldPollRunStatus } from "../lib/run-event-stream.ts";
import type {
  BuddyVirtualOperation,
  BuddyVirtualOperationRequest,
  BuddyVirtualOperationTriggeredRun,
} from "../stores/buddyMascotDebug.ts";
import type { GraphPayload, TemplateRecord } from "../types/node-system.ts";
import type { RunDetail } from "../types/run.ts";
import { buildBuddyTemplateRunGraph } from "./buddyTemplateRunGraph.ts";
import {
  resolveVirtualOperationAffordance,
  resolveVirtualOperationTextInput,
} from "./buddyVirtualOperationTargets.ts";
import {
  dispatchVirtualClick,
  dispatchVirtualInputEvents,
} from "./buddyVirtualPointerEvents.ts";
import {
  normalizeTemplateRunMatchText,
  resolveTemplateRunInputTextInput,
  resolveTemplateRunTargetAffordance,
  routeMatchesVirtualOperationTargetPath,
} from "./buddyVirtualTemplateRunTargets.ts";
import { attachPageOperationRuntimeContext, type PageOperationRuntimeContext } from "./pageOperationAffordances.ts";
import {
  buildPageOperationArtifactRefs,
  buildPageOperationResult,
  buildPageOperationResumePayload,
  buildPageOperationTargetRunValidation,
  canAutoResumePageOperationRun,
  type PageOperationResult,
  type PageOperationResultStatus,
  type PageOperationRetryRecord,
} from "./pageOperationResume.ts";
import {
  resolveBuddyVirtualOperationUserAction,
} from "./buddyVirtualOperationInteractionPolicy.ts";
import type {
  BuddyPageOperationForegroundRun,
  BuddyPageOperationRuntimeContextOptions,
} from "./useBuddyPageOperationContext.ts";
import type { BuddyVirtualOperationToken } from "./useBuddyVirtualOperationLifecycle.ts";
import {
  resolveBuddyVirtualOperationPlanFromActivityEvent,
  type BuddyVirtualOperationPlan,
} from "./virtualOperationProtocol.ts";

const RUN_POLL_INTERVAL_MS = 700;
const BUDDY_VIRTUAL_OPERATION_CLICK_SETTLE_MS = 80;
const BUDDY_VIRTUAL_OPERATION_TYPE_CHARACTER_DELAY_MS = 18;
const BUDDY_VIRTUAL_OPERATION_TRIGGERED_RUN_WAIT_MS = 4000;
const BUDDY_VIRTUAL_OPERATION_TRIGGERED_RUN_POLL_MS = 80;
const BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS = 4000;
const BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS = 80;
const BUDDY_VIRTUAL_TEMPLATE_SEARCH_SETTLE_MS = 180;
const BUDDY_PAGE_OPERATION_TRIGGERED_RUN_MAX_WAIT_MS = 120000;

type BuddyVirtualOperationCommandResult = {
  status: PageOperationResultStatus;
  graphEditSummary: Record<string, unknown> | null;
  retryChain: PageOperationRetryRecord[];
};

type BuddyBackgroundTemplateRunExecution = {
  triggeredRun: BuddyVirtualOperationTriggeredRun;
  graph: GraphPayload;
};

type BuddyPageOperationRuntimeContextResult = {
  pageContext: string;
  actionRuntimeContext: PageOperationRuntimeContext;
};

type BuddyAutoResumedPageOperationFinishOptions = {
  runId: string;
  assistantMessageId: string;
  sessionId: string;
};

type BuddyVirtualOperationDebugBridge = {
  beginVirtualOperationRunAttribution: (operationPlan: BuddyVirtualOperationPlan) => void;
  recordVirtualOperationTriggeredRun: (triggeredRun: BuddyVirtualOperationTriggeredRun) => void;
  requestVirtualOperation: (operationPlan: BuddyVirtualOperationPlan) => void;
  resolveVirtualOperationTriggeredRun: (operationRequestId: string) => BuddyVirtualOperationTriggeredRun | null;
  setVirtualCursorEnabled: (enabled: boolean) => void;
};

type BuddyVirtualOperationExecutorOptions = {
  activeRunId: Ref<string | null>;
  activeSessionId: Ref<string | null>;
  activeVirtualOperationToken: Ref<BuddyVirtualOperationToken | null>;
  buildPageOperationRuntimeContext: (options?: BuddyPageOperationRuntimeContextOptions) => BuddyPageOperationRuntimeContextResult;
  buildTriggeredForegroundRunFact: (
    triggeredRun: { runId: string; initialStatus: string } | null,
    runDetail: RunDetail | null,
  ) => BuddyPageOperationForegroundRun | null;
  debugBridge: BuddyVirtualOperationDebugBridge;
  executeBuddyVirtualGraphEditOperation: (
    operationPlan: BuddyVirtualOperationPlan,
    operation: BuddyVirtualOperation,
  ) => Promise<Record<string, unknown>>;
  finishAutoResumedPageOperationRun: (options: BuddyAutoResumedPageOperationFinishOptions) => Promise<void>;
  finishVirtualOperation: (token: BuddyVirtualOperationToken) => boolean;
  beginBackgroundVirtualOperationLifecycle: (label: string) => BuddyVirtualOperationToken;
  beginVirtualOperationLifecycle: (label: string) => BuddyVirtualOperationToken;
  ensureVirtualCursorReadyForOperation: () => Promise<void>;
  interruptVirtualOperationLifecycle: (label: string) => boolean;
  isVirtualOperationInterrupted: (token: BuddyVirtualOperationToken | null) => boolean;
  moveVirtualCursorToElement: (element: HTMLElement) => Promise<void>;
  promoteBackgroundTemplateRunResultToBuddyReply: (
    operationPlan: BuddyVirtualOperationPlan,
    runDetail: RunDetail,
    graph: GraphPayload,
  ) => void;
  recordVirtualOperationRetry: (token: BuddyVirtualOperationToken | null, record: PageOperationRetryRecord) => void;
  buildVirtualOperationRetryRecord: (
    kind: PageOperationRetryRecord["kind"],
    targetId: string,
    attempts: number,
    status: PageOperationRetryRecord["status"],
    startedAt: number,
  ) => PageOperationRetryRecord;
  replaceVirtualText: (element: HTMLInputElement | HTMLTextAreaElement, text: string) => Promise<void>;
  resetPausedBuddyPause: () => void;
  resolveBuddyRunControllerMessageId: (runId: string) => string;
  routePath: Ref<string>;
  stopBuddyIdleAnimation: () => void;
  syncBackgroundTemplateRunDisplay: (
    operationPlan: BuddyVirtualOperationPlan,
    runDetail: RunDetail,
    graph: GraphPayload,
  ) => void;
  t: (key: string) => string;
  virtualCursorDragging: Ref<boolean>;
  waitForFrontendObservation: (timeoutMs: number) => Promise<void>;
  waitForVirtualOperation: (timeoutMs: number, token?: BuddyVirtualOperationToken | null) => Promise<void>;
};

export function useBuddyVirtualOperationExecutor({
  activeRunId,
  activeSessionId,
  activeVirtualOperationToken,
  buildPageOperationRuntimeContext,
  buildTriggeredForegroundRunFact,
  debugBridge,
  executeBuddyVirtualGraphEditOperation,
  finishAutoResumedPageOperationRun,
  finishVirtualOperation,
  beginBackgroundVirtualOperationLifecycle,
  beginVirtualOperationLifecycle,
  ensureVirtualCursorReadyForOperation,
  interruptVirtualOperationLifecycle,
  isVirtualOperationInterrupted,
  moveVirtualCursorToElement,
  promoteBackgroundTemplateRunResultToBuddyReply,
  recordVirtualOperationRetry,
  buildVirtualOperationRetryRecord,
  replaceVirtualText,
  resetPausedBuddyPause,
  resolveBuddyRunControllerMessageId,
  routePath,
  stopBuddyIdleAnimation,
  syncBackgroundTemplateRunDisplay,
  t,
  virtualCursorDragging,
  waitForFrontendObservation,
  waitForVirtualOperation,
}: BuddyVirtualOperationExecutorOptions) {
  function handleBuddyVirtualUiOperationEvent(payload: Record<string, unknown>) {
    const operationPlan = resolveBuddyVirtualOperationPlanFromActivityEvent(payload);
    if (!operationPlan) {
      return;
    }
    debugBridge.requestVirtualOperation(operationPlan);
  }

  async function executeVirtualOperationRequest(request: BuddyVirtualOperationRequest | null) {
    if (!request) {
      return;
    }
    const operationPlan = request.request;
    const pageOperationContextBefore = buildPageOperationRuntimeContext();
    const routeBefore = routePath.value;
    let status: PageOperationResultStatus = "succeeded";
    let error: string | null = null;
    let triggeredRun: BuddyVirtualOperationTriggeredRun | null = null;
    let triggeredRunDetail: RunDetail | null = null;
    let graphEditSummary: Record<string, unknown> | null = null;
    let retryChain: PageOperationRetryRecord[] = [];
    try {
      const backgroundTemplateOperation = resolveBackgroundTemplateRunOperation(operationPlan);
      if (backgroundTemplateOperation) {
        const token = beginBackgroundVirtualOperation();
        try {
          const execution = await executeBuddyBackgroundRunTemplateOperation(
            operationPlan,
            backgroundTemplateOperation,
            pageOperationContextBefore,
          );
          triggeredRun = execution.triggeredRun;
          const completedTriggeredRunDetail = await waitForTriggeredRunCompletion(triggeredRun, {
            onSnapshot: (runDetail) => syncBackgroundTemplateRunDisplay(operationPlan, runDetail, execution.graph),
          });
          triggeredRunDetail = completedTriggeredRunDetail;
          if (completedTriggeredRunDetail) {
            promoteBackgroundTemplateRunResultToBuddyReply(operationPlan, completedTriggeredRunDetail, execution.graph);
          }
          status = completedTriggeredRunDetail?.status === "failed" ? "failed" : "succeeded";
        } finally {
          if (finishVirtualOperation(token)) {
            virtualCursorDragging.value = false;
          }
        }
      } else {
        debugBridge.beginVirtualOperationRunAttribution(operationPlan);
        const commandResult = await executeVirtualOperationCommands(operationPlan);
        status = commandResult.status;
        graphEditSummary = commandResult.graphEditSummary;
        retryChain = commandResult.retryChain;
        triggeredRun = await waitForVirtualOperationTriggeredRun(operationPlan);
        triggeredRunDetail = triggeredRun ? await waitForTriggeredRunCompletion(triggeredRun) : null;
        if (status !== "failed" && triggeredRunDetail && !shouldPollRunStatus(triggeredRunDetail.status)) {
          status = triggeredRunDetail.status === "failed" ? "failed" : "succeeded";
        }
      }
    } catch (caughtError) {
      status = "failed";
      error = caughtError instanceof Error ? caughtError.message : String(caughtError);
    }
    await nextTick();
    const latestForegroundRun = buildTriggeredForegroundRunFact(triggeredRun, triggeredRunDetail);
    const pageOperationContextAfterBase = buildPageOperationRuntimeContext({ latestForegroundRun });
    const operationResult = buildPageOperationResult({
      operationPlan,
      status,
      routeBefore,
      routeAfter: routePath.value,
      pageOperationContextBefore: pageOperationContextBefore.actionRuntimeContext,
      pageOperationContextAfter: pageOperationContextAfterBase.actionRuntimeContext,
      triggeredRunId: triggeredRun?.runId ?? null,
      triggeredGraphId: triggeredRun?.graphId ?? null,
      triggeredRunInitialStatus: triggeredRun?.initialStatus ?? null,
      triggeredRunStatus: triggeredRunDetail?.status ?? triggeredRun?.initialStatus ?? null,
      triggeredRunFinalResult: triggeredRunDetail?.final_result ?? null,
      artifactRefs: buildPageOperationArtifactRefs(triggeredRunDetail),
      targetRunValidation: buildPageOperationTargetRunValidation(triggeredRunDetail),
      retryChain,
      graphEditSummary,
      error,
    });
    const pageOperationContextAfter = buildPageOperationRuntimeContext({
      latestOperationReport: operationResult.operation_report,
      latestForegroundRun,
    });
    await maybeAutoResumePageOperationRun(operationPlan, operationResult, pageOperationContextAfter);
  }

  async function executeVirtualOperationCommands(operationPlan: BuddyVirtualOperationPlan): Promise<BuddyVirtualOperationCommandResult> {
    stopBuddyIdleAnimation();
    const token = beginVirtualOperation();
    let graphEditSummary: Record<string, unknown> | null = null;
    try {
      await ensureVirtualCursorReadyForOperation();
      for (const operation of operationPlan.operations) {
        if (isVirtualOperationInterrupted(token)) {
          break;
        }
        const commandResult = await executeBuddyVirtualOperationCommand(operationPlan, operation);
        if (commandResult?.graphEditSummary) {
          graphEditSummary = commandResult.graphEditSummary;
        }
      }
      if (!isVirtualOperationInterrupted(token) && (operationPlan.cursorLifecycle === "return_after_step" || operationPlan.cursorLifecycle === "return_at_end")) {
        await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_CLICK_SETTLE_MS, activeVirtualOperationToken.value);
        if (!isVirtualOperationInterrupted(token)) {
          debugBridge.setVirtualCursorEnabled(false);
        }
      }
      if (isVirtualOperationInterrupted(token)) {
        debugBridge.setVirtualCursorEnabled(false);
      }
      return {
        status: resolveVirtualOperationCommandStatus(token, graphEditSummary),
        graphEditSummary,
        retryChain: [...token.retryChain],
      };
    } finally {
      if (finishVirtualOperation(token)) {
        virtualCursorDragging.value = false;
      }
    }
  }

  function resolveVirtualOperationCommandStatus(
    token: BuddyVirtualOperationToken,
    graphEditSummary: Record<string, unknown> | null,
  ): PageOperationResultStatus {
    if (isVirtualOperationInterrupted(token)) {
      return "interrupted";
    }
    if (graphEditSummary?.status === "failed") {
      return "failed";
    }
    return "succeeded";
  }

  async function maybeAutoResumePageOperationRun(
    operationPlan: BuddyVirtualOperationPlan,
    operationResult: PageOperationResult,
    pageOperationContextAfter: BuddyPageOperationRuntimeContextResult,
  ) {
    if (!operationPlan.runId || !operationPlan.operationRequestId || !operationPlan.expectedContinuation) {
      return;
    }
    const runDetail = await fetchRun(operationPlan.runId);
    if (!canAutoResumePageOperationRun(runDetail, operationPlan.operationRequestId)) {
      return;
    }
    const assistantMessageId = resolveBuddyRunControllerMessageId(operationPlan.runId);
    const sessionId = activeSessionId.value;
    const response = await resumeRun(
      operationPlan.runId,
      buildPageOperationResumePayload({
        operationResult,
        pageContext: pageOperationContextAfter.pageContext,
        pageOperationContext: pageOperationContextAfter.actionRuntimeContext,
      }),
    );
    activeRunId.value = response.run_id;
    resetPausedBuddyPause();
    if (!assistantMessageId || !sessionId) {
      activeRunId.value = null;
      return;
    }
    await finishAutoResumedPageOperationRun({
      runId: response.run_id,
      assistantMessageId,
      sessionId,
    });
  }

  function resolveBackgroundTemplateRunOperation(
    operationPlan: BuddyVirtualOperationPlan,
  ): Extract<BuddyVirtualOperation, { kind: "run_template" }> | null {
    if (operationPlan.operations.length !== 1) {
      return null;
    }
    const operation = operationPlan.operations[0];
    return operation?.kind === "run_template" ? operation : null;
  }

  async function executeBuddyBackgroundRunTemplateOperation(
    operationPlan: BuddyVirtualOperationPlan,
    operation: Extract<BuddyVirtualOperation, { kind: "run_template" }>,
    pageOperationContext: BuddyPageOperationRuntimeContextResult,
  ): Promise<BuddyBackgroundTemplateRunExecution> {
    const operationRequestId = String(operationPlan.operationRequestId ?? "").trim();
    if (!operationRequestId) {
      throw new Error("缺少页面操作请求 ID。");
    }
    const template = await fetchBuddyVirtualRunTemplate(operation);
    const { graph } = buildBuddyTemplateRunGraph(template, {
      inputText: operation.inputText,
      operationRequestId,
      templateId: operation.templateId || template.template_id,
      templateName: operation.templateName || template.label || template.default_graph_name,
    });
    const response = await runGraph(attachPageOperationRuntimeContext(graph, pageOperationContext.actionRuntimeContext));
    const triggeredRun: BuddyVirtualOperationTriggeredRun = {
      operationRequestId,
      targetId: operation.runTargetId || "editor.action.runActiveGraph",
      tabId: "background",
      runId: response.run_id,
      graphId: graph.graph_id ?? null,
      initialStatus: response.status,
    };
    debugBridge.recordVirtualOperationTriggeredRun(triggeredRun);
    return { triggeredRun, graph };
  }

  async function fetchBuddyVirtualRunTemplate(operation: Extract<BuddyVirtualOperation, { kind: "run_template" }>) {
    if (operation.templateId) {
      try {
        return await fetchTemplate(operation.templateId);
      } catch {
        // Fall back to visible-search semantics below when the template id is stale or unavailable.
      }
    }
    const templates = await fetchTemplates();
    const expectedTexts = [operation.templateId, operation.templateName, operation.searchText]
      .map(normalizeTemplateRunMatchText)
      .filter(Boolean);
    const matchedTemplate = templates.find((template) => templateMatchesVirtualRunTarget(template, expectedTexts));
    if (!matchedTemplate) {
      throw new Error(`找不到目标图模板：${operation.templateName || operation.templateId || operation.searchText}`);
    }
    return matchedTemplate;
  }

  function beginVirtualOperation(): BuddyVirtualOperationToken {
    return beginVirtualOperationLifecycle(t("buddy.virtualOperation.running"));
  }

  function beginBackgroundVirtualOperation(): BuddyVirtualOperationToken {
    stopBuddyIdleAnimation();
    return beginBackgroundVirtualOperationLifecycle(t("buddy.virtualOperation.backgroundRunning"));
  }

  function interruptVirtualOperation() {
    const action = resolveBuddyVirtualOperationUserAction({
      isOperationRunning: Boolean(activeVirtualOperationToken.value),
      source: "stop_button",
    });
    if (!action.interruptOperation) {
      return;
    }
    if (interruptVirtualOperationLifecycle(t("buddy.virtualOperation.stopping"))) {
      virtualCursorDragging.value = false;
    }
  }

  async function waitForVirtualOperationTriggeredRun(
    operationPlan: BuddyVirtualOperationPlan,
  ): Promise<BuddyVirtualOperationTriggeredRun | null> {
    const operationRequestId = String(operationPlan.operationRequestId ?? "").trim();
    if (!operationRequestId || !hasRunActiveGraphOperation(operationPlan)) {
      return null;
    }
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TRIGGERED_RUN_WAIT_MS;
    while (Date.now() <= deadline) {
      const triggeredRun = debugBridge.resolveVirtualOperationTriggeredRun(operationRequestId);
      if (triggeredRun) {
        return triggeredRun;
      }
      await waitForFrontendObservation(BUDDY_VIRTUAL_OPERATION_TRIGGERED_RUN_POLL_MS);
    }
    return debugBridge.resolveVirtualOperationTriggeredRun(operationRequestId);
  }

  async function waitForTriggeredRunCompletion(
    triggeredRun: BuddyVirtualOperationTriggeredRun,
    options: {
      token?: BuddyVirtualOperationToken | null;
      onSnapshot?: (runDetail: RunDetail) => void;
    } = {},
  ): Promise<RunDetail | null> {
    const deadline = Date.now() + BUDDY_PAGE_OPERATION_TRIGGERED_RUN_MAX_WAIT_MS;
    let latestRun: RunDetail | null = null;
    while (!(options.token && isVirtualOperationInterrupted(options.token)) && Date.now() <= deadline) {
      try {
        latestRun = await fetchRun(triggeredRun.runId);
        options.onSnapshot?.(latestRun);
        if (!shouldPollRunStatus(latestRun.status)) {
          return latestRun;
        }
      } catch {
        return latestRun;
      }
      if (options.token) {
        await waitForVirtualOperation(RUN_POLL_INTERVAL_MS, options.token);
      } else {
        await waitForFrontendObservation(RUN_POLL_INTERVAL_MS);
      }
    }
    return latestRun;
  }

  function hasRunActiveGraphOperation(operationPlan: BuddyVirtualOperationPlan) {
    return operationPlan.operations.some(
      (operation) => operation.kind === "run_template" || ("targetId" in operation && operation.targetId === "editor.action.runActiveGraph"),
    );
  }

  async function executeBuddyVirtualOperationCommand(
    operationPlan: BuddyVirtualOperationPlan,
    operation: BuddyVirtualOperation,
  ): Promise<{ graphEditSummary: Record<string, unknown> } | null> {
    switch (operation.kind) {
      case "click":
        await executeBuddyVirtualClickOperation(operation);
        return null;
      case "focus":
        await executeBuddyVirtualFocusOperation(operation);
        return null;
      case "clear":
        await executeBuddyVirtualClearOperation(operation);
        return null;
      case "type":
        await executeBuddyVirtualTypeOperation(operation);
        return null;
      case "press":
        await executeBuddyVirtualPressOperation(operation);
        return null;
      case "wait":
        await executeBuddyVirtualWaitOperation(operation);
        return null;
      case "graph_edit":
        return { graphEditSummary: await executeBuddyVirtualGraphEditOperation(operationPlan, operation) };
      case "run_template":
        await executeBuddyVirtualRunTemplateOperation(operation);
        return null;
    }
  }

  async function executeBuddyVirtualClickOperation(operation: BuddyVirtualOperation) {
    if (!("targetId" in operation)) {
      return;
    }
    const token = activeVirtualOperationToken.value;
    await clickVirtualOperationTargetWithRetry(operation.targetId, token);
  }

  async function executeBuddyVirtualFocusOperation(operation: BuddyVirtualOperation) {
    if (!("targetId" in operation)) {
      return;
    }
    const token = activeVirtualOperationToken.value;
    const affordance = await waitForVirtualOperationAffordance(operation.targetId, token);
    if (!affordance) {
      throw new Error(`找不到可见页面目标：${operation.targetId}`);
    }
    await moveVirtualCursorToElement(affordance.element);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    affordance.element.focus();
  }

  async function executeBuddyVirtualClearOperation(operation: BuddyVirtualOperation) {
    if (!("targetId" in operation)) {
      return;
    }
    await executeBuddyVirtualFocusOperation(operation);
    const input = await waitForVirtualOperationTextInput(operation.targetId, activeVirtualOperationToken.value);
    if (!input) {
      throw new Error(`找不到可编辑页面目标：${operation.targetId}`);
    }
    input.value = "";
    dispatchVirtualInputEvents(input, "deleteContentBackward", "");
  }

  async function executeBuddyVirtualTypeOperation(operation: BuddyVirtualOperation) {
    if (!("targetId" in operation) || operation.kind !== "type" || !operation.text) {
      return;
    }
    const token = activeVirtualOperationToken.value;
    await executeBuddyVirtualFocusOperation(operation);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    const input = await waitForVirtualOperationTextInput(operation.targetId, token);
    if (!input) {
      throw new Error(`找不到可编辑页面目标：${operation.targetId}`);
    }
    await typeVirtualText(input, operation.text);
  }

  async function executeBuddyVirtualPressOperation(operation: BuddyVirtualOperation) {
    if (!("targetId" in operation) || operation.kind !== "press" || !operation.key) {
      return;
    }
    const token = activeVirtualOperationToken.value;
    const affordance = await waitForVirtualOperationAffordance(operation.targetId, token);
    if (!affordance) {
      throw new Error(`找不到可见页面目标：${operation.targetId}`);
    }
    await moveVirtualCursorToElement(affordance.element);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    affordance.element.focus();
    affordance.element.dispatchEvent(new KeyboardEvent("keydown", { key: operation.key, bubbles: true }));
    affordance.element.dispatchEvent(new KeyboardEvent("keyup", { key: operation.key, bubbles: true }));
  }

  async function executeBuddyVirtualWaitOperation(operation: BuddyVirtualOperation) {
    if (operation.kind !== "wait") {
      return;
    }
    await waitForVirtualOperation(operation.option === "short" ? 300 : 120);
  }

  async function executeBuddyVirtualRunTemplateOperation(operation: BuddyVirtualOperation) {
    if (operation.kind !== "run_template") {
      return;
    }
    const token = activeVirtualOperationToken.value;
    await clickVirtualOperationTargetWithRetry("app.nav.library", token);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    if (!(await waitForRoutePath("/library", token))) {
      throw new Error("页面没有进入目标路径：/library");
    }
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    const searchInput = await waitForVirtualOperationTextInput("library.search.query", token);
    if (!searchInput) {
      throw new Error("找不到图与模板搜索栏。");
    }
    await moveVirtualCursorToElement(searchInput);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    searchInput.focus();
    await replaceVirtualText(searchInput, operation.searchText);
    await waitForVirtualOperation(BUDDY_VIRTUAL_TEMPLATE_SEARCH_SETTLE_MS, token);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    const templateAffordance = await waitForTemplateRunTargetAffordance(operation, token);
    if (!templateAffordance) {
      throw new Error(`找不到目标图模板：${operation.templateName || operation.templateId || operation.searchText}`);
    }
    await moveVirtualCursorToElement(templateAffordance.element);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    dispatchVirtualClick(templateAffordance.element);
    if (!(await waitForRoutePath("/editor", token))) {
      throw new Error("页面没有进入目标路径：/editor");
    }
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    await fillTemplateRunInputNode(operation, token);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    await clickVirtualOperationTargetWithRetry(operation.runTargetId, token);
  }

  async function clickVirtualOperationTargetWithRetry(targetId: string, token: BuddyVirtualOperationToken | null) {
    const affordance = await waitForVirtualOperationAffordance(targetId, token);
    if (!affordance) {
      throw new Error(`找不到可见页面目标：${targetId}`);
    }
    await moveVirtualCursorToElement(affordance.element);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    dispatchVirtualClick(affordance.element);
    await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_CLICK_SETTLE_MS, token);
  }

  async function waitForVirtualOperationAffordance(targetId: string, token: BuddyVirtualOperationToken | null) {
    const startedAt = Date.now();
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS;
    let attempts = 0;
    while (!isVirtualOperationInterrupted(token) && Date.now() <= deadline) {
      attempts += 1;
      const affordance = resolveVirtualOperationAffordance(targetId);
      if (affordance) {
        recordVirtualOperationRetry(token, buildVirtualOperationRetryRecord("affordance", targetId, attempts, "resolved", startedAt));
        return affordance;
      }
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS, token);
      await nextTick();
    }
    const affordance = resolveVirtualOperationAffordance(targetId);
    recordVirtualOperationRetry(
      token,
      buildVirtualOperationRetryRecord(
        "affordance",
        targetId,
        attempts,
        isVirtualOperationInterrupted(token) ? "interrupted" : affordance ? "resolved" : "missing",
        startedAt,
      ),
    );
    return affordance;
  }

  async function waitForVirtualOperationTextInput(targetId: string, token: BuddyVirtualOperationToken | null) {
    const startedAt = Date.now();
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS;
    let attempts = 0;
    while (!isVirtualOperationInterrupted(token) && Date.now() <= deadline) {
      attempts += 1;
      const input = resolveVirtualOperationTextInput(targetId);
      if (input) {
        recordVirtualOperationRetry(token, buildVirtualOperationRetryRecord("text_input", targetId, attempts, "resolved", startedAt));
        return input;
      }
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS, token);
      await nextTick();
    }
    const input = resolveVirtualOperationTextInput(targetId);
    recordVirtualOperationRetry(
      token,
      buildVirtualOperationRetryRecord(
        "text_input",
        targetId,
        attempts,
        isVirtualOperationInterrupted(token) ? "interrupted" : input ? "resolved" : "missing",
        startedAt,
      ),
    );
    return input;
  }

  async function waitForTemplateRunTargetAffordance(operation: BuddyVirtualOperation, token: BuddyVirtualOperationToken | null) {
    if (operation.kind !== "run_template") {
      return null;
    }
    const targetId = operation.targetId || operation.templateId || operation.templateName || operation.searchText || "template";
    const startedAt = Date.now();
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS;
    let attempts = 0;
    while (!isVirtualOperationInterrupted(token) && Date.now() <= deadline) {
      attempts += 1;
      const affordance = resolveTemplateRunTargetAffordance(operation);
      if (affordance) {
        recordVirtualOperationRetry(token, buildVirtualOperationRetryRecord("template_target", targetId, attempts, "resolved", startedAt));
        return affordance;
      }
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS, token);
      await nextTick();
    }
    const affordance = resolveTemplateRunTargetAffordance(operation);
    recordVirtualOperationRetry(
      token,
      buildVirtualOperationRetryRecord(
        "template_target",
        targetId,
        attempts,
        isVirtualOperationInterrupted(token) ? "interrupted" : affordance ? "resolved" : "missing",
        startedAt,
      ),
    );
    return affordance;
  }

  async function fillTemplateRunInputNode(
    operation: Extract<BuddyVirtualOperation, { kind: "run_template" }>,
    token: BuddyVirtualOperationToken | null,
  ) {
    const input = await waitForTemplateRunInputTextInput(token);
    if (!input) {
      throw new Error("找不到可编辑的图模板 input 节点。");
    }
    await moveVirtualCursorToElement(input);
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    dispatchVirtualClick(input);
    input.focus();
    await replaceVirtualText(input, operation.inputText);
    await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_CLICK_SETTLE_MS, token);
  }

  async function waitForTemplateRunInputTextInput(token: BuddyVirtualOperationToken | null) {
    const startedAt = Date.now();
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS;
    let attempts = 0;
    while (!isVirtualOperationInterrupted(token) && Date.now() <= deadline) {
      attempts += 1;
      const input = resolveTemplateRunInputTextInput();
      if (input) {
        recordVirtualOperationRetry(token, buildVirtualOperationRetryRecord("template_input", "editor.template.input", attempts, "resolved", startedAt));
        return input;
      }
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS, token);
      await nextTick();
    }
    const input = resolveTemplateRunInputTextInput();
    recordVirtualOperationRetry(
      token,
      buildVirtualOperationRetryRecord(
        "template_input",
        "editor.template.input",
        attempts,
        isVirtualOperationInterrupted(token) ? "interrupted" : input ? "resolved" : "missing",
        startedAt,
      ),
    );
    return input;
  }

  async function waitForRoutePath(expectedPath: string, token: BuddyVirtualOperationToken | null) {
    const startedAt = Date.now();
    const deadline = Date.now() + BUDDY_VIRTUAL_OPERATION_TARGET_WAIT_MS;
    let attempts = 0;
    while (!isVirtualOperationInterrupted(token) && Date.now() <= deadline) {
      attempts += 1;
      await nextTick();
      if (routeMatchesVirtualOperationTargetPath(routePath.value, expectedPath)) {
        recordVirtualOperationRetry(token, buildVirtualOperationRetryRecord("route", expectedPath, attempts, "resolved", startedAt));
        return true;
      }
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TARGET_RETRY_MS, token);
    }
    const matched = routeMatchesVirtualOperationTargetPath(routePath.value, expectedPath);
    recordVirtualOperationRetry(
      token,
      buildVirtualOperationRetryRecord(
        "route",
        expectedPath,
        attempts,
        isVirtualOperationInterrupted(token) ? "interrupted" : matched ? "resolved" : "missing",
        startedAt,
      ),
    );
    return matched;
  }

  async function typeVirtualText(element: HTMLInputElement | HTMLTextAreaElement, text: string) {
    for (const character of text) {
      if (isVirtualOperationInterrupted(activeVirtualOperationToken.value)) {
        break;
      }
      element.value = `${element.value}${character}`;
      dispatchVirtualInputEvents(element, "insertText", character);
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TYPE_CHARACTER_DELAY_MS);
    }
  }

  return {
    executeVirtualOperationRequest,
    handleBuddyVirtualUiOperationEvent,
    interruptVirtualOperation,
  };
}

function templateMatchesVirtualRunTarget(template: TemplateRecord, expectedTexts: string[]) {
  if (expectedTexts.length === 0) {
    return false;
  }
  const haystack = normalizeTemplateRunMatchText(
    `${template.template_id} ${template.label} ${template.default_graph_name} ${template.description}`,
  );
  return expectedTexts.some((text) => haystack.includes(text));
}
