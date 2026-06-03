import { ref } from "vue";

import type { PresetDocument } from "../../types/node-system.ts";
import type { SettingsPayload } from "../../types/settings.ts";
import type { ActionDefinition } from "../../types/actions.ts";
import type { ToolDefinition } from "../../types/tools.ts";

type WorkspaceResourceControllerInput = {
  fetchSettings: () => Promise<SettingsPayload>;
  fetchActionDefinitions: () => Promise<ActionDefinition[]>;
  fetchToolDefinitions: () => Promise<ToolDefinition[]>;
  fetchPresets: () => Promise<PresetDocument[]>;
};

export function useWorkspaceResourceController(input: WorkspaceResourceControllerInput) {
  const settings = ref<SettingsPayload | null>(null);
  const actionDefinitions = ref<ActionDefinition[]>([]);
  const actionDefinitionsLoading = ref(true);
  const actionDefinitionsError = ref<string | null>(null);
  const toolDefinitions = ref<ToolDefinition[]>([]);
  const toolDefinitionsLoading = ref(true);
  const toolDefinitionsError = ref<string | null>(null);
  const persistedPresets = ref<PresetDocument[]>([]);

  async function loadSettings() {
    try {
      settings.value = await input.fetchSettings();
    } catch {
      settings.value = null;
    }
  }

  async function refreshAgentModels() {
    await loadSettings();
  }

  async function loadActionDefinitions() {
    try {
      actionDefinitionsLoading.value = true;
      actionDefinitions.value = await input.fetchActionDefinitions();
      actionDefinitionsError.value = null;
    } catch (error) {
      actionDefinitions.value = [];
      actionDefinitionsError.value = error instanceof Error ? error.message : "Failed to load actions.";
    } finally {
      actionDefinitionsLoading.value = false;
    }
  }

  async function loadToolDefinitions() {
    try {
      toolDefinitionsLoading.value = true;
      toolDefinitions.value = await input.fetchToolDefinitions();
      toolDefinitionsError.value = null;
    } catch (error) {
      toolDefinitions.value = [];
      toolDefinitionsError.value = error instanceof Error ? error.message : "Failed to load tools.";
    } finally {
      toolDefinitionsLoading.value = false;
    }
  }

  async function loadPersistedPresets() {
    persistedPresets.value = await input.fetchPresets();
  }

  function loadInitialWorkspaceResources() {
    void loadSettings();
    void loadActionDefinitions();
    void loadToolDefinitions();
    void loadPersistedPresets();
  }

  return {
    settings,
    actionDefinitions,
    actionDefinitionsLoading,
    actionDefinitionsError,
    toolDefinitions,
    toolDefinitionsLoading,
    toolDefinitionsError,
    persistedPresets,
    loadInitialWorkspaceResources,
    loadSettings,
    refreshAgentModels,
    loadActionDefinitions,
    loadToolDefinitions,
    loadPersistedPresets,
  };
}
