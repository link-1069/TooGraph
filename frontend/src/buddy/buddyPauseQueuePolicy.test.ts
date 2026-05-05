import test from "node:test";
import assert from "node:assert/strict";

import {
  resolveBuddyComposerDecision,
  resolveInitialBuddyPauseActionMode,
  shouldHoldBuddyQueueDrain,
} from "./buddyPauseQueuePolicy.ts";

test("resolveBuddyComposerDecision enqueues a new turn when no run is paused", () => {
  assert.deepEqual(
    resolveBuddyComposerDecision({
      draftText: "  帮我继续推进  ",
      hasPausedRun: false,
      isResumeBusy: false,
    }),
    { kind: "enqueue_new_turn", userMessage: "帮我继续推进" },
  );
});

test("resolveBuddyComposerDecision treats paused runs as background work and enqueues a new turn", () => {
  assert.deepEqual(
    resolveBuddyComposerDecision({
      draftText: "这是一条新的用户消息",
      hasPausedRun: true,
      isResumeBusy: false,
    }),
    { kind: "enqueue_new_turn", userMessage: "这是一条新的用户消息" },
  );
});

test("resolveBuddyComposerDecision does not route user text into paused-run resume payloads", () => {
  assert.deepEqual(
    resolveBuddyComposerDecision({
      draftText: "继续",
      hasPausedRun: true,
      isResumeBusy: true,
    }),
    { kind: "enqueue_new_turn", userMessage: "继续" },
  );
});

test("resolveInitialBuddyPauseActionMode starts in supplement mode only when required inputs exist", () => {
  assert.equal(resolveInitialBuddyPauseActionMode(0), "execute");
  assert.equal(resolveInitialBuddyPauseActionMode(2), "supplement");
});

test("shouldHoldBuddyQueueDrain keeps Buddy chat turns independent from background paused runs", () => {
  assert.equal(shouldHoldBuddyQueueDrain({ hasPausedRun: true }), false);
  assert.equal(shouldHoldBuddyQueueDrain({ hasPausedRun: false }), false);
});
