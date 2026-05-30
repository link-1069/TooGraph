import test from "node:test";
import assert from "node:assert/strict";

import type { ModelLogEntry, ModelLogTreeNode } from "@/types/model-log";

import { buildModelLogTreeItems, collectExpandableModelLogTreeKeys } from "./modelLogsTreeModel.ts";

function treeNode(overrides: Partial<ModelLogTreeNode>): ModelLogTreeNode {
  return {
    kind: "graph_node",
    id: "node:root",
    run_id: "run-root",
    label: "Root node",
    model_log_ids: [],
    children: [],
    ...overrides,
  };
}

function modelLog(id: string, overrides: Partial<ModelLogEntry> = {}): ModelLogEntry {
  return {
    id,
    timestamp: "2026-05-30T00:00:00Z",
    duration_ms: 12,
    provider_id: "openai-codex",
    transport: "codex-responses",
    model: "gpt-5.3-codex",
    path: "/responses",
    request_kind: "chat",
    messages: [],
    reasoning: "",
    content: "",
    request_raw: {},
    response_raw: {},
    ...overrides,
  };
}

test("buildModelLogTreeItems hides child logs and descendants under collapsed nodes", () => {
  const child = treeNode({ id: "node:child", label: "Child node", model_log_ids: ["log-child"] });
  const root = treeNode({
    id: "run:root",
    kind: "run",
    label: "Root run",
    model_log_ids: ["log-root"],
    children: [child],
  });
  const logIndex = new Map([
    ["log-root", modelLog("log-root")],
    ["log-child", modelLog("log-child")],
  ]);

  const collapsedItems = buildModelLogTreeItems([root], logIndex, new Set());
  assert.deepEqual(collapsedItems.map((item) => item.key), ["run:root"]);
  assert.equal(collapsedItems[0]?.hasChildren, true);
  assert.equal(collapsedItems[0]?.expanded, false);

  const expandedItems = buildModelLogTreeItems([root], logIndex, new Set(["run:root"]));
  assert.deepEqual(expandedItems.map((item) => item.key), [
    "run:root",
    "model:log-root",
    "node:child:path:run:root.0",
  ]);
  assert.equal(expandedItems[0]?.expanded, true);
  assert.equal(expandedItems[1]?.kind, "model_call");
});

test("buildModelLogTreeItems groups repeated capability loop nodes under collapsed rounds", () => {
  const replyOne = treeNode({
    id: "node:loop:reply_and_select_capability",
    execution_id: "reply-1",
    node_id: "reply_and_select_capability",
    label: "reply_and_select_capability",
    model_log_ids: ["log-reply-1"],
  });
  const executeOne = treeNode({
    id: "node:loop:execute_capability",
    execution_id: "execute-1",
    node_id: "execute_capability",
    label: "execute_capability",
    model_log_ids: ["log-execute-1"],
    children: [treeNode({ id: "node:subgraph", label: "Search subgraph", model_log_ids: ["log-subgraph"] })],
  });
  const replyTwo = treeNode({
    id: "node:loop:reply_and_select_capability",
    execution_id: "reply-2",
    node_id: "reply_and_select_capability",
    label: "reply_and_select_capability",
    model_log_ids: ["log-reply-2"],
  });
  const executeTwo = treeNode({
    id: "node:loop:execute_capability",
    execution_id: "execute-2",
    node_id: "execute_capability",
    label: "execute_capability",
    model_log_ids: ["log-execute-2"],
  });
  const root = treeNode({
    id: "run:root",
    kind: "run",
    label: "Root run",
    children: [replyOne, executeOne, replyTwo, executeTwo],
  });
  const logIndex = new Map<string, ModelLogEntry>(
    ["log-reply-1", "log-execute-1", "log-subgraph", "log-reply-2", "log-execute-2"].map((id) => [id, modelLog(id)] as [
      string,
      ModelLogEntry,
    ]),
  );

  const rootExpandedItems = buildModelLogTreeItems([root], logIndex, new Set(["run:root"]));
  assert.deepEqual(
    rootExpandedItems.map((item) => item.kind),
    ["run", "loop_group", "loop_group"],
  );
  assert.deepEqual(
    rootExpandedItems.map((item) => item.key),
    [
      "run:root",
      "loop:run:root:1:reply-1:execute-1",
      "loop:run:root:2:reply-2:execute-2",
    ],
  );
  assert.equal(rootExpandedItems[1]?.expanded, false);
  assert.equal(rootExpandedItems[1]?.loopIndex, 1);
  assert.deepEqual(rootExpandedItems[1]?.logIds, ["log-reply-1", "log-execute-1"]);

  const firstLoopExpandedItems = buildModelLogTreeItems(
    [root],
    logIndex,
    new Set(["run:root", "loop:run:root:1:reply-1:execute-1"]),
  );
  assert.deepEqual(
    firstLoopExpandedItems.map((item) => item.key),
    [
      "run:root",
      "loop:run:root:1:reply-1:execute-1",
      "node:loop:reply_and_select_capability:exec:reply-1",
      "node:loop:execute_capability:exec:execute-1",
      "loop:run:root:2:reply-2:execute-2",
    ],
  );
  assert.deepEqual(firstLoopExpandedItems[3]?.logIds, ["log-execute-1", "log-subgraph"]);

  const expandableKeys = collectExpandableModelLogTreeKeys([root]);
  assert.equal(expandableKeys.has("loop:run:root:1:reply-1:execute-1"), true);
  assert.equal(expandableKeys.has("node:loop:execute_capability:exec:execute-1"), true);
});

test("buildModelLogTreeItems keeps duplicate graph node ids independently expandable", () => {
  const duplicateOne = treeNode({
    id: "node:run:execute_capability",
    execution_id: "execute-1",
    node_id: "execute_capability",
    label: "execute_capability",
    model_log_ids: ["log-1"],
  });
  const duplicateTwo = treeNode({
    id: "node:run:execute_capability",
    execution_id: "execute-2",
    node_id: "execute_capability",
    label: "execute_capability",
    model_log_ids: ["log-2"],
  });
  const root = treeNode({
    id: "run:root",
    kind: "run",
    label: "Root run",
    children: [duplicateOne, duplicateTwo],
  });
  const logIndex = new Map([
    ["log-1", modelLog("log-1")],
    ["log-2", modelLog("log-2")],
  ]);

  const items = buildModelLogTreeItems([root], logIndex, new Set(["run:root"]));
  assert.deepEqual(
    items.map((item) => item.key),
    ["run:root", "node:run:execute_capability:exec:execute-1", "node:run:execute_capability:exec:execute-2"],
  );
});

test("collectExpandableModelLogTreeKeys includes nodes that can reveal logs or child nodes", () => {
  const root = treeNode({
    id: "run:root",
    kind: "run",
    model_log_ids: [],
    children: [
      treeNode({ id: "node:empty", model_log_ids: [], children: [] }),
      treeNode({ id: "node:with-log", model_log_ids: ["log-1"], children: [] }),
    ],
  });

  assert.deepEqual([...collectExpandableModelLogTreeKeys([root])].sort(), ["node:with-log:path:run:root.1", "run:root"]);
});
