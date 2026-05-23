import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";

import type { GraphPayload } from "../types/node-system.ts";
import type { RunDetail } from "../types/run.ts";
import { buildBuddyPublicOutputBindings } from "./buddyPublicOutput.ts";
import { buildPublicOutputRuntimeStateFromRunDetail } from "./useBuddyRunDisplayMessages.ts";
import { useBuddyRunDisplayMessages } from "./useBuddyRunDisplayMessages.ts";

function outputTimelineGraph(): GraphPayload {
  return {
    graph_id: null,
    name: "Buddy",
    state_schema: {
      answer: { name: "answer", description: "", type: "markdown", value: "", color: "#000" },
    },
    nodes: {
      gate: {
        kind: "condition",
        name: "Needs capability?",
        description: "",
        reads: [{ state: "answer", required: true }],
        writes: [],
        config: { branches: ["true", "false"], loopLimit: 5, branchMapping: {}, rule: null },
        ui: { position: { x: 0, y: 0 } },
      },
      output_answer: {
        kind: "output",
        name: "Answer",
        description: "",
        reads: [{ state: "answer", required: true }],
        writes: [],
        config: { displayMode: "markdown", persistEnabled: false, persistFormat: "auto", fileNameTemplate: "" },
        ui: { position: { x: 0, y: 0 } },
      },
    },
    edges: [],
    conditional_edges: [{ source: "gate", branches: { false: "output_answer" } }],
    metadata: {},
  };
}

test("buildPublicOutputRuntimeStateFromRunDetail uses reached output previews instead of raw state events", () => {
  const graph = outputTimelineGraph();
  const bindings = buildBuddyPublicOutputBindings(graph);
  const run = {
    status: "completed",
    output_previews: [
      {
        node_id: "output_answer",
        source_kind: "state",
        source_key: "answer",
        display_mode: "markdown",
        persist_enabled: false,
        persist_format: "auto",
        value: "final",
      },
    ],
    artifacts: {
      state_events: [
        {
          node_id: "writer",
          state_key: "answer",
          output_key: "answer",
          value: "progress",
          sequence: 1,
          created_at: "2026-05-24T03:14:04.000Z",
        },
        {
          node_id: "writer",
          state_key: "answer",
          output_key: "answer",
          value: "final",
          sequence: 2,
          created_at: "2026-05-24T03:14:41.000Z",
        },
      ],
    },
    node_executions: [],
  } as Partial<RunDetail> as RunDetail;

  const state = buildPublicOutputRuntimeStateFromRunDetail(run, bindings, graph);

  assert.deepEqual(state.order, ["output_answer"]);
  assert.equal(state.messagesByOutputNodeId.output_answer.content, "final");
  assert.equal(state.messagesByOutputNodeId["output_answer:2"], undefined);
});

type DisplayTestMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  clientOrder?: number | null;
  includeInContext?: boolean;
  runId?: string | null;
  activityText?: string;
  publicOutput?: unknown;
  outputTrace?: unknown;
};

function createDisplayHarness() {
  const messages = ref<DisplayTestMessage[]>([
    { id: "controller", role: "assistant", content: "", clientOrder: 0 },
  ]);
  let nextOrder = 1;
  const display = useBuddyRunDisplayMessages<DisplayTestMessage>({
    messages,
    mood: ref("thinking"),
    t: (key) => key,
    createMessage: (role, content, id, clientOrder) => ({ id: id ?? `message_${nextOrder}`, role, content, clientOrder }),
    allocateBuddyMessageClientOrder: () => nextOrder++,
    scrollMessagesToBottom: async () => {},
    clearAutoResumingPageOperationPlaceholder: () => {},
  });
  return { display, messages };
}

function repeatedLoopTraceState() {
  return {
    order: ["segment_1", "segment_2"],
    activeSegmentId: "segment_2",
    nextSegmentIndex: 1,
    segmentsById: {
      segment_1: {
        segmentId: "segment_1",
        boundaryNodeId: "gate",
        boundaryLabel: "Gate",
        outputNodeIds: ["output_answer"],
        status: "completed",
        startedAtMs: 1000,
        completedAtMs: 2000,
        durationMs: 1000,
        records: [],
      },
      segment_2: {
        segmentId: "segment_2",
        boundaryNodeId: "gate",
        boundaryLabel: "Gate",
        outputNodeIds: ["output_answer"],
        status: "running",
        startedAtMs: 3000,
        completedAtMs: null,
        durationMs: null,
        records: [],
      },
    },
  } as const;
}

function completedOutput(outputNodeId: string, content: string) {
  return {
    outputNodeId,
    sourceOutputNodeId: "output_answer",
    outputNodeName: "Answer",
    stateKey: "answer",
    stateName: "answer",
    stateType: "markdown",
    displayMode: "markdown",
    kind: "text" as const,
    content,
    startedAtMs: null,
    durationMs: null,
    status: "completed" as const,
  };
}

test("syncBuddyRunDisplayMessages does not attach a previous output to a later loop capsule", () => {
  const { display, messages } = createDisplayHarness();

  display.syncBuddyRunDisplayMessages(
    "controller",
    "run_1",
    repeatedLoopTraceState(),
    {
      order: ["output_answer"],
      startedAtByOutputNodeId: {},
      messagesByOutputNodeId: {
        output_answer: completedOutput("output_answer", "progress"),
      },
    },
  );

  assert.deepEqual(
    messages.value.map((message) => message.id),
    ["controller", "controller:trace:segment_1", "controller:output:output_answer", "controller:trace:segment_2"],
  );
});

test("syncBuddyRunDisplayMessages attaches the next repeated output to the next loop capsule", () => {
  const { display, messages } = createDisplayHarness();

  display.syncBuddyRunDisplayMessages(
    "controller",
    "run_1",
    repeatedLoopTraceState(),
    {
      order: ["output_answer", "output_answer:2"],
      startedAtByOutputNodeId: {},
      messagesByOutputNodeId: {
        output_answer: completedOutput("output_answer", "progress"),
        "output_answer:2": completedOutput("output_answer:2", "final"),
      },
    },
  );

  assert.deepEqual(
    messages.value.map((message) => message.id),
    [
      "controller",
      "controller:trace:segment_1",
      "controller:output:output_answer",
      "controller:trace:segment_2",
      "controller:output:output_answer:2",
    ],
  );
});
