import type { Ref } from "vue";

import type { RunDetail } from "../types/run.ts";
import { buildBuddyPageContext, type BuddyEditorContextSnapshot } from "./buddyPageContext.ts";
import {
  buildPageOperationRuntimeContext as buildPageOperationActionRuntimeContext,
  collectPageOperationSnapshot,
  type PageOperationEditorFactInput,
} from "./pageOperationAffordances.ts";

export type BuddyPageOperationForegroundRun = {
  runId: string;
  status: string;
  resultSummary: string;
};

export type BuddyPageOperationRuntimeContextOptions = {
  latestOperationReport?: Record<string, unknown> | null;
  latestForegroundRun?: BuddyPageOperationForegroundRun | null;
};

type BuddyTriggeredRunFactInput = {
  runId: string;
  initialStatus: string;
};

type BuddyPageOperationContextOptions = {
  routePath: Ref<string>;
  activeRunId: Ref<string | null>;
  getEditorSnapshot: () => BuddyEditorContextSnapshot | null;
  getRoot?: () => ParentNode | null;
};

export function useBuddyPageOperationContext({
  routePath,
  activeRunId,
  getEditorSnapshot,
  getRoot = () => (typeof document === "undefined" ? null : document),
}: BuddyPageOperationContextOptions) {
  function buildPageOperationRuntimeContext(options: BuddyPageOperationRuntimeContextOptions = {}) {
    const root = getRoot();
    const snapshot = collectPageOperationSnapshot({
      routePath: routePath.value,
      root,
    });
    const editorSnapshot = getEditorSnapshot();
    const actionRuntimeContext = buildPageOperationActionRuntimeContext({
      routePath: routePath.value,
      root,
      snapshot,
      editor: buildBuddyPageOperationEditorFacts(editorSnapshot),
      latestForegroundRun: options.latestForegroundRun ?? null,
      latestOperationReport: options.latestOperationReport ?? null,
    });
    return {
      pageContext: buildBuddyPageContext({
        routePath: routePath.value,
        editor: editorSnapshot,
        activeBuddyRunId: activeRunId.value,
        pageOperationBook: actionRuntimeContext.page_operation_book,
        pageFacts: actionRuntimeContext.page_facts,
      }),
      actionRuntimeContext,
    };
  }

  return {
    buildPageOperationRuntimeContext,
    buildTriggeredForegroundRunFact,
    compactPageFactText,
  };
}

function buildBuddyPageOperationEditorFacts(editor: BuddyEditorContextSnapshot | null): PageOperationEditorFactInput | null {
  if (!editor) {
    return null;
  }
  const documentName = editor.document?.name ?? "";
  const documentGraphId = editor.document && "graph_id" in editor.document ? editor.document.graph_id ?? "" : "";
  return {
    activeTabId: editor.activeTabId,
    activeTabTitle: editor.activeTabTitle,
    activeTabKind: editor.activeTabKind,
    activeGraphId: editor.activeGraphId ?? documentGraphId,
    activeGraphName: editor.activeGraphName ?? documentName ?? editor.activeTabTitle,
    activeGraphDirty: editor.activeGraphDirty === true,
  };
}

function buildTriggeredForegroundRunFact(
  triggeredRun: BuddyTriggeredRunFactInput | null,
  runDetail: RunDetail | null,
): BuddyPageOperationForegroundRun | null {
  if (runDetail) {
    return {
      runId: runDetail.run_id,
      status: runDetail.status,
      resultSummary: compactPageFactText(runDetail.final_result),
    };
  }
  if (!triggeredRun) {
    return null;
  }
  return {
    runId: triggeredRun.runId,
    status: triggeredRun.initialStatus,
    resultSummary: "",
  };
}

function compactPageFactText(value: unknown) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}
