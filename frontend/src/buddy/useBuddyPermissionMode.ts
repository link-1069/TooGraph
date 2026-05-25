import { computed, ref, watch } from "vue";

import { fetchBuddyRuntimeSettings, updateBuddyRuntimeSettings } from "../api/settings.ts";
import type { BuddyPermissionMode } from "../types/settings.ts";
import { DEFAULT_BUDDY_MODE, resolveBuddyMode, type BuddyMode } from "./buddyChatGraph.ts";

export function useBuddyPermissionMode() {
  const buddyMode = ref<BuddyMode>(DEFAULT_BUDDY_MODE);
  const isBuddyModeLoading = ref(false);
  const isBuddyModeSaving = ref(false);
  const buddyModeError = ref("");
  const hasHydratedBuddyMode = ref(false);

  const buddyModeDisabled = computed(() => isBuddyModeLoading.value || isBuddyModeSaving.value);

  async function hydrateBuddyPermissionMode() {
    isBuddyModeLoading.value = true;
    buddyModeError.value = "";
    try {
      const settings = await fetchBuddyRuntimeSettings();
      buddyMode.value = resolveBuddyMode(settings.permission_mode);
      hasHydratedBuddyMode.value = true;
    } catch (error) {
      buddyModeError.value = error instanceof Error ? error.message : "Failed to load Buddy permission mode.";
      hasHydratedBuddyMode.value = true;
    } finally {
      isBuddyModeLoading.value = false;
    }
  }

  async function persistBuddyPermissionMode(mode: BuddyMode) {
    isBuddyModeSaving.value = true;
    buddyModeError.value = "";
    try {
      const settings = await updateBuddyRuntimeSettings({ permission_mode: mode as BuddyPermissionMode });
      buddyMode.value = resolveBuddyMode(settings.permission_mode);
    } catch (error) {
      buddyModeError.value = error instanceof Error ? error.message : "Failed to save Buddy permission mode.";
    } finally {
      isBuddyModeSaving.value = false;
    }
  }

  watch(buddyMode, (nextMode) => {
    const safeMode = resolveBuddyMode(nextMode);
    if (safeMode !== nextMode) {
      buddyMode.value = safeMode;
      return;
    }
    if (!hasHydratedBuddyMode.value || isBuddyModeLoading.value || isBuddyModeSaving.value) {
      return;
    }
    void persistBuddyPermissionMode(safeMode);
  });

  return {
    buddyMode,
    buddyModeDisabled,
    buddyModeError,
    hydrateBuddyPermissionMode,
  };
}
