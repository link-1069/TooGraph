<template>
  <div class="tool-node-body">
    <div class="tool-node-body__controls">
      <label class="tool-node-body__tool-field">
        <span class="tool-node-body__field-label">Tool</span>
        <ToographSelect
          class="tool-node-body__tool-select"
          :model-value="selectedToolKey"
          :placeholder="toolPlaceholder"
          :disabled="toolSelectDisabled"
          filterable
          remount-on-select
          popper-class="tool-node-body__tool-popper"
          @update:model-value="emit('select-tool', String($event ?? ''))"
        >
          <ElOption label="No tool" value="" />
          <ElOption
            v-if="selectedToolMissing"
            :label="selectedToolKey"
            :value="selectedToolKey"
            disabled
          />
          <ElOption
            v-for="definition in availableToolDefinitions"
            :key="definition.toolKey"
            :label="definition.name"
            :value="definition.toolKey"
          />
        </ToographSelect>
      </label>
      <label v-if="showsTargetAgentSelect" class="tool-node-body__tool-field">
        <span class="tool-node-body__field-label">Target LLM</span>
        <ToographSelect
          class="tool-node-body__tool-select"
          :model-value="targetAgentNodeId"
          placeholder="Select LLM node"
          :disabled="targetAgentNodeOptions.length === 0"
          filterable
          remount-on-select
          popper-class="tool-node-body__tool-popper"
          @update:model-value="emit('update-target-agent-node', String($event ?? ''))"
        >
          <ElOption label="No target" value="" />
          <ElOption
            v-for="option in targetAgentNodeOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ToographSelect>
      </label>
    </div>

    <div v-if="selectedToolInputFields.length > 0" class="tool-node-body__static-inputs">
      <div class="tool-node-body__static-inputs-header">
        <span class="tool-node-body__field-label">Card value</span>
      </div>
      <div
        v-for="field in selectedToolInputFields"
        :key="field.key"
        class="tool-node-body__static-input-row"
        :class="{ 'tool-node-body__static-input-row--enabled': isStaticInputEnabled(field.key) }"
      >
        <div class="tool-node-body__static-input-topline">
          <div class="tool-node-body__static-input-meta">
            <span class="tool-node-body__static-input-name">{{ field.name || field.key }}</span>
            <span class="tool-node-body__static-input-key">{{ field.key }} · {{ field.valueType }}</span>
          </div>
          <ElSwitch
            class="tool-node-body__static-mode-switch"
            :model-value="isStaticInputEnabled(field.key)"
            :width="72"
            inline-prompt
            active-text="Card"
            inactive-text="Port"
            @update:model-value="$event => updateStaticInputMode(field, Boolean($event))"
          />
        </div>
        <div v-if="isStaticInputEnabled(field.key)" class="tool-node-body__static-editor">
          <ElSwitch
            v-if="isBooleanStaticField(field)"
            class="tool-node-body__static-value-switch"
            :model-value="Boolean(staticInputs[field.key])"
            :width="76"
            inline-prompt
            active-text="True"
            inactive-text="False"
            @update:model-value="$event => updateStaticInputValue(field.key, Boolean($event))"
          />
          <ElInputNumber
            v-else-if="isNumberStaticField(field)"
            class="tool-node-body__static-number"
            :model-value="staticInputNumberValue(field.key)"
            controls-position="right"
            @update:model-value="$event => updateStaticInputValue(field.key, Number($event ?? 0))"
          />
          <ElInput
            v-else
            class="tool-node-body__static-text"
            :model-value="staticInputDraftText(field)"
            :type="isJsonStaticField(field) ? 'textarea' : 'text'"
            :autosize="{ minRows: 2, maxRows: 5 }"
            @update:model-value="$event => updateStaticInputDraft(field.key, String($event ?? ''))"
            @blur="commitStaticInputDraft(field)"
            @keydown.ctrl.enter.prevent="commitStaticInputDraft(field)"
            @keydown.meta.enter.prevent="commitStaticInputDraft(field)"
          />
          <div v-if="staticInputErrors[field.key]" class="tool-node-body__static-error">
            {{ staticInputErrors[field.key] }}
          </div>
        </div>
        <p v-if="field.description" class="tool-node-body__static-description">{{ field.description }}</p>
      </div>
    </div>

    <div class="node-card__port-grid">
      <div class="node-card__port-column">
        <StatePortList
          side="input"
          :ports="orderedInputPorts"
          :node-id="nodeId"
          :popover-style="stateEditorPopoverStyle"
          :state-editor-draft="stateEditorDraft"
          :state-editor-error="stateEditorError"
          :type-options="typeOptions"
          :color-options="colorOptions"
          :is-state-editor-open="isStateEditorOpen"
          :is-state-editor-confirm-open="isStateEditorConfirmOpen"
          :is-remove-port-state-confirm-open="isRemovePortStateConfirmOpen"
          :is-state-editor-pill-revealed="isStateEditorPillRevealed"
          :is-port-reordering="isPortReordering"
          :is-port-reorder-placeholder="isPortReorderPlaceholder"
          :create-visible="false"
          :create-open="false"
          create-accent-color="#16a34a"
          create-label="+ input"
          create-anchor-state-key="__toograph_virtual_any_input__"
          :create-draft="createDraft"
          :create-title="createTitle"
          :create-error="createError"
          :create-hint="createHint"
          :create-selection-value="createSelectionValue"
          :create-existing-state-options="createExistingStateOptions"
          :create-type-options="typeOptions"
          :create-popover-style="agentAddPopoverStyle"
          @pointer-enter="emit('pointer-enter', $event)"
          @pointer-leave="emit('pointer-leave', $event)"
          @reorder-pointer-down="(side, stateKey, pointerEvent) => emit('reorder-pointer-down', side, stateKey, pointerEvent)"
          @port-click="(anchorId, stateKey) => emit('port-click', anchorId, stateKey)"
          @remove-click="(anchorId, side, stateKey) => emit('remove-click', anchorId, side, stateKey)"
          @open-create="emit('open-create', $event)"
          @update:name="emit('update:name', $event)"
          @update:type="emit('update:type', $event)"
          @update:color="emit('update:color', $event)"
          @update:description="emit('update:description', $event)"
          @update:create-selection="emit('update:create-selection', $event)"
          @update:create-name="emit('update:create-name', $event)"
          @update:create-type="emit('update:create-type', $event)"
          @update:create-color="emit('update:create-color', $event)"
          @update:create-description="emit('update:create-description', $event)"
          @update:create-value="emit('update:create-value', $event)"
          @cancel-create="emit('cancel-create')"
          @commit-create="emit('commit-create')"
        />
      </div>

      <div class="node-card__port-column node-card__port-column--right">
        <StatePortList
          side="output"
          :ports="orderedOutputPorts"
          :node-id="nodeId"
          :popover-style="stateEditorPopoverStyle"
          :state-editor-draft="stateEditorDraft"
          :state-editor-error="stateEditorError"
          :type-options="typeOptions"
          :color-options="colorOptions"
          :is-state-editor-open="isStateEditorOpen"
          :is-state-editor-confirm-open="isStateEditorConfirmOpen"
          :is-remove-port-state-confirm-open="isRemovePortStateConfirmOpen"
          :is-state-editor-pill-revealed="isStateEditorPillRevealed"
          :is-port-reordering="isPortReordering"
          :is-port-reorder-placeholder="isPortReorderPlaceholder"
          :create-visible="false"
          :create-open="false"
          create-accent-color="#9a3412"
          create-label="+ output"
          create-anchor-state-key="__toograph_virtual_any_output__"
          :create-draft="createDraft"
          :create-title="createTitle"
          :create-error="createError"
          :create-hint="createHint"
          :create-selection-value="createSelectionValue"
          :create-existing-state-options="createExistingStateOptions"
          :create-type-options="typeOptions"
          :create-popover-style="agentAddPopoverStyle"
          @pointer-enter="emit('pointer-enter', $event)"
          @pointer-leave="emit('pointer-leave', $event)"
          @reorder-pointer-down="(side, stateKey, pointerEvent) => emit('reorder-pointer-down', side, stateKey, pointerEvent)"
          @port-click="(anchorId, stateKey) => emit('port-click', anchorId, stateKey)"
          @remove-click="(anchorId, side, stateKey) => emit('remove-click', anchorId, side, stateKey)"
          @open-create="emit('open-create', $event)"
          @update:name="emit('update:name', $event)"
          @update:type="emit('update:type', $event)"
          @update:color="emit('update:color', $event)"
          @update:description="emit('update:description', $event)"
          @update:create-selection="emit('update:create-selection', $event)"
          @update:create-name="emit('update:create-name', $event)"
          @update:create-type="emit('update:create-type', $event)"
          @update:create-color="emit('update:create-color', $event)"
          @update:create-description="emit('update:create-description', $event)"
          @update:create-value="emit('update:create-value', $event)"
          @cancel-create="emit('cancel-create')"
          @commit-create="emit('commit-create')"
        />
      </div>
    </div>

    <div v-if="toolDefinitionsLoading" class="tool-node-body__message">Loading tools</div>
    <div v-else-if="toolDefinitionsError" class="tool-node-body__message tool-node-body__message--error">
      {{ toolDefinitionsError }}
    </div>
    <div v-else-if="body.toolDescription" class="tool-node-body__description">
      {{ body.toolDescription }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from "vue";
import { ElInput, ElInputNumber, ElOption, ElSwitch } from "element-plus";

import ToographSelect from "@/components/ToographSelect.vue";
import StatePortList from "./StatePortList.vue";
import type { StatePortExistingStateOption } from "./statePortCreateModel";
import type { NodeCardViewModel, NodePortViewModel } from "./nodeCardViewModel";
import type { ToolDefinition, ToolIoField } from "@/types/tools";
import type { StateColorOption, StateFieldDraft, StateFieldType } from "@/editor/workspace/statePanelFields";

type ToolBodyViewModel = Extract<NodeCardViewModel["body"], { kind: "tool" }>;

const props = defineProps<{
  nodeId: string;
  body: ToolBodyViewModel;
  selectedToolKey: string;
  staticInputs: Record<string, unknown>;
  targetAgentNodeId: string;
  targetAgentNodeOptions: Array<{ value: string; label: string }>;
  toolDefinitions: ToolDefinition[];
  toolDefinitionsLoading: boolean;
  toolDefinitionsError: string | null;
  orderedInputPorts: NodePortViewModel[];
  orderedOutputPorts: NodePortViewModel[];
  stateEditorPopoverStyle: CSSProperties;
  agentAddPopoverStyle: CSSProperties;
  stateEditorDraft: StateFieldDraft | null;
  stateEditorError: string | null;
  typeOptions: StateFieldType[];
  colorOptions: StateColorOption[];
  createDraft: StateFieldDraft | null;
  createTitle: string;
  createError: string | null;
  createHint: string;
  createSelectionValue: string;
  createExistingStateOptions: StatePortExistingStateOption[];
  isStateEditorOpen: (anchorId: string) => boolean;
  isStateEditorConfirmOpen: (anchorId: string) => boolean;
  isRemovePortStateConfirmOpen: (anchorId: string) => boolean;
  isStateEditorPillRevealed: (anchorId: string) => boolean;
  isPortReordering: (side: "input" | "output", stateKey: string) => boolean;
  isPortReorderPlaceholder: (side: "input" | "output", stateKey: string) => boolean;
}>();

const emit = defineEmits<{
  (event: "select-tool", toolKey: string): void;
  (event: "update-static-inputs", staticInputs: Record<string, unknown>): void;
  (event: "update-target-agent-node", nodeId: string): void;
  (event: "pointer-enter", anchorId: string): void;
  (event: "pointer-leave", anchorId: string): void;
  (event: "reorder-pointer-down", side: "input" | "output", stateKey: string, pointerEvent: PointerEvent): void;
  (event: "port-click", anchorId: string, stateKey: string): void;
  (event: "remove-click", anchorId: string, side: "input" | "output", stateKey: string): void;
  (event: "open-create", side: "input" | "output"): void;
  (event: "update:name", value: string): void;
  (event: "update:type", value: string): void;
  (event: "update:color", value: string): void;
  (event: "update:description", value: string): void;
  (event: "update:create-selection", value: string): void;
  (event: "update:create-name", value: string | number): void;
  (event: "update:create-type", value: string | number | boolean | undefined): void;
  (event: "update:create-color", value: string | number | boolean | undefined): void;
  (event: "update:create-description", value: string | number): void;
  (event: "update:create-value", value: unknown): void;
  (event: "cancel-create"): void;
  (event: "commit-create"): void;
}>();

const availableToolDefinitions = computed(() =>
  props.toolDefinitions.filter((definition) => definition.status !== "disabled"),
);
const selectedToolDefinition = computed(() =>
  availableToolDefinitions.value.find((definition) => definition.toolKey === props.selectedToolKey),
);
const selectedToolInputFields = computed(() => selectedToolDefinition.value?.inputSchema ?? []);
const selectedToolMissing = computed(
  () => Boolean(props.selectedToolKey) && !availableToolDefinitions.value.some((definition) => definition.toolKey === props.selectedToolKey),
);
const toolSelectDisabled = computed(() => props.toolDefinitionsLoading || Boolean(props.toolDefinitionsError));
const toolPlaceholder = computed(() => {
  if (props.toolDefinitionsLoading) {
    return "Loading tools";
  }
  if (props.toolDefinitionsError) {
    return "Tool catalog unavailable";
  }
  return props.selectedToolKey ? "Select tool" : "No tool";
});
const showsTargetAgentSelect = computed(() => props.selectedToolKey === "buddy_context_pressure_check");
const staticInputDrafts = ref<Record<string, string>>({});
const staticInputErrors = ref<Record<string, string>>({});

watch(
  () => props.selectedToolKey,
  () => {
    staticInputDrafts.value = {};
    staticInputErrors.value = {};
  },
);

watch(
  () => props.staticInputs,
  () => {
    const activeKeys = new Set(Object.keys(props.staticInputs));
    staticInputDrafts.value = Object.fromEntries(Object.entries(staticInputDrafts.value).filter(([fieldKey]) => activeKeys.has(fieldKey)));
    staticInputErrors.value = Object.fromEntries(Object.entries(staticInputErrors.value).filter(([fieldKey]) => activeKeys.has(fieldKey)));
  },
  { deep: true },
);

function isStaticInputEnabled(fieldKey: string) {
  return Object.prototype.hasOwnProperty.call(props.staticInputs, fieldKey);
}

function updateStaticInputMode(field: ToolIoField, enabled: boolean) {
  const nextStaticInputs = { ...props.staticInputs };
  if (enabled) {
    nextStaticInputs[field.key] = isStaticInputEnabled(field.key)
      ? props.staticInputs[field.key]
      : defaultStaticInputValue(field);
  } else {
    delete nextStaticInputs[field.key];
    clearStaticInputDraft(field.key);
  }
  emit("update-static-inputs", nextStaticInputs);
}

function updateStaticInputValue(fieldKey: string, value: unknown) {
  emit("update-static-inputs", { ...props.staticInputs, [fieldKey]: value });
  clearStaticInputDraft(fieldKey);
}

function updateStaticInputDraft(fieldKey: string, value: string) {
  staticInputDrafts.value = { ...staticInputDrafts.value, [fieldKey]: value };
  if (staticInputErrors.value[fieldKey]) {
    staticInputErrors.value = { ...staticInputErrors.value, [fieldKey]: "" };
  }
}

function commitStaticInputDraft(field: ToolIoField) {
  if (!isStaticInputEnabled(field.key)) {
    return;
  }
  const parseResult = parseStaticInputValue(field, staticInputDraftText(field));
  if (parseResult.kind === "error") {
    staticInputErrors.value = { ...staticInputErrors.value, [field.key]: parseResult.message };
    return;
  }
  updateStaticInputValue(field.key, parseResult.value);
}

function staticInputDraftText(field: ToolIoField) {
  return staticInputDrafts.value[field.key] ?? formatStaticInputValue(props.staticInputs[field.key], field);
}

function staticInputNumberValue(fieldKey: string) {
  const numericValue = Number(props.staticInputs[fieldKey]);
  return Number.isFinite(numericValue) ? numericValue : 0;
}

function isBooleanStaticField(field: ToolIoField) {
  return normalizeStaticFieldValueType(field) === "boolean";
}

function isNumberStaticField(field: ToolIoField) {
  const valueType = normalizeStaticFieldValueType(field);
  return valueType === "number" || valueType === "integer";
}

function isJsonStaticField(field: ToolIoField) {
  const valueType = normalizeStaticFieldValueType(field);
  return valueType === "json" || valueType === "object" || valueType === "array";
}

function normalizeStaticFieldValueType(field: ToolIoField) {
  return field.valueType.trim().toLowerCase();
}

function defaultStaticInputValue(field: ToolIoField): unknown {
  if (isBooleanStaticField(field)) {
    return false;
  }
  if (isNumberStaticField(field)) {
    return 0;
  }
  if (isJsonStaticField(field)) {
    return {};
  }
  return "";
}

function formatStaticInputValue(value: unknown, field: ToolIoField) {
  if (isJsonStaticField(field)) {
    return JSON.stringify(value ?? null, null, 2);
  }
  if (typeof value === "string") {
    return value;
  }
  return value == null ? "" : String(value);
}

function parseStaticInputValue(field: ToolIoField, value: string): { kind: "ok"; value: unknown } | { kind: "error"; message: string } {
  if (isJsonStaticField(field)) {
    const trimmedValue = value.trim();
    if (!trimmedValue) {
      return { kind: "ok", value: null };
    }
    try {
      return { kind: "ok", value: JSON.parse(trimmedValue) };
    } catch {
      return { kind: "error", message: "Invalid JSON" };
    }
  }
  if (isNumberStaticField(field)) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return { kind: "error", message: "Invalid number" };
    }
    return { kind: "ok", value: numericValue };
  }
  return { kind: "ok", value };
}

function clearStaticInputDraft(fieldKey: string) {
  const { [fieldKey]: removedDraft, ...nextDrafts } = staticInputDrafts.value;
  const { [fieldKey]: removedError, ...nextErrors } = staticInputErrors.value;
  void removedDraft;
  void removedError;
  staticInputDrafts.value = nextDrafts;
  staticInputErrors.value = nextErrors;
}
</script>

<style scoped>
.tool-node-body {
  display: grid;
  gap: 12px;
}

.tool-node-body__controls {
  display: grid;
  gap: 8px;
}

.tool-node-body__tool-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.tool-node-body__field-label {
  color: #3b82f6;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.tool-node-body__tool-select {
  width: 100%;
  --el-color-primary: #2563eb;
  --el-border-radius-base: 16px;
}

.tool-node-body__static-inputs {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.tool-node-body__static-inputs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.tool-node-body__static-input-row {
  display: grid;
  gap: 7px;
  min-width: 0;
  border: 1px solid rgba(59, 130, 246, 0.13);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.66);
  padding: 9px 10px;
}

.tool-node-body__static-input-row--enabled {
  border-color: rgba(37, 99, 235, 0.22);
  background: rgba(239, 246, 255, 0.62);
}

.tool-node-body__static-input-topline {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.tool-node-body__static-input-meta {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.tool-node-body__static-input-name {
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-node-body__static-input-key {
  overflow: hidden;
  color: rgba(71, 85, 105, 0.72);
  font-family: var(--toograph-font-mono);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-node-body__static-mode-switch,
.tool-node-body__static-value-switch {
  --el-switch-on-color: #2563eb;
  --el-switch-off-color: rgba(100, 116, 139, 0.3);
}

.tool-node-body__static-editor {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.tool-node-body__static-number {
  width: 100%;
}

.tool-node-body__static-text :deep(.el-input__wrapper),
.tool-node-body__static-text :deep(.el-textarea__inner),
.tool-node-body__static-number :deep(.el-input__wrapper) {
  background: rgba(255, 252, 246, 0.96);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08);
}

.tool-node-body__static-description {
  margin: 0;
  color: rgba(60, 41, 20, 0.58);
  font-size: 11px;
  line-height: 1.42;
}

.tool-node-body__static-error {
  color: #b91c1c;
  font-size: 11px;
  font-weight: 700;
}

.node-card__port-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
  width: 100%;
  column-gap: 24px;
}

.node-card__port-column {
  display: grid;
  min-width: 0;
  width: 100%;
  gap: 6px;
}

.node-card__port-column--right {
  justify-items: end;
}

.tool-node-body__description,
.tool-node-body__message {
  border-radius: 14px;
  background: rgba(255, 250, 241, 0.74);
  color: #6b5a48;
  font-size: 12px;
  line-height: 1.45;
  padding: 9px 11px;
}

.tool-node-body__message--error {
  color: #b91c1c;
}
</style>
