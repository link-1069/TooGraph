<template>
  <form
    class="buddy-widget__form"
    :class="{ 'buddy-widget__form--with-terminate': isRunActive }"
    @submit.prevent="emit('submit')"
  >
    <textarea
      :value="modelValue"
      class="buddy-widget__input"
      rows="2"
      :placeholder="placeholder"
      @input="handleInput"
      @keydown.enter.exact.prevent="emit('submit')"
    />
    <button
      v-if="isRunActive"
      type="button"
      class="buddy-widget__terminate"
      :class="{ 'buddy-widget__terminate--terminating': isTerminatingRun }"
      :disabled="isTerminatingRun"
      :title="isTerminatingRun ? terminatingLabel : terminateLabel"
      :aria-label="isTerminatingRun ? terminatingLabel : terminateLabel"
      :aria-busy="isTerminatingRun ? 'true' : undefined"
      @click="emit('terminate')"
    >
      <ElIcon>
        <Loading v-if="isTerminatingRun" />
        <CloseBold v-else />
      </ElIcon>
    </button>
    <button
      type="submit"
      class="buddy-widget__send"
      :disabled="!modelValue.trim()"
      :title="sendLabel"
      :aria-label="sendLabel"
    >
      <ElIcon><Promotion /></ElIcon>
    </button>
  </form>
</template>

<script setup lang="ts">
import { CloseBold, Loading, Promotion } from "@element-plus/icons-vue";
import { ElIcon } from "element-plus";

withDefaults(defineProps<{
  modelValue: string;
  placeholder: string;
  sendLabel: string;
  terminateLabel?: string;
  terminatingLabel?: string;
  isRunActive?: boolean;
  isTerminatingRun?: boolean;
}>(), {
  terminateLabel: "",
  terminatingLabel: "",
  isRunActive: false,
  isTerminatingRun: false,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  terminate: [];
}>();

function handleInput(event: Event) {
  emit("update:modelValue", event.target instanceof HTMLTextAreaElement ? event.target.value : "");
}
</script>

<style scoped>
.buddy-widget__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid rgba(154, 52, 18, 0.1);
  background: rgba(255, 248, 240, 0.56);
}

.buddy-widget__form--with-terminate {
  grid-template-columns: minmax(0, 1fr) 38px 38px;
}

.buddy-widget__input {
  width: 100%;
  min-height: 42px;
  max-height: 96px;
  resize: vertical;
  border: 1px solid rgba(154, 52, 18, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.74);
  color: var(--toograph-text-strong);
  padding: 9px 10px;
  font-size: 13px;
  line-height: 1.45;
}

.buddy-widget__input:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.buddy-widget__send,
.buddy-widget__terminate {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 42px;
  border: 1px solid rgba(154, 52, 18, 0.14);
  border-radius: 8px;
  background: rgba(154, 52, 18, 0.1);
  color: var(--toograph-accent-strong);
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    color 160ms ease,
    transform 160ms ease;
}

.buddy-widget__terminate {
  border-color: rgba(185, 28, 28, 0.2);
  background: rgba(254, 226, 226, 0.78);
  color: #991b1b;
}

.buddy-widget__terminate--terminating {
  border-color: rgba(220, 38, 38, 0.48);
  background: rgba(220, 38, 38, 0.94);
  color: rgba(255, 251, 247, 1);
  box-shadow: 0 0 0 3px rgba(248, 113, 113, 0.18);
  animation: buddy-widget-terminating-pulse 0.9s ease-in-out infinite;
}

.buddy-widget__terminate--terminating .el-icon {
  animation: buddy-widget-spin 0.82s linear infinite;
}

.buddy-widget__send:hover,
.buddy-widget__terminate:hover {
  border-color: rgba(154, 52, 18, 0.24);
  background: rgba(255, 248, 240, 0.92);
  transform: translateY(-1px);
}

.buddy-widget__terminate:hover {
  border-color: rgba(185, 28, 28, 0.34);
  background: rgba(254, 202, 202, 0.86);
}

.buddy-widget__send:disabled {
  cursor: not-allowed;
  opacity: 0.54;
  transform: none;
}

.buddy-widget__terminate:disabled {
  cursor: wait;
  opacity: 0.72;
  transform: none;
}

.buddy-widget__terminate--terminating:disabled {
  opacity: 1;
}

.buddy-widget__send:focus-visible,
.buddy-widget__terminate:focus-visible,
.buddy-widget__input:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(210, 162, 117, 0.3);
}

@keyframes buddy-widget-terminating-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 2px rgba(248, 113, 113, 0.16);
  }

  50% {
    box-shadow: 0 0 0 5px rgba(248, 113, 113, 0.3);
  }
}

@keyframes buddy-widget-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .buddy-widget__terminate--terminating,
  .buddy-widget__terminate--terminating .el-icon {
    animation: none;
  }
}
</style>
