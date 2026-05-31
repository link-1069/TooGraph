import type { Ref } from "vue";

import type { RunDetail } from "../types/run.ts";
import { useBuddyAutonomousReviewRun } from "./useBuddyAutonomousReviewRun.ts";

type BuddyVisibleRunTemplateEffectsOptions = {
  buddyModelRef: Ref<string>;
  pollRunUntilFinished: (runId: string, signal: AbortSignal) => Promise<RunDetail>;
  notifyBuddyDataChanged: () => void;
};

type BuddyVisibleRunTemplateEffectsRequest = {
  runDetail: RunDetail;
};

export function useBuddyVisibleRunTemplateEffects({
  buddyModelRef,
  pollRunUntilFinished,
  notifyBuddyDataChanged,
}: BuddyVisibleRunTemplateEffectsOptions) {
  const {
    startBuddyAutonomousReviewRun,
    abortBackgroundReviewRuns,
  } = useBuddyAutonomousReviewRun({
    buddyModelRef,
    pollRunUntilFinished,
    notifyBuddyDataChanged,
  });

  function startBuddyVisibleRunTemplateEffects(request: BuddyVisibleRunTemplateEffectsRequest) {
    void startBuddyAutonomousReviewRun(request.runDetail);
  }

  function abortBuddyVisibleRunTemplateEffects() {
    abortBackgroundReviewRuns();
  }

  return {
    startBuddyVisibleRunTemplateEffects,
    abortBuddyVisibleRunTemplateEffects,
  };
}
