import assert from "node:assert/strict";
import test from "node:test";

import type { BuddyOutputTraceSegment } from "./buddyOutputTrace.ts";
import type { RunDetail, RunTreeNode } from "../types/run.ts";
import { buildBuddyOutputTraceTreeRows } from "./buddyOutputTraceTree.ts";

const baseRecord = {
  kind: "node" as const,
  status: "completed" as const,
  startedAtMs: 1000,
  completedAtMs: 1200,
  durationMs: 200,
  nodeType: "agent",
};

function createRunTreeNode(overrides: Partial<RunTreeNode> & Pick<RunTreeNode, "run_id">): RunTreeNode {
  return {
    run_id: overrides.run_id,
    graph_id: overrides.graph_id ?? "graph_1",
    graph_name: overrides.graph_name ?? "Run",
    status: overrides.status ?? "completed",
    runtime_backend: "langgraph",
    lifecycle: {
      updated_at: "2026-04-18T00:00:00Z",
      resume_count: 0,
    },
    checkpoint_metadata: {
      available: false,
    },
    revision_round: 0,
    started_at: "2026-04-18T00:00:00Z",
    current_node_id: overrides.current_node_id ?? null,
    final_result: overrides.final_result ?? "",
    parent_run_id: overrides.parent_run_id ?? "",
    root_run_id: overrides.root_run_id ?? overrides.run_id,
    parent_node_id: overrides.parent_node_id ?? "",
    invocation_kind: overrides.invocation_kind ?? "",
    invocation_key: overrides.invocation_key ?? "",
    run_depth: overrides.run_depth ?? 0,
    run_path: overrides.run_path ?? [overrides.run_id],
    batch_group_id: overrides.batch_group_id ?? "",
    batch_item_index: overrides.batch_item_index ?? null,
    batch_item_label: overrides.batch_item_label ?? "",
    children: overrides.children ?? [],
    duration_ms: overrides.duration_ms ?? null,
  };
}

test("buildBuddyOutputTraceTreeRows renders main and subgraph records as an indented tree", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "主图输出",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2400,
    durationMs: 1400,
    records: [
      {
        ...baseRecord,
        recordId: "record_a",
        runtimeKey: "node:main_a",
        label: "主图节点 A",
        nodeId: "main_a",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        recordId: "record_subgraph",
        runtimeKey: "node:subgraph_a",
        label: "子图 A",
        nodeId: "subgraph_a",
        nodeType: "subgraph",
        subgraphNodeId: null,
        aggregateSubgraphNodeId: "subgraph_a",
      },
      {
        ...baseRecord,
        recordId: "record_inner_1",
        runtimeKey: "node:subgraph_a/inner_1",
        label: "子图 A / 子图节点 1",
        nodeId: "inner_1",
        subgraphNodeId: "subgraph_a",
      },
      {
        ...baseRecord,
        recordId: "record_inner_2",
        runtimeKey: "node:subgraph_a/inner_2",
        label: "子图 A / 子图节点 2",
        nodeId: "inner_2",
        subgraphNodeId: "subgraph_a",
      },
      {
        ...baseRecord,
        recordId: "record_b",
        runtimeKey: "node:main_b",
        label: "主图节点 B",
        nodeId: "main_b",
        subgraphNodeId: null,
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始" });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind, evidenceRunId: row.evidenceRunId })),
    [
      { label: "主图节点 A", depth: 0, kind: "node", evidenceRunId: null },
      { label: "子图 A", depth: 0, kind: "subgraph", evidenceRunId: null },
      { label: "子图节点 1", depth: 1, kind: "node", evidenceRunId: null },
      { label: "子图节点 2", depth: 1, kind: "node", evidenceRunId: null },
      { label: "主图节点 B", depth: 0, kind: "node", evidenceRunId: null },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows exposes activity evidence labels", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "主图输出",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 1300,
    durationMs: 300,
    records: [
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_activity",
        runtimeKey: "activity:1:main_a",
        label: "A / Virtual template run",
        nodeId: "main_a",
        nodeType: "activity",
        subgraphNodeId: null,
        artifactLabels: ["artifacts: 2", "retries: 5"],
        triggeredRunId: "run_report",
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始" });

  assert.deepEqual(rows[0].artifactLabels, ["artifacts: 2", "retries: 5"]);
  assert.equal(rows[0].evidenceRunId, "run_report");
});

test("buildBuddyOutputTraceTreeRows nests activity rows under their owning node", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "Final",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 1800,
    durationMs: 800,
    records: [
      {
        ...baseRecord,
        recordId: "record_agent",
        runtimeKey: "node:agent_a",
        label: "Agent A",
        nodeId: "agent_a",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_activity",
        runtimeKey: "activity:1:agent_a",
        label: "Agent A / web_search",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "Main graph" });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind })),
    [
      { label: "Agent A", depth: 0, kind: "node" },
      { label: "web_search", depth: 1, kind: "activity" },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows nests raw activity rows under their invocation parent", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "Final",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2200,
    durationMs: 1200,
    records: [
      {
        ...baseRecord,
        recordId: "record_agent",
        runtimeKey: "node:agent_a",
        label: "Agent A",
        nodeId: "agent_a",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_invocation",
        runtimeKey: "activity:1:agent_a",
        label: "Agent A / web_search",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityId: "activity_0002",
        invocationId: "activity_0002",
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_search",
        runtimeKey: "activity:2:agent_a",
        label: "Agent A / web_search",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityId: "activity_0003",
        parentActivityId: "activity_0002",
        invocationId: "activity_0002",
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_download",
        runtimeKey: "activity:3:agent_a",
        label: "Agent A / web_download",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityId: "activity_0004",
        parentActivityId: "activity_0002",
        invocationId: "activity_0002",
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "Main graph" });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind })),
    [
      { label: "Agent A", depth: 0, kind: "node" },
      { label: "web_search", depth: 1, kind: "activity" },
      { label: "web_search", depth: 2, kind: "activity" },
      { label: "web_download", depth: 2, kind: "activity" },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows groups legacy raw activity rows by capability key", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "Final",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2200,
    durationMs: 1200,
    records: [
      {
        ...baseRecord,
        recordId: "record_agent",
        runtimeKey: "node:agent_a",
        label: "Agent A",
        nodeId: "agent_a",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_invocation",
        runtimeKey: "activity:1:agent_a",
        label: "Agent A / web_search",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityKind: "action_invocation",
        capabilityKey: "web_search",
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_search",
        runtimeKey: "activity:2:agent_a",
        label: "Agent A / web_search",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityKind: "web_search",
        capabilityKey: "web_search",
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_download",
        runtimeKey: "activity:3:agent_a",
        label: "Agent A / web_download",
        nodeId: "agent_a",
        nodeType: "activity",
        subgraphNodeId: null,
        activityKind: "web_download",
        capabilityKey: "web_search",
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "Main graph" });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind })),
    [
      { label: "Agent A", depth: 0, kind: "node" },
      { label: "web_search", depth: 1, kind: "activity" },
      { label: "web_search", depth: 2, kind: "activity" },
      { label: "web_download", depth: 2, kind: "activity" },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows hides internal child run artifact labels", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "主图输出",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 1400,
    durationMs: 400,
    records: [
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_subgraph",
        runtimeKey: "activity:subgraph:dynamic_capability:run_research",
        label: "动态能力 / 高级联网搜索",
        nodeId: "dynamic_capability",
        nodeType: "activity",
        subgraphNodeId: null,
        treeDepth: 1,
        artifactLabels: ["run: run_research completed"],
        triggeredRunId: "run_research",
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始" });

  assert.deepEqual(rows[0].artifactLabels, []);
  assert.equal(rows[0].evidenceRunId, "run_research");
});

test("buildBuddyOutputTraceTreeRows renders dynamic capability traces like a file tree", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "最终回复",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2400,
    durationMs: 1400,
    records: [
      {
        ...baseRecord,
        recordId: "record_dynamic",
        runtimeKey: "node:dynamic_capability",
        label: "动态能力",
        nodeId: "dynamic_capability",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_ability",
        runtimeKey: "activity:1:dynamic_capability",
        label: "动态能力 / 高级联网搜索",
        nodeId: "dynamic_capability",
        nodeType: "activity",
        subgraphNodeId: null,
        treeDepth: 1,
        triggeredRunId: "run_research",
      },
      {
        ...baseRecord,
        recordId: "record_child_1",
        runtimeKey: "node:dynamic_capability/advanced_web_research_loop/plan_search",
        label: "动态能力 / 高级联网搜索 / 规划搜索",
        nodeId: "plan_search",
        subgraphNodeId: null,
        treeDepth: 2,
      },
      {
        ...baseRecord,
        recordId: "record_child_2",
        runtimeKey: "node:dynamic_capability/advanced_web_research_loop/summarize_results",
        label: "动态能力 / 高级联网搜索 / 整理结果",
        nodeId: "summarize_results",
        subgraphNodeId: null,
        treeDepth: 2,
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始" });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind, evidenceRunId: row.evidenceRunId })),
    [
      { label: "动态能力", depth: 0, kind: "node", evidenceRunId: null },
      { label: "高级联网搜索", depth: 1, kind: "subgraph", evidenceRunId: "run_research" },
      { label: "规划搜索", depth: 2, kind: "node", evidenceRunId: null },
      { label: "整理结果", depth: 2, kind: "node", evidenceRunId: null },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows resolves dynamic subgraph child node names from child run detail", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "最终回复",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2400,
    durationMs: 1400,
    records: [
      {
        ...baseRecord,
        recordId: "record_child_1",
        runtimeKey: "node:dynamic_capability/advanced_web_research_loop/plan_search",
        label: "动态能力 / 高级联网搜索 / plan search",
        nodeId: "plan_search",
        subgraphNodeId: null,
        treeDepth: 2,
        dynamicCapabilityRunId: "run_research",
      },
    ],
  };
  const childRun = {
    graph_snapshot: {
      nodes: {
        plan_search: {
          name: "制定搜索计划",
          description: "",
          kind: "agent",
        },
      },
    },
  } as Partial<RunDetail> as RunDetail;

  const rows = buildBuddyOutputTraceTreeRows(segment, {
    rootLabel: "主图开始",
    childRunDetailsByRunId: { run_research: childRun },
  });

  assert.equal(rows[0].label, "制定搜索计划");
});

test("buildBuddyOutputTraceTreeRows upgrades stored dynamic capability activity rows from run evidence", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "最终回复",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2400,
    durationMs: 1400,
    records: [
      {
        ...baseRecord,
        recordId: "record_dynamic",
        runtimeKey: "node:dynamic_capability",
        label: "动态能力",
        nodeId: "dynamic_capability",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_ability",
        runtimeKey: "activity:2:dynamic_capability",
        label: "动态能力 / advanced_web_research_loop",
        nodeId: "dynamic_capability",
        nodeType: "activity",
        subgraphNodeId: null,
        triggeredRunId: "run_research",
      },
    ],
  };
  const runTree = createRunTreeNode({
    run_id: "run_parent",
    graph_name: "Buddy Loop",
    children: [
      createRunTreeNode({
        run_id: "run_research",
        graph_name: "高级联网搜索",
        parent_run_id: "run_parent",
        parent_node_id: "dynamic_capability",
        invocation_kind: "dynamic_subgraph_capability",
        invocation_key: "advanced_web_research_loop",
      }),
    ],
  });
  const childRun = {
    graph_snapshot: {
      nodes: {
        plan_search: { name: "制定搜索计划", description: "", kind: "agent" },
        output_final: { name: "最终回复", description: "", kind: "output" },
      },
    },
    node_executions: [
      {
        node_id: "plan_search",
        node_type: "agent",
        status: "success",
        started_at: "2026-05-13T10:00:00.100Z",
        finished_at: "2026-05-13T10:00:00.300Z",
        duration_ms: 200,
        input_summary: "",
        output_summary: "",
        artifacts: { inputs: {}, outputs: {}, family: "agent", state_reads: [], state_writes: [] },
        warnings: [],
        errors: [],
      },
      {
        node_id: "output_final",
        node_type: "output",
        status: "success",
        started_at: "2026-05-13T10:00:00.350Z",
        finished_at: "2026-05-13T10:00:00.350Z",
        duration_ms: 0,
        input_summary: "",
        output_summary: "",
        artifacts: { inputs: {}, outputs: {}, family: "output", state_reads: [], state_writes: [] },
        warnings: [],
        errors: [],
      },
    ],
  } as Partial<RunDetail> as RunDetail;

  const rows = buildBuddyOutputTraceTreeRows(segment, {
    rootLabel: "主图开始",
    runTree,
    childRunDetailsByRunId: { run_research: childRun },
  });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind, evidenceRunId: row.evidenceRunId })),
    [
      { label: "动态能力", depth: 0, kind: "node", evidenceRunId: null },
      { label: "高级联网搜索", depth: 1, kind: "subgraph", evidenceRunId: "run_research" },
      { label: "制定搜索计划", depth: 2, kind: "node", evidenceRunId: null },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows exposes graph revision restore metadata", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "主图输出",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 1300,
    durationMs: 300,
    records: [
      {
        ...baseRecord,
        kind: "activity",
        recordId: "record_activity",
        runtimeKey: "activity:1:main_a",
        label: "A / Virtual graph edit",
        nodeId: "main_a",
        nodeType: "activity",
        subgraphNodeId: null,
        artifactLabels: ["graph revision: grev_buddy"],
        graphRevision: {
          graphId: "graph_buddy",
          revisionId: "grev_buddy",
          status: "saved",
        },
      },
    ],
  };

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始" });

  assert.deepEqual(rows[0].graphRevision, {
    graphId: "graph_buddy",
    revisionId: "grev_buddy",
    status: "saved",
  });
});

test("buildBuddyOutputTraceTreeRows keeps segment rows when a fetched run tree exists", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:final",
    boundaryNodeId: "final",
    boundaryLabel: "主图输出",
    outputNodeIds: ["output_final"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2400,
    durationMs: 1400,
    records: [
      {
        ...baseRecord,
        recordId: "record_fallback",
        runtimeKey: "node:fallback",
        label: "局部 fallback",
        nodeId: "fallback",
        subgraphNodeId: null,
      },
    ],
  };
  const runTree = createRunTreeNode({
    run_id: "run_parent",
    graph_name: "Buddy Loop",
    status: "completed",
    children: [
      createRunTreeNode({
        run_id: "run_child",
        graph_name: "Research",
        parent_run_id: "run_parent",
        parent_node_id: "execute_capability",
        invocation_kind: "dynamic_subgraph_capability",
        invocation_key: "advanced_web_research_loop",
      }),
      createRunTreeNode({
        run_id: "run_item_a",
        graph_name: "Batch worker",
        parent_run_id: "run_parent",
        parent_node_id: "batch_news",
        invocation_kind: "batch_subgraph_worker",
        invocation_key: "summarize_article",
        batch_group_id: "batch_news",
        batch_item_index: 0,
        batch_item_label: "article-a",
        status: "completed",
      }),
      createRunTreeNode({
        run_id: "run_item_b",
        graph_name: "Batch worker",
        parent_run_id: "run_parent",
        parent_node_id: "batch_news",
        invocation_kind: "batch_subgraph_worker",
        invocation_key: "summarize_article",
        batch_group_id: "batch_news",
        batch_item_index: 1,
        batch_item_label: "article-b",
        status: "failed",
      }),
    ],
  });

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始", runTree });

  assert.deepEqual(
    rows.map((row) => ({
      kind: row.kind,
      label: row.label,
      depth: row.depth,
      status: row.status,
      evidenceRunId: row.evidenceRunId,
      artifactLabels: row.artifactLabels,
    })),
    [
      {
        kind: "node",
        label: "局部 fallback",
        depth: 0,
        status: "completed",
        evidenceRunId: null,
        artifactLabels: [],
      },
    ],
  );
});

test("buildBuddyOutputTraceTreeRows enriches subgraph segment rows with child run links", () => {
  const segment: BuddyOutputTraceSegment = {
    segmentId: "boundary:node_c",
    boundaryNodeId: "node_c",
    boundaryLabel: "C",
    outputNodeIds: ["output_c"],
    status: "completed",
    startedAtMs: 1000,
    completedAtMs: 2500,
    durationMs: 1500,
    records: [
      {
        ...baseRecord,
        recordId: "record_a",
        runtimeKey: "node:node_a",
        label: "A",
        nodeId: "node_a",
        subgraphNodeId: null,
      },
      {
        ...baseRecord,
        recordId: "record_c",
        runtimeKey: "node:node_c",
        label: "C",
        nodeId: "node_c",
        nodeType: "subgraph",
        subgraphNodeId: null,
        aggregateSubgraphNodeId: "node_c",
        durationMs: 900,
      },
      {
        ...baseRecord,
        recordId: "record_inner_1",
        runtimeKey: "node:node_c/inner_1",
        label: "C / 子节点 1",
        nodeId: "inner_1",
        subgraphNodeId: "node_c",
      },
    ],
  };
  const runTree = createRunTreeNode({
    run_id: "run_parent",
    graph_name: "Buddy Loop",
    children: [
      createRunTreeNode({
        run_id: "run_child_c",
        graph_name: "C Child Run",
        parent_run_id: "run_parent",
        parent_node_id: "node_c",
        invocation_kind: "subgraph_node",
        invocation_key: "embedded:C",
      }),
      createRunTreeNode({
        run_id: "run_unrelated_f",
        graph_name: "F Child Run",
        parent_run_id: "run_parent",
        parent_node_id: "node_f",
        invocation_kind: "subgraph_node",
        invocation_key: "embedded:F",
      }),
    ],
  });

  const rows = buildBuddyOutputTraceTreeRows(segment, { rootLabel: "主图开始", runTree });

  assert.deepEqual(
    rows.map((row) => ({ label: row.label, depth: row.depth, kind: row.kind, evidenceRunId: row.evidenceRunId, playbackTarget: row.playbackTarget })),
    [
      { label: "A", depth: 0, kind: "node", evidenceRunId: null, playbackTarget: null },
      { label: "C", depth: 0, kind: "subgraph", evidenceRunId: "run_child_c", playbackTarget: null },
      { label: "子节点 1", depth: 1, kind: "node", evidenceRunId: null, playbackTarget: null },
    ],
  );
});
