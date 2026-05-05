export type BuddyPauseActionMode = "execute" | "supplement";

export type BuddyComposerDecision =
  | { kind: "ignore_empty"; userMessage: "" }
  | { kind: "enqueue_new_turn"; userMessage: string };

export function resolveBuddyComposerDecision(input: {
  draftText: string;
  hasPausedRun: boolean;
  isResumeBusy: boolean;
}): BuddyComposerDecision {
  const userMessage = input.draftText.trim();
  if (!userMessage) {
    return { kind: "ignore_empty", userMessage: "" };
  }
  void input.hasPausedRun;
  void input.isResumeBusy;
  return { kind: "enqueue_new_turn", userMessage };
}

export function resolveInitialBuddyPauseActionMode(requiredInputCount: number): BuddyPauseActionMode {
  return requiredInputCount > 0 ? "supplement" : "execute";
}

export function shouldHoldBuddyQueueDrain(input: { hasPausedRun: boolean }) {
  void input.hasPausedRun;
  return false;
}
