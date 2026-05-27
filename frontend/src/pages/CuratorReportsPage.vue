<template>
  <AppShell>
    <section class="curator-reports-page">
      <header class="curator-reports-page__header">
        <div>
          <div class="curator-reports-page__eyebrow">{{ t("curatorReports.eyebrow") }}</div>
          <h2 class="curator-reports-page__title">{{ t("curatorReports.title") }}</h2>
          <p class="curator-reports-page__body">{{ t("curatorReports.body") }}</p>
        </div>
        <ElButton
          class="curator-reports-page__refresh"
          :loading="loading"
          data-virtual-affordance-id="curatorReports.action.refresh"
          :data-virtual-affordance-label="t('curatorReports.refresh')"
          data-virtual-affordance-role="button"
          data-virtual-affordance-zone="curatorReports.header"
          data-virtual-affordance-actions="click"
          @click="loadReports"
        >
          <ElIcon aria-hidden="true"><Refresh /></ElIcon>
          <span>{{ loading ? t("curatorReports.refreshing") : t("curatorReports.refresh") }}</span>
        </ElButton>
      </header>

      <section class="curator-reports-page__overview" :aria-label="t('curatorReports.overviewLabel')">
        <article v-for="metric in overview" :key="metric.key" class="curator-reports-page__metric">
          <span>{{ t(metric.labelKey) }}</span>
          <strong>{{ metric.value || t("common.none") }}</strong>
        </article>
      </section>

      <article v-if="error" class="curator-reports-page__notice">{{ t("common.failedToLoad", { error }) }}</article>

      <section class="curator-reports-page__workspace">
        <aside class="curator-reports-page__list" :aria-label="t('curatorReports.listLabel')">
          <div class="curator-reports-page__panel-heading">
            <div>
              <span>{{ t("curatorReports.listLabel") }}</span>
              <h3>{{ t("curatorReports.reportCount", { count: reportItems.length }) }}</h3>
            </div>
          </div>

          <article v-if="loading" class="curator-reports-page__empty">{{ t("common.loading") }}</article>
          <article v-else-if="reportItems.length === 0" class="curator-reports-page__empty">
            <p>{{ t("curatorReports.empty") }}</p>
            <RouterLink to="/scheduler">{{ t("curatorReports.openScheduler") }}</RouterLink>
          </article>
          <div v-else class="curator-reports-page__run-list">
            <button
              v-for="report in reportItems"
              :key="report.runId"
              type="button"
              class="curator-reports-page__run"
              :class="{ 'curator-reports-page__run--active': selectedRunId === report.runId }"
              @click="selectedRunId = report.runId"
            >
              <span :class="statusClass(report.status)">{{ report.status }}</span>
              <strong>{{ report.graphName || report.runId }}</strong>
              <small>{{ report.runId }}</small>
              <time>{{ formatDateTime(report.startedAt) }}</time>
            </button>
          </div>
        </aside>

        <article class="curator-reports-page__detail" :aria-label="t('curatorReports.detailLabel')">
          <template v-if="selectedReportDetail">
            <header class="curator-reports-page__detail-header">
              <div>
                <span class="curator-reports-page__id">{{ selectedReportDetail.runId }}</span>
                <h3>{{ selectedReportDetail.graphName || t("curatorReports.title") }}</h3>
              </div>
              <RouterLink :to="runHref(selectedReportDetail.runId)" class="curator-reports-page__run-link">
                {{ t("curatorReports.openRun") }}
              </RouterLink>
            </header>

            <section class="curator-reports-page__facts">
              <div>
                <span>{{ t("common.status") }}</span>
                <strong>{{ selectedReportDetail.status }}</strong>
              </div>
              <div>
                <span>{{ t("common.startedAt") }}</span>
                <strong>{{ formatDateTime(selectedReportDetail.startedAt) }}</strong>
              </div>
              <div>
                <span>{{ t("curatorReports.candidateCount") }}</span>
                <strong>{{ selectedReportDetail.candidateCount }}</strong>
              </div>
              <div>
                <span>{{ t("curatorReports.healthScore") }}</span>
                <strong>{{ selectedReportDetail.healthScore || t("common.none") }}</strong>
              </div>
            </section>

            <section class="curator-reports-page__report">
              <h4>{{ t("curatorReports.report") }}</h4>
              <pre>{{ selectedReportDetail.reportMarkdown || t("curatorReports.emptyReport") }}</pre>
            </section>

            <div class="curator-reports-page__json-grid">
              <section>
                <h4>{{ t("curatorReports.healthReport") }}</h4>
                <pre>{{ JSON.stringify(selectedReportDetail.healthReport, null, 2) }}</pre>
              </section>
              <section>
                <h4>{{ t("curatorReports.improvementCandidates") }}</h4>
                <pre>{{ JSON.stringify(selectedReportDetail.improvementCandidates, null, 2) }}</pre>
              </section>
              <section class="curator-reports-page__json-wide">
                <h4>{{ t("curatorReports.schedulerRecommendation") }}</h4>
                <pre>{{ JSON.stringify(selectedReportDetail.schedulerRecommendation, null, 2) }}</pre>
              </section>
            </div>
          </template>
          <article v-else-if="detailLoading" class="curator-reports-page__empty">{{ t("common.loadingRun") }}</article>
          <article v-else-if="detailError" class="curator-reports-page__notice">{{ t("common.failedToLoad", { error: detailError }) }}</article>
          <article v-else class="curator-reports-page__empty">{{ t("curatorReports.noSelection") }}</article>
        </article>
      </section>
    </section>
  </AppShell>
</template>

<script setup lang="ts">
import { Refresh } from "@element-plus/icons-vue";
import { ElButton, ElIcon } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { fetchRun, fetchRuns } from "@/api/runs";
import AppShell from "@/layouts/AppShell.vue";
import type { RunDetail, RunSummary } from "@/types/run";

import {
  buildCuratorReportDetail,
  buildCuratorReportItems,
  buildCuratorReportOverview,
  CURATOR_REPORT_TEMPLATE_ID,
} from "./curatorReportsPageModel.ts";

const { t, locale } = useI18n();

const runs = ref<RunSummary[]>([]);
const selectedRun = ref<RunDetail | null>(null);
const selectedRunId = ref("");
const loading = ref(false);
const detailLoading = ref(false);
const error = ref("");
const detailError = ref("");

const reportItems = computed(() => buildCuratorReportItems(runs.value));
const overview = computed(() => {
  locale.value;
  return buildCuratorReportOverview(runs.value);
});
const selectedReportDetail = computed(() => selectedRun.value ? buildCuratorReportDetail(selectedRun.value) : null);

watch(reportItems, (items) => {
  if (items.some((item) => item.runId === selectedRunId.value)) {
    return;
  }
  selectedRunId.value = items[0]?.runId ?? "";
}, { immediate: true });

watch(selectedRunId, (runId) => {
  if (!runId) {
    selectedRun.value = null;
    return;
  }
  void loadSelectedRun(runId);
});

onMounted(() => {
  void loadReports();
});

async function loadReports() {
  loading.value = true;
  error.value = "";
  try {
    runs.value = await fetchRuns({ templateId: CURATOR_REPORT_TEMPLATE_ID, includeInternal: true });
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : String(loadError);
  } finally {
    loading.value = false;
  }
}

async function loadSelectedRun(runId: string) {
  detailLoading.value = true;
  detailError.value = "";
  selectedRun.value = null;
  try {
    const nextRun = await fetchRun(selectedRunId.value);
    if (selectedRunId.value === runId) {
      selectedRun.value = nextRun;
    }
  } catch (loadError) {
    if (selectedRunId.value === runId) {
      selectedRun.value = null;
      detailError.value = loadError instanceof Error ? loadError.message : String(loadError);
    }
  } finally {
    if (selectedRunId.value === runId) {
      detailLoading.value = false;
    }
  }
}

function runHref(runId: string) {
  return `/runs/${encodeURIComponent(runId)}`;
}

function formatDateTime(value: string) {
  if (!value) {
    return t("common.none");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function statusClass(status: string) {
  return ["curator-reports-page__status", `curator-reports-page__status--${status || "unknown"}`];
}
</script>

<style scoped>
.curator-reports-page {
  --curator-panel-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
  --curator-card-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
  box-sizing: border-box;
  width: min(1360px, 100%);
  min-width: 0;
  margin: 0 auto;
  padding: 32px 28px 48px;
  color: #28140f;
}

.curator-reports-page__header,
.curator-reports-page__overview,
.curator-reports-page__workspace {
  min-width: 0;
}

.curator-reports-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.curator-reports-page__eyebrow {
  margin-bottom: 8px;
  color: #9a3412;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.curator-reports-page__title {
  margin: 0;
  color: #1f130f;
  font-size: clamp(1.7rem, 2vw, 2.3rem);
  line-height: 1.1;
  letter-spacing: 0;
}

.curator-reports-page__body {
  max-width: 760px;
  margin: 10px 0 0;
  color: rgba(72, 45, 34, 0.72);
  line-height: 1.6;
}

.curator-reports-page__refresh {
  flex: 0 0 auto;
}

.curator-reports-page__overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.curator-reports-page__metric,
.curator-reports-page__list,
.curator-reports-page__detail {
  border: 1px solid rgba(120, 53, 15, 0.12);
  border-radius: 8px;
  background: rgba(255, 252, 248, 0.88);
  box-shadow: var(--curator-card-shadow);
}

.curator-reports-page__metric {
  padding: 14px 16px;
}

.curator-reports-page__metric span,
.curator-reports-page__facts span,
.curator-reports-page__panel-heading span {
  display: block;
  color: rgba(72, 45, 34, 0.62);
  font-size: 0.78rem;
  font-weight: 700;
}

.curator-reports-page__metric strong {
  display: block;
  margin-top: 8px;
  min-width: 0;
  overflow-wrap: anywhere;
  color: #1f130f;
  font-size: 1.35rem;
}

.curator-reports-page__notice,
.curator-reports-page__empty {
  border: 1px solid rgba(120, 53, 15, 0.12);
  border-radius: 8px;
  padding: 18px;
  background: rgba(255, 252, 248, 0.82);
  color: rgba(72, 45, 34, 0.72);
}

.curator-reports-page__empty {
  display: grid;
  gap: 8px;
  justify-items: start;
}

.curator-reports-page__empty p {
  margin: 0;
}

.curator-reports-page__empty a,
.curator-reports-page__run-link {
  color: #9a3412;
  font-weight: 700;
  text-decoration: none;
}

.curator-reports-page__workspace {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.curator-reports-page__list,
.curator-reports-page__detail {
  min-width: 0;
  padding: 18px;
}

.curator-reports-page__panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.curator-reports-page__panel-heading h3 {
  margin: 4px 0 0;
  color: #1f130f;
  font-size: 1.05rem;
}

.curator-reports-page__run-list {
  display: grid;
  gap: 8px;
}

.curator-reports-page__run {
  appearance: none;
  display: grid;
  width: 100%;
  gap: 6px;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.68);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease;
}

.curator-reports-page__run:hover,
.curator-reports-page__run--active {
  border-color: rgba(154, 52, 18, 0.24);
  background: rgba(255, 248, 240, 0.88);
  box-shadow: 0 10px 24px rgba(154, 52, 18, 0.08);
}

.curator-reports-page__run strong,
.curator-reports-page__run small,
.curator-reports-page__run time {
  min-width: 0;
  overflow-wrap: anywhere;
}

.curator-reports-page__run small,
.curator-reports-page__run time {
  color: rgba(72, 45, 34, 0.58);
}

.curator-reports-page__status {
  width: fit-content;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(71, 85, 105, 0.1);
  color: #334155;
  font-size: 0.72rem;
  font-weight: 800;
}

.curator-reports-page__status--completed {
  background: rgba(21, 128, 61, 0.12);
  color: #166534;
}

.curator-reports-page__status--failed {
  background: rgba(185, 28, 28, 0.12);
  color: #991b1b;
}

.curator-reports-page__detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.curator-reports-page__id {
  display: block;
  color: #9a3412;
  font-size: 0.78rem;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.curator-reports-page__detail-header h3 {
  margin: 6px 0 0;
  color: #1f130f;
  font-size: 1.35rem;
}

.curator-reports-page__facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.curator-reports-page__facts div {
  min-width: 0;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.58);
}

.curator-reports-page__facts strong {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
}

.curator-reports-page__report,
.curator-reports-page__json-grid section {
  min-width: 0;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.58);
}

.curator-reports-page__report {
  margin-bottom: 14px;
}

.curator-reports-page__report h4,
.curator-reports-page__json-grid h4 {
  margin: 0 0 10px;
  color: #1f130f;
  font-size: 0.95rem;
}

.curator-reports-page__report pre,
.curator-reports-page__json-grid pre {
  max-height: 520px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #2f1d17;
  font: 0.86rem/1.55 var(--toograph-font-mono);
}

.curator-reports-page__json-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.curator-reports-page__json-wide {
  grid-column: 1 / -1;
}

@media (max-width: 1100px) {
  .curator-reports-page__workspace,
  .curator-reports-page__overview,
  .curator-reports-page__facts {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .curator-reports-page {
    padding: 24px 0 36px;
  }

  .curator-reports-page__header,
  .curator-reports-page__detail-header {
    display: grid;
  }

  .curator-reports-page__overview,
  .curator-reports-page__workspace,
  .curator-reports-page__facts,
  .curator-reports-page__json-grid {
    grid-template-columns: 1fr;
  }

  .curator-reports-page__json-wide {
    grid-column: auto;
  }
}
</style>
