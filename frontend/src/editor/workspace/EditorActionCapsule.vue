<template>
  <div class="editor-action-capsule">
    <div class="editor-action-capsule__tools">
      <ElTooltip :content="resolvedSaveGraphLabel" placement="bottom">
        <button
          type="button"
          class="editor-action-capsule__icon-button"
          :aria-label="resolvedSaveGraphLabel"
          data-virtual-affordance-id="editor.action.saveActiveGraph"
          :data-virtual-affordance-label="resolvedSaveGraphLabel"
          data-virtual-affordance-role="button"
          data-virtual-affordance-zone="editor.actions"
          data-virtual-affordance-actions="click"
          @click="$emit('save-active-graph')"
        >
          <ElIcon aria-hidden="true"><CollectionTag /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip v-if="showSaveAsGraph" :content="resolvedSaveAsGraphLabel" placement="bottom">
        <button
          type="button"
          class="editor-action-capsule__icon-button editor-action-capsule__icon-button--save-as"
          :aria-label="resolvedSaveAsGraphLabel"
          @click="$emit('save-active-graph-as-new')"
        >
          <ElIcon aria-hidden="true"><CollectionTag /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip :content="t('editor.saveAsTemplate')" placement="bottom">
        <button
          type="button"
          class="editor-action-capsule__icon-button editor-action-capsule__icon-button--save-template"
          :aria-label="t('editor.saveAsTemplate')"
          data-virtual-affordance-id="editor.action.saveActiveGraphAsTemplate"
          :data-virtual-affordance-label="t('editor.saveAsTemplate')"
          data-virtual-affordance-role="button"
          data-virtual-affordance-zone="editor.actions"
          data-virtual-affordance-actions="click"
          @click="$emit('save-active-graph-as-template')"
        >
          <ElIcon aria-hidden="true"><CollectionTag /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip v-if="showRevisionHistory" :content="t('graphLibrary.history')" placement="bottom">
        <button
          type="button"
          class="editor-action-capsule__icon-button"
          :aria-label="t('graphLibrary.history')"
          data-virtual-affordance-id="editor.action.openGraphRevisionHistory"
          :data-virtual-affordance-label="t('graphLibrary.history')"
          data-virtual-affordance-role="button"
          data-virtual-affordance-zone="editor.actions"
          data-virtual-affordance-actions="click"
          @click="$emit('open-active-graph-revisions')"
        >
          <ElIcon aria-hidden="true"><Clock /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip :content="t('editor.validateGraph')" placement="bottom">
        <button
          type="button"
          class="editor-action-capsule__icon-button"
          :aria-label="t('editor.validateGraph')"
          data-virtual-affordance-id="editor.action.validateActiveGraph"
          :data-virtual-affordance-label="t('editor.validateGraph')"
          data-virtual-affordance-role="button"
          data-virtual-affordance-zone="editor.actions"
          data-virtual-affordance-actions="click"
          @click="$emit('validate-active-graph')"
        >
          <ElIcon aria-hidden="true"><CircleCheck /></ElIcon>
        </button>
      </ElTooltip>
      <ElTooltip :content="t('editor.exportPythonGraph')" placement="bottom">
        <button type="button" class="editor-action-capsule__icon-button" :aria-label="t('editor.exportPythonGraph')" @click="$emit('export-active-graph')">
          <ElIcon aria-hidden="true"><Download /></ElIcon>
        </button>
      </ElTooltip>
    </div>

    <button
      type="button"
      class="editor-action-capsule__state-pill"
      :class="{ 'editor-action-capsule__state-pill--active': isStatePanelOpen }"
      data-virtual-affordance-id="editor.action.toggleStatePanel"
      :data-virtual-affordance-label="t('editor.statePanel')"
      data-virtual-affordance-role="button"
      data-virtual-affordance-zone="editor.actions"
      data-virtual-affordance-actions="click"
      :data-virtual-affordance-current="isStatePanelOpen ? 'true' : undefined"
      @click="$emit('toggle-state-panel')"
    >
      <span>{{ t("editor.statePanel") }}</span>
      <span class="editor-action-capsule__state-count">{{ activeStateCount }}</span>
    </button>

    <button
      type="button"
      class="editor-action-capsule__state-pill"
      :class="{
        'editor-action-capsule__state-pill--active': isRunActivityPanelOpen,
        'editor-action-capsule__state-pill--hint': hasRunActivityHint && !isRunActivityPanelOpen,
      }"
      data-virtual-affordance-id="editor.action.toggleRunActivity"
      :data-virtual-affordance-label="t('editor.runActivityPanel')"
      data-virtual-affordance-role="button"
      data-virtual-affordance-zone="editor.actions"
      data-virtual-affordance-actions="click"
      :data-virtual-affordance-current="isRunActivityPanelOpen ? 'true' : undefined"
      @click="$emit('toggle-run-activity-panel')"
    >
      <span>{{ t("editor.runActivityPanel") }}</span>
    </button>

    <button
      type="button"
      class="editor-action-capsule__run"
      :class="{
        'editor-action-capsule__run--terminate': isTerminateMode,
        'editor-action-capsule__run--terminating': props.isTerminatingActiveRun,
      }"
      :aria-label="primaryRunActionLabel"
      :aria-busy="props.isTerminatingActiveRun ? 'true' : undefined"
      :disabled="isTerminatingActiveRun"
      :data-virtual-affordance-id="isTerminateMode ? 'editor.action.terminateActiveRun' : 'editor.action.runActiveGraph'"
      :data-virtual-affordance-label="primaryRunActionLabel"
      data-virtual-affordance-role="button"
      data-virtual-affordance-zone="editor.actions"
      data-virtual-affordance-actions="click"
      @click="handlePrimaryRunClick"
    >
      <ElIcon class="editor-action-capsule__run-icon" aria-hidden="true">
        <Loading v-if="props.isTerminatingActiveRun" />
        <CloseBold v-else-if="isTerminateMode" />
        <VideoPlay v-else />
      </ElIcon>
      <span>{{ primaryRunActionLabel }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { CircleCheck, Clock, CloseBold, CollectionTag, Download, Loading, VideoPlay } from "@element-plus/icons-vue";
import { ElIcon, ElTooltip } from "element-plus";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const TERMINABLE_RUN_STATUSES = new Set(["queued", "running", "resuming"]);

const props = defineProps<{
  activeStateCount: number;
  isStatePanelOpen: boolean;
  isRunActivityPanelOpen: boolean;
  hasRunActivityHint: boolean;
  activeRunStatus?: string | null;
  isTerminatingActiveRun?: boolean;
  saveGraphLabel?: string;
  showSaveAsGraph?: boolean;
  saveAsGraphLabel?: string;
  showRevisionHistory?: boolean;
}>();

const emit = defineEmits<{
  (event: "toggle-state-panel"): void;
  (event: "toggle-run-activity-panel"): void;
  (event: "save-active-graph"): void;
  (event: "save-active-graph-as-new"): void;
  (event: "save-active-graph-as-template"): void;
  (event: "open-active-graph-revisions"): void;
  (event: "validate-active-graph"): void;
  (event: "export-active-graph"): void;
  (event: "run-active-graph"): void;
  (event: "terminate-active-run"): void;
}>();

const { t } = useI18n();
const resolvedSaveGraphLabel = computed(() => props.saveGraphLabel ?? t("editor.saveGraph"));
const resolvedSaveAsGraphLabel = computed(() => props.saveAsGraphLabel ?? t("editor.saveAsGraph"));
const isTerminateMode = computed(() => TERMINABLE_RUN_STATUSES.has(String(props.activeRunStatus ?? "")));
const primaryRunActionLabel = computed(() => {
  if (props.isTerminatingActiveRun) {
    return t("editor.terminatingRun");
  }
  return isTerminateMode.value ? t("editor.terminateRun") : t("editor.runGraph");
});

function handlePrimaryRunClick() {
  if (isTerminateMode.value) {
    emit("terminate-active-run");
    return;
  }
  emit("run-active-graph");
}
</script>

<style scoped>
.editor-action-capsule {
  position: relative;
  isolation: isolate;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  border: 1px solid var(--toograph-glass-border);
  border-radius: 999px;
  background: var(--toograph-glass-bg);
  padding: 8px;
  box-shadow: var(--toograph-glass-shadow), var(--toograph-glass-highlight), var(--toograph-glass-rim);
  backdrop-filter: blur(28px) saturate(1.65) contrast(1.02);
}

.editor-action-capsule::before {
  content: "";
  pointer-events: none;
  position: absolute;
  inset: 1px;
  z-index: 0;
  border-radius: inherit;
  background: var(--toograph-glass-specular), var(--toograph-glass-lens);
  mix-blend-mode: screen;
  opacity: 0.62;
}

.editor-action-capsule > * {
  position: relative;
  z-index: 1;
}

.editor-action-capsule__tools {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.editor-action-capsule__icon-button,
.editor-action-capsule__state-pill,
.editor-action-capsule__run {
  min-height: 40px;
  border-radius: 999px;
  transition: background-color 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, color 0.16s ease,
    transform 0.16s ease;
}

.editor-action-capsule__icon-button {
  width: 40px;
  border: 1px solid transparent;
  background: transparent;
  color: rgba(90, 58, 34, 0.94);
  cursor: pointer;
}

.editor-action-capsule__state-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(154, 52, 18, 0.18);
  background: rgba(255, 252, 247, 0.92);
  padding: 0 14px;
  color: rgba(120, 53, 15, 0.92);
  cursor: pointer;
}

.editor-action-capsule__state-pill--active {
  border-color: rgba(154, 52, 18, 0.44);
  background: rgba(255, 238, 222, 0.98);
  color: rgba(126, 46, 11, 0.98);
}

.editor-action-capsule__state-pill--hint {
  border-color: rgba(37, 99, 235, 0.42);
  background: rgba(239, 246, 255, 0.96);
  color: rgba(30, 64, 175, 0.96);
  animation: editor-action-capsule-run-activity-pulse 1.1s ease-in-out infinite;
}

.editor-action-capsule__state-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  min-height: 22px;
  border-radius: 999px;
  background: rgba(154, 52, 18, 0.12);
  padding: 0 7px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

.editor-action-capsule__run {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid rgba(154, 52, 18, 0.9);
  background: rgba(154, 52, 18, 0.92);
  color: rgba(255, 250, 242, 0.98);
  padding: 0 16px;
  font-weight: 700;
  cursor: pointer;
}

.editor-action-capsule__run-icon {
  font-size: 0.95rem;
}

.editor-action-capsule__icon-button:hover {
  border-color: rgba(193, 151, 106, 0.34);
  background: rgba(255, 245, 232, 0.96);
}

.editor-action-capsule__state-pill:hover {
  border-color: rgba(154, 52, 18, 0.28);
  background: rgba(255, 246, 237, 0.98);
}

.editor-action-capsule__state-pill--active:hover {
  border-color: rgba(154, 52, 18, 0.44);
  background: rgba(255, 238, 222, 0.98);
  color: rgba(126, 46, 11, 0.98);
}

.editor-action-capsule__state-pill--hint:hover {
  border-color: rgba(37, 99, 235, 0.5);
  background: rgba(219, 234, 254, 0.98);
  color: rgba(30, 64, 175, 0.98);
}

.editor-action-capsule__run:hover {
  border-color: rgba(131, 43, 13, 0.96);
  background: rgba(131, 43, 13, 0.96);
  transform: translateY(-1px);
}

.editor-action-capsule__run--terminate {
  border-color: rgba(185, 28, 28, 0.86);
  background: rgba(185, 28, 28, 0.92);
  color: rgba(255, 251, 247, 0.98);
}

.editor-action-capsule__run--terminate:hover {
  border-color: rgba(153, 27, 27, 0.96);
  background: rgba(153, 27, 27, 0.96);
}

.editor-action-capsule__run--terminating {
  border-color: rgba(220, 38, 38, 0.94);
  background: rgba(220, 38, 38, 0.96);
  color: rgba(255, 251, 247, 1);
  box-shadow: 0 0 0 4px rgba(248, 113, 113, 0.2), 0 10px 22px rgba(127, 29, 29, 0.2);
  animation: editor-action-capsule-terminating-pulse 0.9s ease-in-out infinite;
}

.editor-action-capsule__run--terminating .editor-action-capsule__run-icon {
  animation: editor-action-capsule-spin 0.82s linear infinite;
}

.editor-action-capsule__run:disabled {
  cursor: wait;
  opacity: 1;
  transform: none;
}

.editor-action-capsule__icon-button:focus-visible,
.editor-action-capsule__state-pill:focus-visible,
.editor-action-capsule__run:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(210, 162, 117, 0.3);
}

@keyframes editor-action-capsule-run-activity-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.16);
  }

  50% {
    box-shadow: 0 0 0 5px rgba(37, 99, 235, 0.18);
  }
}

@keyframes editor-action-capsule-terminating-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.16), 0 10px 22px rgba(127, 29, 29, 0.18);
  }

  50% {
    box-shadow: 0 0 0 7px rgba(248, 113, 113, 0.28), 0 12px 26px rgba(127, 29, 29, 0.24);
  }
}

@keyframes editor-action-capsule-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .editor-action-capsule__state-pill--hint {
    animation: none;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
  }

  .editor-action-capsule__run--terminating,
  .editor-action-capsule__run--terminating .editor-action-capsule__run-icon {
    animation: none;
  }
}
</style>
