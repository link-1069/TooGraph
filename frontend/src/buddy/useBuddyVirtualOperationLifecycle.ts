import { computed, ref, shallowRef } from "vue";

import type {
  PageOperationRetryKind,
  PageOperationRetryRecord,
} from "./pageOperationResume.ts";

export type BuddyVirtualOperationStatus = {
  label: string;
  tone: "active" | "stopping";
};

export type BuddyVirtualOperationToken = {
  id: number;
  interrupted: boolean;
  retryChain: PageOperationRetryRecord[];
  interruptPromise: Promise<void>;
  interrupt: () => void;
};

export function useBuddyVirtualOperationLifecycle() {
  const virtualOperationStatus = ref<BuddyVirtualOperationStatus | null>(null);
  const activeVirtualOperationToken = shallowRef<BuddyVirtualOperationToken | null>(null);
  const isVirtualOperationRunning = computed(() => Boolean(activeVirtualOperationToken.value));
  let virtualOperationTokenId = 0;

  function beginVirtualOperation(label: string): BuddyVirtualOperationToken {
    activeVirtualOperationToken.value?.interrupt();
    const token = createBuddyVirtualOperationToken();
    activeVirtualOperationToken.value = token;
    virtualOperationStatus.value = {
      label,
      tone: "active",
    };
    return token;
  }

  function beginBackgroundVirtualOperation(label: string): BuddyVirtualOperationToken {
    activeVirtualOperationToken.value?.interrupt();
    const token = createBuddyVirtualOperationToken();
    activeVirtualOperationToken.value = token;
    virtualOperationStatus.value = {
      label,
      tone: "active",
    };
    return token;
  }

  function createBuddyVirtualOperationToken(): BuddyVirtualOperationToken {
    let resolveInterrupt: () => void = () => undefined;
    const interruptPromise = new Promise<void>((resolve) => {
      resolveInterrupt = resolve;
    });
    const token: BuddyVirtualOperationToken = {
      id: ++virtualOperationTokenId,
      interrupted: false,
      retryChain: [],
      interruptPromise,
      interrupt: () => {
        if (token.interrupted) {
          return;
        }
        token.interrupted = true;
        resolveInterrupt();
      },
    };
    return token;
  }

  function interruptVirtualOperation(label: string) {
    const token = activeVirtualOperationToken.value;
    if (!token) {
      return false;
    }
    token.interrupt();
    virtualOperationStatus.value = {
      label,
      tone: "stopping",
    };
    return true;
  }

  function finishVirtualOperation(token: BuddyVirtualOperationToken) {
    if (activeVirtualOperationToken.value !== token) {
      return false;
    }
    activeVirtualOperationToken.value = null;
    virtualOperationStatus.value = null;
    return true;
  }

  function isVirtualOperationInterrupted(token: BuddyVirtualOperationToken | null) {
    return !token || token.interrupted || activeVirtualOperationToken.value !== token;
  }

  function recordVirtualOperationRetry(token: BuddyVirtualOperationToken | null, record: PageOperationRetryRecord) {
    if (!token) {
      return;
    }
    token.retryChain.push(record);
  }

  function buildVirtualOperationRetryRecord(
    kind: PageOperationRetryKind,
    targetId: string,
    attempts: number,
    status: PageOperationRetryRecord["status"],
    startedAt: number,
  ): PageOperationRetryRecord {
    return {
      kind,
      target_id: targetId,
      attempts: Math.max(1, attempts),
      status,
      elapsed_ms: Math.max(0, Date.now() - startedAt),
    };
  }

  function waitForVirtualOperation(timeoutMs: number, token: BuddyVirtualOperationToken | null = activeVirtualOperationToken.value) {
    return new Promise<void>((resolve) => {
      if (typeof window === "undefined") {
        resolve();
        return;
      }
      if (token?.interrupted) {
        resolve();
        return;
      }
      let settled = false;
      let timeoutId: number | null = null;
      const finishWait = () => {
        if (settled) {
          return;
        }
        settled = true;
        if (timeoutId !== null) {
          window.clearTimeout(timeoutId);
        }
        resolve();
      };
      timeoutId = window.setTimeout(finishWait, Math.max(0, Math.round(timeoutMs)));
      token?.interruptPromise.then(finishWait);
    });
  }

  return {
    activeVirtualOperationToken,
    beginBackgroundVirtualOperation,
    beginVirtualOperation,
    buildVirtualOperationRetryRecord,
    finishVirtualOperation,
    interruptVirtualOperation,
    isVirtualOperationInterrupted,
    isVirtualOperationRunning,
    recordVirtualOperationRetry,
    virtualOperationStatus,
    waitForVirtualOperation,
  };
}
