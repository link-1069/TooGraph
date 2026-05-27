<template>
  <AppShell>
    <section class="scheduler-page">
      <header class="scheduler-page__header">
        <div>
          <div class="scheduler-page__eyebrow">{{ t("scheduler.eyebrow") }}</div>
          <h2 class="scheduler-page__title">{{ t("scheduler.title") }}</h2>
          <p class="scheduler-page__body">{{ t("scheduler.body") }}</p>
        </div>
        <div class="scheduler-page__header-actions">
          <ElButton
            type="primary"
            class="scheduler-page__action"
            data-virtual-affordance-id="scheduler.action.createJob"
            :data-virtual-affordance-label="t('scheduler.createJob')"
            data-virtual-affordance-role="button"
            data-virtual-affordance-zone="scheduler.header"
            data-virtual-affordance-actions="click"
            @click="openCreateDialog"
          >
            <ElIcon aria-hidden="true"><CirclePlus /></ElIcon>
            <span>{{ t("scheduler.createJob") }}</span>
          </ElButton>
          <ElButton
            class="scheduler-page__action"
            :loading="loading"
            data-virtual-affordance-id="scheduler.action.refresh"
            :data-virtual-affordance-label="t('scheduler.refresh')"
            data-virtual-affordance-role="button"
            data-virtual-affordance-zone="scheduler.header"
            data-virtual-affordance-actions="click"
            @click="loadSchedulerJobs"
          >
            <ElIcon aria-hidden="true"><Refresh /></ElIcon>
            <span>{{ t("scheduler.refresh") }}</span>
          </ElButton>
        </div>
      </header>

      <section class="scheduler-page__overview" :aria-label="t('scheduler.overviewLabel')">
        <article v-for="item in overview" :key="item.key" class="scheduler-page__metric">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>

      <article v-if="error" class="scheduler-page__notice">
        {{ t("common.failedToLoad", { error }) }}
      </article>
      <article v-if="actionError" class="scheduler-page__notice">
        {{ t("scheduler.actionFailed", { error: actionError }) }}
      </article>

      <section
        v-if="officialMaintenanceRecommendations.length > 0"
        class="scheduler-page__maintenance-guide"
        :aria-label="t('scheduler.officialMaintenanceTitle')"
      >
        <div class="scheduler-page__panel-heading">
          <div>
            <span class="scheduler-page__section-kicker">{{ t("scheduler.officialMaintenanceEyebrow") }}</span>
            <h3>{{ t("scheduler.officialMaintenanceTitle") }}</h3>
            <p class="scheduler-page__muted">{{ t("scheduler.officialMaintenanceBody") }}</p>
          </div>
        </div>
        <div class="scheduler-page__maintenance-list">
          <article
            v-for="recommendation in officialMaintenanceRecommendations"
            :key="recommendation.job_id"
            class="scheduler-page__maintenance-card"
          >
            <div>
              <span
                :class="recommendation.enabled ? 'scheduler-page__status scheduler-page__status--enabled' : 'scheduler-page__status'"
              >
                {{ recommendation.enabled ? t("scheduler.enabledStatus") : t("scheduler.disabledStatus") }}
              </span>
              <h4>{{ recommendation.title }}</h4>
              <p>{{ recommendation.description }}</p>
              <small>{{ recommendation.template_id }} · {{ recommendation.schedule }}</small>
            </div>
            <ElButton
              v-if="recommendation.action === 'enable'"
              type="primary"
              :loading="pendingActionKey === jobActionKey(recommendation.job_id, 'toggle')"
              :disabled="Boolean(pendingActionKey)"
              data-virtual-affordance-id="scheduler.officialMaintenance.enable"
              :data-virtual-affordance-label="t('scheduler.enable')"
              data-virtual-affordance-role="button"
              data-virtual-affordance-zone="scheduler.officialMaintenance"
              data-virtual-affordance-actions="click"
              @click="toggleJobEnabled(recommendation.job_id, true)"
            >
              {{ t("scheduler.enable") }}
            </ElButton>
            <ElButton
              v-else
              type="primary"
              :loading="pendingActionKey === jobActionKey(recommendation.job_id, 'run')"
              :disabled="Boolean(pendingActionKey)"
              data-virtual-affordance-id="scheduler.officialMaintenance.runNow"
              :data-virtual-affordance-label="t('scheduler.runNow')"
              data-virtual-affordance-role="button"
              data-virtual-affordance-zone="scheduler.officialMaintenance"
              data-virtual-affordance-actions="click"
              @click="runJobNow(recommendation.job_id)"
            >
              <ElIcon aria-hidden="true"><VideoPlay /></ElIcon>
              <span>{{ t("scheduler.runNow") }}</span>
            </ElButton>
          </article>
        </div>
      </section>

      <section class="scheduler-page__layout">
        <aside class="scheduler-page__job-panel" :aria-label="t('scheduler.jobList')">
          <div class="scheduler-page__panel-heading">
            <div>
              <span class="scheduler-page__section-kicker">{{ t("scheduler.jobList") }}</span>
              <h3>{{ t("scheduler.jobCount", { count: sortedJobs.length }) }}</h3>
            </div>
          </div>

          <article v-if="loading" class="scheduler-page__empty">{{ t("common.loading") }}</article>
          <article v-else-if="sortedJobs.length === 0" class="scheduler-page__empty">{{ t("scheduler.emptyJobs") }}</article>
          <div v-else class="scheduler-page__job-list">
            <button
              v-for="job in sortedJobs"
              :key="job.job_id"
              type="button"
              class="scheduler-page__job-card"
              :class="{ 'scheduler-page__job-card--active': selectedJobId === job.job_id }"
              @click="selectJob(job.job_id)"
            >
              <div class="scheduler-page__job-card-heading">
                <strong>{{ job.name || job.job_id }}</strong>
                <span :class="job.enabled ? 'scheduler-page__status scheduler-page__status--enabled' : 'scheduler-page__status'">
                  {{ job.enabled ? t("scheduler.enabledStatus") : t("scheduler.disabledStatus") }}
                </span>
              </div>
              <span class="scheduler-page__id" :title="job.template_id">{{ job.template_id }}</span>
              <div class="scheduler-page__badges">
                <span>{{ formatSchedule(job) }}</span>
                <span v-if="isOfficialJob(job)">{{ t("scheduler.official") }}</span>
              </div>
            </button>
          </div>
        </aside>

        <section class="scheduler-page__detail-panel" :aria-label="t('scheduler.selectedJob')">
          <article v-if="!selectedJob" class="scheduler-page__empty">{{ t("scheduler.noSelection") }}</article>
          <template v-else>
            <div class="scheduler-page__detail-heading">
              <div>
                <span class="scheduler-page__section-kicker">{{ selectedJob.job_id }}</span>
                <h3>{{ selectedJob.name || selectedJob.job_id }}</h3>
                <p class="scheduler-page__muted">{{ selectedJob.template_id }}</p>
              </div>
              <div class="scheduler-page__detail-actions">
                <label class="scheduler-page__switch-label">
                  <span>{{ selectedJob.enabled ? t("scheduler.enabledStatus") : t("scheduler.disabledStatus") }}</span>
                  <ElSwitch
                    :model-value="selectedJob.enabled"
                    :loading="pendingActionKey === jobActionKey(selectedJob.job_id, 'toggle')"
                    :disabled="Boolean(pendingActionKey)"
                    :aria-label="selectedJob.enabled ? t('scheduler.disable') : t('scheduler.enable')"
                    data-virtual-affordance-id="scheduler.job.toggle"
                    :data-virtual-affordance-label="selectedJob.enabled ? t('scheduler.disable') : t('scheduler.enable')"
                    data-virtual-affordance-role="switch"
                    data-virtual-affordance-zone="scheduler.job"
                    data-virtual-affordance-actions="toggle"
                    @change="(value: unknown) => toggleJobEnabled(selectedJob.job_id, Boolean(value))"
                  />
                </label>
                <ElButton
                  type="primary"
                  :loading="pendingActionKey === jobActionKey(selectedJob.job_id, 'run')"
                  :disabled="Boolean(pendingActionKey) || !selectedJob.enabled"
                  data-virtual-affordance-id="scheduler.job.runNow"
                  :data-virtual-affordance-label="t('scheduler.runNow')"
                  data-virtual-affordance-role="button"
                  data-virtual-affordance-zone="scheduler.job"
                  data-virtual-affordance-actions="click"
                  @click="runJobNow(selectedJob.job_id)"
                >
                  <ElIcon aria-hidden="true"><VideoPlay /></ElIcon>
                  <span>{{ t("scheduler.runNow") }}</span>
                </ElButton>
              </div>
            </div>

            <section class="scheduler-page__facts">
              <article>
                <span>{{ t("scheduler.schedule") }}</span>
                <strong>{{ formatSchedule(selectedJob) }}</strong>
              </article>
              <article>
                <span>{{ t("scheduler.nextRun") }}</span>
                <strong>{{ formatTimestamp(selectedJob.next_run_at) }}</strong>
              </article>
              <article>
                <span>{{ t("scheduler.lastRun") }}</span>
                <RouterLink
                  v-if="selectedJob.last_run_id"
                  class="scheduler-page__run-link"
                  :to="`/runs/${encodeURIComponent(selectedJob.last_run_id)}`"
                >
                  {{ shortId(selectedJob.last_run_id) }}
                </RouterLink>
                <strong v-else>{{ t("common.none") }}</strong>
              </article>
              <article>
                <span>{{ t("scheduler.timezone") }}</span>
                <strong>{{ selectedJob.timezone || "UTC" }}</strong>
              </article>
            </section>

            <section class="scheduler-page__detail-grid">
              <article class="scheduler-page__json-panel">
                <div class="scheduler-page__panel-heading">
                  <div>
                    <span class="scheduler-page__section-kicker">{{ t("scheduler.inputBindings") }}</span>
                    <h4>{{ t("scheduler.template") }} · {{ selectedJob.template_id }}</h4>
                  </div>
                </div>
                <pre>{{ formatJson(selectedJob.input_bindings) }}</pre>
              </article>
              <article class="scheduler-page__json-panel">
                <div class="scheduler-page__panel-heading">
                  <div>
                    <span class="scheduler-page__section-kicker">{{ t("scheduler.runtimeOverrides") }}</span>
                    <h4>{{ t("scheduler.metadata") }}</h4>
                  </div>
                </div>
                <pre>{{ formatJson({
                  runtime_overrides: selectedJob.runtime_overrides,
                  delivery_target: selectedJob.delivery_target,
                  retry_policy: selectedJob.retry_policy,
                  metadata: selectedJob.metadata,
                }) }}</pre>
              </article>
            </section>

            <section class="scheduler-page__runs">
              <div class="scheduler-page__panel-heading">
                <div>
                  <span class="scheduler-page__section-kicker">{{ t("scheduler.jobRuns") }}</span>
                  <h4>{{ t("scheduler.jobRuns") }}</h4>
                </div>
              </div>
              <article v-if="runsLoading" class="scheduler-page__empty">{{ t("common.loading") }}</article>
              <article v-else-if="sortedRuns.length === 0" class="scheduler-page__empty">{{ t("scheduler.emptyRuns") }}</article>
              <div v-else class="scheduler-page__run-list">
                <article v-for="run in sortedRuns" :key="run.job_run_id" class="scheduler-page__run-row">
                  <span :class="statusClass(run.status)">{{ normalizeJobRunStatus(run.status) }}</span>
                  <div>
                    <strong>{{ shortId(run.job_run_id) }}</strong>
                    <p>
                      <span>{{ t("scheduler.trigger") }}: {{ run.trigger_reason || t("common.none") }}</span>
                      <span>{{ formatTimestamp(run.started_at || run.created_at) }}</span>
                    </p>
                    <p v-if="run.error" class="scheduler-page__error">{{ run.error }}</p>
                  </div>
                  <RouterLink
                    v-if="run.run_id"
                    class="scheduler-page__run-link"
                    :to="`/runs/${encodeURIComponent(run.run_id)}`"
                  >
                    {{ t("scheduler.openRun") }}
                  </RouterLink>
                </article>
              </div>
            </section>
          </template>
        </section>
      </section>

      <ElDialog
        v-model="createDialogVisible"
        class="scheduler-page__dialog"
        :title="t('scheduler.createJobTitle')"
        width="680px"
      >
        <p class="scheduler-page__muted scheduler-page__dialog-body">{{ t("scheduler.createJobBody") }}</p>
        <ElForm class="scheduler-page__form" label-position="top">
          <ElFormItem :label="t('scheduler.jobName')">
            <ElInput v-model="createDraft.name" :placeholder="t('scheduler.jobNamePlaceholder')" />
          </ElFormItem>
          <ElFormItem :label="t('scheduler.templateSelect')" required>
            <ElSelect
              v-model="createDraft.template_id"
              class="scheduler-page__select toograph-select"
              filterable
              popper-class="toograph-select-popper"
              :loading="templatesLoading"
              :placeholder="t('scheduler.templatePlaceholder')"
              data-virtual-affordance-id="scheduler.create.template"
              :data-virtual-affordance-label="t('scheduler.templateSelect')"
              data-virtual-affordance-role="select"
              data-virtual-affordance-zone="scheduler.create"
              data-virtual-affordance-actions="select"
            >
              <ElOption
                v-for="template in templates"
                :key="template.template_id"
                :label="template.label || template.template_id"
                :value="template.template_id"
              >
                <span>{{ template.label || template.template_id }}</span>
                <small class="scheduler-page__option-id">{{ template.template_id }}</small>
              </ElOption>
            </ElSelect>
            <p v-if="!templatesLoading && templates.length === 0" class="scheduler-page__form-note">{{ t("scheduler.noTemplates") }}</p>
          </ElFormItem>
          <ElFormItem :label="t('scheduler.scheduleKind')">
            <ElSelect v-model="createDraft.schedule_kind" class="scheduler-page__select toograph-select" popper-class="toograph-select-popper">
              <ElOption v-for="option in scheduleKindOptions" :key="option.value" :label="option.label" :value="option.value" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem v-if="createDraft.schedule_kind !== 'manual'" :label="t('scheduler.scheduleExpr')">
            <ElInput v-model="createDraft.schedule_expr" :placeholder="t('scheduler.scheduleExprPlaceholder')" />
          </ElFormItem>
          <ElFormItem :label="t('scheduler.timezone')">
            <ElInput v-model="createDraft.timezone" :placeholder="t('scheduler.timezonePlaceholder')" />
          </ElFormItem>
          <ElFormItem :label="t('scheduler.inputBindings')">
            <ElInput v-model="createDraft.input_bindings_json" type="textarea" :rows="8" />
          </ElFormItem>
          <ElFormItem :label="t('scheduler.deliveryTarget')">
            <ElInput
              v-model="createDraft.delivery_target_json"
              type="textarea"
              :rows="4"
              :placeholder="t('scheduler.deliveryTargetPlaceholder')"
            />
          </ElFormItem>
          <label class="scheduler-page__switch-label scheduler-page__switch-label--form">
            <span>{{ t("scheduler.enabledOnCreate") }}</span>
            <ElSwitch v-model="createDraft.enabled" />
          </label>
        </ElForm>
        <template #footer>
          <div class="scheduler-page__dialog-actions">
            <ElButton @click="createDialogVisible = false">{{ t("common.cancel") }}</ElButton>
            <ElButton
              type="primary"
              :loading="creatingJob"
              :disabled="templates.length === 0"
              data-virtual-affordance-id="scheduler.create.submit"
              :data-virtual-affordance-label="t('scheduler.create')"
              data-virtual-affordance-role="button"
              data-virtual-affordance-zone="scheduler.create"
              data-virtual-affordance-actions="click"
              @click="submitCreateJob"
            >
              {{ t("scheduler.create") }}
            </ElButton>
          </div>
        </template>
      </ElDialog>
    </section>
  </AppShell>
</template>

<script setup lang="ts">
import { CirclePlus, Refresh, VideoPlay } from "@element-plus/icons-vue";
import { ElButton, ElDialog, ElForm, ElFormItem, ElIcon, ElInput, ElOption, ElSelect, ElSwitch } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { fetchTemplates } from "@/api/graphs";
import {
  createScheduledGraphJob,
  fetchScheduledGraphJobRuns,
  fetchScheduledGraphJobs,
  runScheduledGraphJob,
  setScheduledGraphJobEnabled,
} from "@/api/scheduler";
import AppShell from "@/layouts/AppShell.vue";
import type { TemplateRecord } from "@/types/node-system";
import type { ScheduledGraphJob, ScheduledGraphJobRun } from "@/types/scheduler";

import {
  buildOfficialSchedulerEnableRecommendations,
  buildDefaultScheduledGraphJobDraft,
  buildScheduledGraphJobPayload,
  buildSchedulerOverview,
  formatSchedule,
  normalizeJobRunStatus,
  sortScheduledGraphJobRuns,
  sortScheduledGraphJobs,
  type ScheduledGraphJobDraft,
} from "./schedulerPageModel.ts";

const { t, locale } = useI18n();
const jobs = ref<ScheduledGraphJob[]>([]);
const jobRuns = ref<ScheduledGraphJobRun[]>([]);
const selectedJobId = ref("");
const loading = ref(true);
const runsLoading = ref(false);
const templatesLoading = ref(false);
const creatingJob = ref(false);
const pendingActionKey = ref("");
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const createDialogVisible = ref(false);
const templates = ref<TemplateRecord[]>([]);
const createDraft = ref<ScheduledGraphJobDraft>(buildDefaultScheduledGraphJobDraft());

const sortedJobs = computed(() => sortScheduledGraphJobs(jobs.value));
const selectedJob = computed(() => jobs.value.find((job) => job.job_id === selectedJobId.value) ?? sortedJobs.value[0] ?? null);
const sortedRuns = computed(() => sortScheduledGraphJobRuns(jobRuns.value));
const officialMaintenanceRecommendations = computed(() => {
  locale.value;
  return buildOfficialSchedulerEnableRecommendations(jobs.value);
});
const overview = computed(() => {
  locale.value;
  return buildSchedulerOverview(jobs.value);
});
const scheduleKindOptions = computed(() => [
  { label: t("scheduler.manual"), value: "manual" },
  { label: t("scheduler.interval"), value: "interval" },
  { label: t("scheduler.cron"), value: "cron" },
]);

async function loadSchedulerJobs() {
  loading.value = true;
  try {
    const nextJobs = await fetchScheduledGraphJobs(true);
    const previousSelectedJobId = selectedJobId.value;
    jobs.value = nextJobs;
    if (!nextJobs.some((job) => job.job_id === selectedJobId.value)) {
      selectedJobId.value = sortScheduledGraphJobs(nextJobs)[0]?.job_id ?? "";
    }
    error.value = null;
    if (selectedJobId.value !== previousSelectedJobId) {
      return;
    }
    await loadSelectedJobRuns();
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : t("common.loading");
  } finally {
    loading.value = false;
  }
}

function selectJob(jobId: string) {
  selectedJobId.value = jobId;
}

async function loadSelectedJobRuns() {
  const jobId = selectedJobId.value;
  if (!jobId) {
    jobRuns.value = [];
    return;
  }
  runsLoading.value = true;
  try {
    jobRuns.value = await fetchScheduledGraphJobRuns(jobId);
    actionError.value = null;
  } catch (loadError) {
    actionError.value = loadError instanceof Error ? loadError.message : t("scheduler.actionFailedFallback");
  } finally {
    runsLoading.value = false;
  }
}

async function toggleJobEnabled(jobId: string, enabled: boolean) {
  pendingActionKey.value = jobActionKey(jobId, "toggle");
  try {
    const updatedJob = await setScheduledGraphJobEnabled(jobId, enabled);
    mergeJob(updatedJob);
    actionError.value = null;
  } catch (toggleError) {
    actionError.value = toggleError instanceof Error ? toggleError.message : t("scheduler.actionFailedFallback");
  } finally {
    pendingActionKey.value = "";
  }
}

async function openCreateDialog() {
  createDialogVisible.value = true;
  createDraft.value = buildDefaultScheduledGraphJobDraft(templates.value[0]?.template_id ?? "");
  await loadSchedulerTemplates();
}

async function loadSchedulerTemplates() {
  templatesLoading.value = true;
  try {
    templates.value = await fetchTemplates();
    if (!createDraft.value.template_id && templates.value[0]) {
      createDraft.value = {
        ...createDraft.value,
        template_id: templates.value[0].template_id,
      };
    }
    actionError.value = null;
  } catch (loadError) {
    actionError.value = loadError instanceof Error ? loadError.message : t("scheduler.actionFailedFallback");
  } finally {
    templatesLoading.value = false;
  }
}

async function submitCreateJob() {
  creatingJob.value = true;
  try {
    const payload = buildScheduledGraphJobPayload(createDraft.value);
    const createdJob = await createScheduledGraphJob(payload);
    mergeJob(createdJob);
    selectedJobId.value = createdJob.job_id;
    createDialogVisible.value = false;
    actionError.value = null;
  } catch (createError) {
    actionError.value = createError instanceof Error ? createError.message : t("scheduler.actionFailedFallback");
  } finally {
    creatingJob.value = false;
  }
}

async function runJobNow(jobId: string) {
  pendingActionKey.value = jobActionKey(jobId, "run");
  try {
    const result = await runScheduledGraphJob(jobId);
    mergeJob(result.job);
    if (selectedJobId.value === jobId) {
      jobRuns.value = [result.job_run, ...jobRuns.value.filter((run) => run.job_run_id !== result.job_run.job_run_id)];
    }
    actionError.value = null;
  } catch (runError) {
    actionError.value = runError instanceof Error ? runError.message : t("scheduler.actionFailedFallback");
  } finally {
    pendingActionKey.value = "";
  }
}

function mergeJob(job: ScheduledGraphJob) {
  jobs.value = [job, ...jobs.value.filter((existing) => existing.job_id !== job.job_id)];
}

function jobActionKey(jobId: string, action: string) {
  return `${jobId}:${action}`;
}

function isOfficialJob(job: ScheduledGraphJob) {
  return job.metadata?.source === "official_seed" || job.metadata?.source === "official";
}

function formatTimestamp(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return t("common.none");
  }
  const timestamp = Date.parse(normalized);
  if (!Number.isFinite(timestamp)) {
    return normalized;
  }
  return new Intl.DateTimeFormat(locale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

function shortId(value: string) {
  return value.length > 16 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function formatJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function statusClass(status: string) {
  const normalized = normalizeJobRunStatus(status);
  if (normalized === "completed") {
    return "scheduler-page__status scheduler-page__status--completed";
  }
  if (normalized === "failed" || normalized === "cancelled") {
    return "scheduler-page__status scheduler-page__status--failed";
  }
  if (normalized === "running" || normalized === "queued") {
    return "scheduler-page__status scheduler-page__status--running";
  }
  return "scheduler-page__status";
}

watch(selectedJobId, () => {
  void loadSelectedJobRuns();
});

onMounted(() => {
  void loadSchedulerJobs();
});
</script>

<style scoped>
.scheduler-page {
  min-height: 100%;
  display: grid;
  gap: 18px;
  padding: 24px;
}

.scheduler-page__header,
.scheduler-page__overview,
.scheduler-page__maintenance-guide,
.scheduler-page__job-panel,
.scheduler-page__detail-panel {
  background: var(--toograph-glass-specular), var(--toograph-glass-lens), var(--toograph-glass-bg-strong);
  border: 1px solid rgba(120, 53, 15, 0.1);
  box-shadow: 0 18px 46px rgba(30, 41, 59, 0.08);
  backdrop-filter: blur(18px) saturate(1.15);
}

.scheduler-page__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 22px;
  border-radius: 8px;
}

.scheduler-page__eyebrow,
.scheduler-page__section-kicker {
  color: var(--toograph-accent-strong);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.scheduler-page__title {
  margin: 4px 0 8px;
  color: var(--toograph-text-strong);
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  letter-spacing: 0;
}

.scheduler-page__body,
.scheduler-page__muted,
.scheduler-page__run-row p {
  margin: 0;
  color: var(--toograph-text-muted);
  line-height: 1.65;
}

.scheduler-page__header-actions,
.scheduler-page__detail-actions,
.scheduler-page__badges,
.scheduler-page__run-row p {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.scheduler-page__overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border-radius: 8px;
}

.scheduler-page__metric {
  min-width: 0;
  padding: 16px;
  background: rgba(255, 255, 255, 0.62);
}

.scheduler-page__metric span,
.scheduler-page__facts span {
  display: block;
  color: var(--toograph-text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.scheduler-page__metric strong,
.scheduler-page__facts strong {
  display: block;
  margin-top: 5px;
  overflow-wrap: anywhere;
  color: var(--toograph-text-strong);
  font-size: 1.14rem;
}

.scheduler-page__maintenance-guide {
  display: grid;
  gap: 14px;
  border-radius: 8px;
  padding: 16px;
}

.scheduler-page__maintenance-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.scheduler-page__maintenance-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  min-width: 0;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 252, 247, 0.76);
}

.scheduler-page__maintenance-card h4 {
  margin: 8px 0 0;
  color: var(--toograph-text-strong);
  font-size: 1rem;
  line-height: 1.25;
}

.scheduler-page__maintenance-card p,
.scheduler-page__maintenance-card small {
  display: block;
  margin: 7px 0 0;
  color: var(--toograph-text-muted);
  font-size: 0.84rem;
  line-height: 1.5;
}

.scheduler-page__notice,
.scheduler-page__empty {
  padding: 16px;
  border: 1px solid rgba(180, 83, 9, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--toograph-text-muted);
}

.scheduler-page__layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.34fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.scheduler-page__job-panel,
.scheduler-page__detail-panel {
  min-width: 0;
  border-radius: 8px;
  padding: 16px;
}

.scheduler-page__panel-heading,
.scheduler-page__detail-heading,
.scheduler-page__job-card-heading,
.scheduler-page__run-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.scheduler-page__panel-heading h3,
.scheduler-page__detail-heading h3,
.scheduler-page__json-panel h4,
.scheduler-page__runs h4 {
  margin: 3px 0 0;
  color: var(--toograph-text-strong);
  letter-spacing: 0;
}

.scheduler-page__job-list,
.scheduler-page__detail-grid,
.scheduler-page__run-list,
.scheduler-page__runs {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.scheduler-page__job-card,
.scheduler-page__json-panel,
.scheduler-page__facts article,
.scheduler-page__run-row {
  min-width: 0;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.68);
}

.scheduler-page__job-card {
  display: grid;
  gap: 8px;
  width: 100%;
  padding: 13px;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.scheduler-page__job-card:hover,
.scheduler-page__job-card--active {
  border-color: rgba(154, 52, 18, 0.22);
  background: rgba(255, 255, 255, 0.86);
}

.scheduler-page__id {
  display: block;
  min-width: 0;
  overflow: hidden;
  color: var(--toograph-text-muted);
  font-family: var(--toograph-font-mono);
  font-size: 0.76rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scheduler-page__badges span,
.scheduler-page__status {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 999px;
  padding: 3px 9px;
  background: rgba(255, 255, 255, 0.58);
  color: var(--toograph-text-muted);
  font-size: 0.76rem;
  font-weight: 800;
  line-height: 1.2;
}

.scheduler-page__status--enabled,
.scheduler-page__status--completed {
  border-color: rgba(22, 101, 52, 0.18);
  background: rgba(220, 252, 231, 0.76);
  color: #166534;
}

.scheduler-page__status--running {
  border-color: rgba(37, 99, 235, 0.18);
  background: rgba(219, 234, 254, 0.78);
  color: #1d4ed8;
}

.scheduler-page__status--failed {
  border-color: rgba(185, 28, 28, 0.18);
  background: rgba(254, 226, 226, 0.78);
  color: #991b1b;
}

.scheduler-page__switch-label {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 999px;
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.58);
  color: var(--toograph-text-muted);
  font-size: 0.78rem;
  font-weight: 800;
}

.scheduler-page__facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.scheduler-page__facts article {
  padding: 12px;
}

.scheduler-page__detail-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.scheduler-page__json-panel {
  padding: 14px;
}

.scheduler-page__json-panel pre {
  overflow: auto;
  max-height: 320px;
  margin: 12px 0 0;
  border-radius: 8px;
  padding: 12px;
  background: rgba(15, 23, 42, 0.92);
  color: #e5e7eb;
  font-family: var(--toograph-font-mono);
  font-size: 0.78rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.scheduler-page__run-row {
  align-items: center;
  padding: 12px;
}

.scheduler-page__run-row > div {
  min-width: 0;
  flex: 1;
}

.scheduler-page__run-row strong {
  overflow-wrap: anywhere;
  color: var(--toograph-text-strong);
}

.scheduler-page__run-link {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  border: 1px solid rgba(120, 53, 15, 0.14);
  border-radius: 999px;
  padding: 5px 10px;
  color: var(--toograph-accent-strong);
  font-size: 0.78rem;
  font-weight: 800;
  text-decoration: none;
}

.scheduler-page__run-link:hover {
  background: rgba(254, 243, 199, 0.72);
}

.scheduler-page__error {
  color: #991b1b;
}

.scheduler-page__dialog-body {
  margin-bottom: 14px;
}

.scheduler-page__form {
  display: grid;
  gap: 2px;
}

.scheduler-page__form :deep(.el-select) {
  width: 100%;
}

.scheduler-page__form-note {
  margin: 8px 0 0;
  color: var(--toograph-text-muted);
  font-size: 0.82rem;
}

.scheduler-page__option-id {
  display: block;
  overflow: hidden;
  color: var(--toograph-text-muted);
  font-family: var(--toograph-font-mono);
  font-size: 0.72rem;
  text-overflow: ellipsis;
}

.scheduler-page__switch-label--form {
  width: fit-content;
}

.scheduler-page__dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

:global(.scheduler-page__dialog.el-dialog) {
  max-width: calc(100vw - 32px);
  border: 1px solid rgba(120, 53, 15, 0.12);
  border-radius: 8px;
  background: rgba(255, 251, 246, 0.98);
  box-shadow: 0 28px 80px rgba(30, 41, 59, 0.24);
}

:global(.scheduler-page__dialog.el-dialog .el-dialog__header) {
  padding: 20px 22px 8px;
}

:global(.scheduler-page__dialog.el-dialog .el-dialog__body) {
  padding: 8px 22px 12px;
}

:global(.scheduler-page__dialog.el-dialog .el-dialog__footer) {
  padding: 12px 22px 20px;
}

:global(.scheduler-page__dialog.el-dialog .el-dialog__title) {
  color: var(--toograph-text-strong);
  font-weight: 850;
}

:global(.scheduler-page__dialog.el-dialog .el-input__wrapper),
:global(.scheduler-page__dialog.el-dialog .el-textarea__inner) {
  background: rgba(255, 255, 255, 0.94);
  color: var(--toograph-text-strong);
}

@media (max-width: 1100px) {
  .scheduler-page__layout,
  .scheduler-page__detail-grid,
  .scheduler-page__maintenance-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .scheduler-page {
    padding: 16px;
  }

  .scheduler-page__header,
  .scheduler-page__detail-heading,
  .scheduler-page__maintenance-card,
  .scheduler-page__run-row {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .scheduler-page__overview,
  .scheduler-page__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .scheduler-page__detail-actions,
  .scheduler-page__detail-actions > * {
    width: 100%;
  }
}
</style>
