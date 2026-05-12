<template>
  <AppShell>
    <section class="knowledge-page">
      <header class="knowledge-page__header">
        <div>
          <div class="knowledge-page__eyebrow">{{ t("knowledge.eyebrow") }}</div>
          <h2 class="knowledge-page__title">{{ t("knowledge.title") }}</h2>
          <p class="knowledge-page__body">{{ t("knowledge.body") }}</p>
        </div>
        <div class="knowledge-page__header-actions">
          <ElButton
            :loading="loading"
            data-virtual-affordance-id="knowledge.action.refresh"
            :data-virtual-affordance-label="t('knowledge.refresh')"
            data-virtual-affordance-role="button"
            data-virtual-affordance-zone="knowledge.header"
            data-virtual-affordance-actions="click"
            @click="loadKnowledgeBases"
          >
            <ElIcon aria-hidden="true"><Refresh /></ElIcon>
            <span>{{ t("knowledge.refresh") }}</span>
          </ElButton>
          <ElButton
            type="primary"
            :loading="importing"
            data-virtual-affordance-id="knowledge.action.importOfficial"
            :data-virtual-affordance-label="t('knowledge.importOfficial')"
            data-virtual-affordance-role="button"
            data-virtual-affordance-zone="knowledge.header"
            data-virtual-affordance-actions="click"
            @click="importOfficial"
          >
            <ElIcon aria-hidden="true"><Upload /></ElIcon>
            <span>{{ t("knowledge.importOfficial") }}</span>
          </ElButton>
        </div>
      </header>

      <section class="knowledge-page__overview" :aria-label="t('knowledge.overviewLabel')">
        <article v-for="item in overview" :key="item.key" class="knowledge-page__metric">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>

      <article v-if="error" class="knowledge-page__notice">
        {{ t("common.failedToLoad", { error }) }}
      </article>
      <article v-if="actionError" class="knowledge-page__notice">
        {{ t("knowledge.actionFailed", { error: actionError }) }}
      </article>
      <article v-if="actionMessage" class="knowledge-page__notice knowledge-page__notice--success">
        {{ actionMessage }}
      </article>

      <section class="knowledge-page__layout">
        <aside class="knowledge-page__base-panel" :aria-label="t('knowledge.baseList')">
          <div class="knowledge-page__panel-heading">
            <div>
              <span class="knowledge-page__section-kicker">{{ t("knowledge.basesMetric") }}</span>
              <h3>{{ t("knowledge.baseList") }}</h3>
            </div>
            <span>{{ t("knowledge.baseCount", { count: baseRows.length }) }}</span>
          </div>

          <article v-if="loading" class="knowledge-page__empty">{{ t("common.loading") }}</article>
          <article v-else-if="baseRows.length === 0" class="knowledge-page__empty">
            <p>{{ t("knowledge.noBases") }}</p>
            <ElButton type="primary" :loading="importing" @click="importOfficial">
              <ElIcon aria-hidden="true"><Upload /></ElIcon>
              <span>{{ t("knowledge.importOfficial") }}</span>
            </ElButton>
          </article>
          <div v-else class="knowledge-page__base-list">
            <article
              v-for="row in baseRows"
              :key="row.id"
              class="knowledge-page__base-card"
              :class="{ 'knowledge-page__base-card--active': selectedKnowledgeBase === row.id }"
            >
              <button type="button" class="knowledge-page__base-select" @click="selectedKnowledgeBase = row.id">
                <span class="knowledge-page__base-kind">{{ row.sourceKind || t("common.none") }}</span>
                <strong>{{ row.title }}</strong>
                <small v-if="row.description">{{ row.description }}</small>
              </button>
              <div class="knowledge-page__base-meta">
                <span>{{ t("knowledge.documents", { count: row.documentCount }) }}</span>
                <span>{{ t("knowledge.chunks", { count: row.chunkCount }) }}</span>
                <span>{{ row.version || t("common.none") }}</span>
              </div>
              <div class="knowledge-page__base-footer">
                <span :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
                <span class="knowledge-page__embedding-label">{{ row.embeddingLabel }}</span>
              </div>
              <div class="knowledge-page__base-actions">
                <ElButton
                  size="small"
                  :loading="rebuildingBaseId === row.id"
                  :disabled="Boolean(rebuildingBaseId || deletingBaseId)"
                  :data-virtual-affordance-id="`knowledge.base.${row.id}.rebuild`"
                  :data-virtual-affordance-label="t('knowledge.rebuild')"
                  data-virtual-affordance-role="button"
                  data-virtual-affordance-zone="knowledge.base"
                  data-virtual-affordance-actions="click"
                  @click="rebuildBase(row.id)"
                >
                  <ElIcon aria-hidden="true"><Refresh /></ElIcon>
                  <span>{{ t("knowledge.rebuild") }}</span>
                </ElButton>
                <ElPopconfirm
                  :title="t('knowledge.deleteConfirm', { name: row.title })"
                  :width="280"
                  :confirm-button-text="t('knowledge.delete')"
                  confirm-button-type="danger"
                  :cancel-button-text="t('common.cancel')"
                  @confirm="deleteBase(row.id)"
                >
                  <template #reference>
                    <ElButton
                      size="small"
                      type="danger"
                      plain
                      :loading="deletingBaseId === row.id"
                      :disabled="Boolean(rebuildingBaseId || deletingBaseId)"
                      :data-virtual-affordance-id="`knowledge.base.${row.id}.delete`"
                      :data-virtual-affordance-label="t('knowledge.delete')"
                      data-virtual-affordance-role="button"
                      data-virtual-affordance-zone="knowledge.base"
                      data-virtual-affordance-actions="click"
                    >
                      <ElIcon aria-hidden="true"><Delete /></ElIcon>
                      <span>{{ t("knowledge.delete") }}</span>
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </article>
          </div>
        </aside>

        <section class="knowledge-page__search-panel" :aria-label="t('knowledge.searchResults')">
          <div class="knowledge-page__panel-heading">
            <div>
              <span class="knowledge-page__section-kicker">{{ selectedKnowledgeBase || t("common.none") }}</span>
              <h3>{{ t("knowledge.searchResults") }}</h3>
            </div>
          </div>

          <div class="knowledge-page__search-bar">
            <ElSelect
              v-model="selectedKnowledgeBase"
              class="knowledge-page__base-picker toograph-select"
              popper-class="toograph-select-popper"
              :placeholder="t('knowledge.selectedBase')"
              :aria-label="t('knowledge.selectedBase')"
            >
              <ElOption v-for="row in baseRows" :key="row.id" :label="row.title" :value="row.id" />
            </ElSelect>
            <ElInput
              v-model="query"
              :placeholder="t('knowledge.searchPlaceholder')"
              :aria-label="t('knowledge.searchLabel')"
              clearable
              @keyup.enter="runSearch"
            />
            <ElButton
              type="primary"
              :loading="searching"
              :disabled="baseRows.length === 0"
              data-virtual-affordance-id="knowledge.action.search"
              :data-virtual-affordance-label="t('knowledge.search')"
              data-virtual-affordance-role="button"
              data-virtual-affordance-zone="knowledge.search"
              data-virtual-affordance-actions="click"
              @click="runSearch"
            >
              <ElIcon aria-hidden="true"><Search /></ElIcon>
              <span>{{ t("knowledge.search") }}</span>
            </ElButton>
          </div>

          <article v-if="searchRows.length === 0 && !searching" class="knowledge-page__empty">
            <p>{{ t("knowledge.noResults") }}</p>
            <span>{{ t("knowledge.noResultsHint") }}</span>
          </article>
          <div v-else class="knowledge-page__result-list">
            <article v-for="row in searchRows" :key="row.key" class="knowledge-page__result-card">
              <div class="knowledge-page__result-heading">
                <div>
                  <span class="knowledge-page__citation-id">{{ row.citationId }}</span>
                  <h4>{{ row.title }}</h4>
                </div>
                <span class="knowledge-page__score">{{ t("knowledge.score") }} {{ row.scoreLabel }}</span>
              </div>
              <p>{{ row.summary || t("common.noSummary") }}</p>
              <div class="knowledge-page__result-meta">
                <span>{{ t("knowledge.chunk") }} {{ row.chunkId || t("common.none") }}</span>
                <span>{{ t("knowledge.section") }} {{ row.section || t("common.none") }}</span>
                <span>{{ row.retrievalLabel }}</span>
              </div>
              <div class="knowledge-page__source-line">
                <span>{{ t("knowledge.source") }} {{ row.source || t("common.none") }}</span>
                <a v-if="row.url" :href="row.url" target="_blank" rel="noreferrer">{{ t("knowledge.sourceUrl") }}</a>
              </div>
            </article>
          </div>
        </section>
      </section>
    </section>
  </AppShell>
</template>

<script setup lang="ts">
import { Delete, Refresh, Search, Upload } from "@element-plus/icons-vue";
import { ElButton, ElIcon, ElInput, ElOption, ElPopconfirm, ElSelect } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import {
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  importOfficialKnowledgeBases,
  rebuildKnowledgeBase,
  searchKnowledge,
} from "@/api/knowledge";
import AppShell from "@/layouts/AppShell.vue";
import type { KnowledgeBaseRecord, KnowledgeSearchResult } from "@/types/knowledge";

import {
  buildKnowledgeBaseRows,
  buildKnowledgeOverview,
  buildKnowledgeSearchRows,
  chooseInitialKnowledgeBase,
} from "./knowledgePageModel.ts";

const { t, locale } = useI18n();
const bases = ref<KnowledgeBaseRecord[]>([]);
const results = ref<KnowledgeSearchResult[]>([]);
const selectedKnowledgeBase = ref("");
const query = ref("");
const loading = ref(true);
const searching = ref(false);
const importing = ref(false);
const rebuildingBaseId = ref("");
const deletingBaseId = ref("");
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const actionMessage = ref("");

const overview = computed(() => {
  locale.value;
  return buildKnowledgeOverview(bases.value);
});
const baseRows = computed(() => {
  locale.value;
  return buildKnowledgeBaseRows(bases.value);
});
const searchRows = computed(() => buildKnowledgeSearchRows(results.value));

async function loadKnowledgeBases() {
  loading.value = true;
  try {
    const nextBases = await fetchKnowledgeBases();
    bases.value = nextBases;
    selectedKnowledgeBase.value = chooseInitialKnowledgeBase(nextBases, selectedKnowledgeBase.value);
    error.value = null;
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : t("common.loading");
  } finally {
    loading.value = false;
  }
}

async function importOfficial() {
  importing.value = true;
  try {
    await importOfficialKnowledgeBases();
    actionError.value = null;
    actionMessage.value = t("knowledge.importComplete");
    await loadKnowledgeBases();
  } catch (importError) {
    actionError.value = importError instanceof Error ? importError.message : t("knowledge.actionFailedFallback");
    actionMessage.value = "";
  } finally {
    importing.value = false;
  }
}

async function rebuildBase(baseId: string) {
  rebuildingBaseId.value = baseId;
  try {
    await rebuildKnowledgeBase(baseId);
    actionError.value = null;
    actionMessage.value = t("knowledge.rebuildComplete");
    await loadKnowledgeBases();
  } catch (rebuildError) {
    actionError.value = rebuildError instanceof Error ? rebuildError.message : t("knowledge.actionFailedFallback");
    actionMessage.value = "";
  } finally {
    rebuildingBaseId.value = "";
  }
}

async function deleteBase(baseId: string) {
  deletingBaseId.value = baseId;
  try {
    await deleteKnowledgeBase(baseId);
    if (selectedKnowledgeBase.value === baseId) {
      selectedKnowledgeBase.value = "";
      results.value = [];
    }
    actionError.value = null;
    actionMessage.value = t("knowledge.deleteComplete", { name: baseId });
    await loadKnowledgeBases();
  } catch (deleteError) {
    actionError.value = deleteError instanceof Error ? deleteError.message : t("knowledge.actionFailedFallback");
    actionMessage.value = "";
  } finally {
    deletingBaseId.value = "";
  }
}

async function runSearch() {
  const trimmedQuery = query.value.trim();
  if (!trimmedQuery) {
    actionError.value = t("knowledge.queryRequired");
    actionMessage.value = "";
    results.value = [];
    return;
  }
  searching.value = true;
  try {
    results.value = await searchKnowledge({
      query: trimmedQuery,
      knowledgeBase: selectedKnowledgeBase.value,
      limit: 8,
    });
    actionError.value = null;
    actionMessage.value = "";
  } catch (searchError) {
    actionError.value = searchError instanceof Error ? searchError.message : t("knowledge.actionFailedFallback");
    actionMessage.value = "";
  } finally {
    searching.value = false;
  }
}

function statusLabel(status: "indexed" | "needs_rebuild") {
  return status === "indexed" ? t("knowledge.indexed") : t("knowledge.needsRebuild");
}

function statusClass(status: "indexed" | "needs_rebuild") {
  return `knowledge-page__status knowledge-page__status--${status}`;
}

onMounted(() => {
  void loadKnowledgeBases();
});
</script>

<style scoped>
.knowledge-page {
  min-height: 100%;
  display: grid;
  gap: 18px;
  padding: 24px;
}

.knowledge-page__header,
.knowledge-page__overview,
.knowledge-page__base-panel,
.knowledge-page__search-panel {
  background: var(--toograph-glass-specular), var(--toograph-glass-lens), var(--toograph-glass-bg-strong);
  border: 1px solid rgba(120, 53, 15, 0.1);
  box-shadow: 0 18px 46px rgba(30, 41, 59, 0.08);
  backdrop-filter: blur(18px) saturate(1.15);
}

.knowledge-page__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 22px;
  border-radius: 8px;
}

.knowledge-page__eyebrow,
.knowledge-page__section-kicker {
  color: var(--toograph-accent-strong);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.knowledge-page__title {
  margin: 4px 0 8px;
  color: var(--toograph-text-strong);
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  letter-spacing: 0;
}

.knowledge-page__body {
  margin: 0;
  color: var(--toograph-text-muted);
  line-height: 1.65;
}

.knowledge-page__header-actions,
.knowledge-page__base-meta,
.knowledge-page__base-footer,
.knowledge-page__result-meta,
.knowledge-page__source-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.knowledge-page__base-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.knowledge-page__base-actions :deep(.el-button) {
  margin-left: 0;
}

.knowledge-page__overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border-radius: 8px;
}

.knowledge-page__metric {
  min-width: 0;
  padding: 16px;
  background: rgba(255, 255, 255, 0.62);
}

.knowledge-page__metric span {
  display: block;
  color: var(--toograph-text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.knowledge-page__metric strong {
  display: block;
  margin-top: 5px;
  color: var(--toograph-text-strong);
  font-size: 1.25rem;
}

.knowledge-page__notice,
.knowledge-page__empty {
  padding: 16px;
  border: 1px solid rgba(180, 83, 9, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--toograph-text-muted);
}

.knowledge-page__notice--success {
  border-color: rgba(16, 185, 129, 0.18);
  color: #047857;
}

.knowledge-page__empty {
  display: grid;
  gap: 10px;
  align-items: start;
}

.knowledge-page__empty p {
  margin: 0;
  color: var(--toograph-text-strong);
  font-weight: 800;
}

.knowledge-page__layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.36fr) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.knowledge-page__base-panel,
.knowledge-page__search-panel {
  min-width: 0;
  border-radius: 8px;
  padding: 16px;
}

.knowledge-page__panel-heading,
.knowledge-page__result-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.knowledge-page__panel-heading h3,
.knowledge-page__result-heading h4 {
  margin: 3px 0 0;
  color: var(--toograph-text-strong);
  letter-spacing: 0;
}

.knowledge-page__base-list,
.knowledge-page__result-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.knowledge-page__base-card,
.knowledge-page__result-card {
  min-width: 0;
  border: 1px solid rgba(120, 53, 15, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.68);
}

.knowledge-page__base-card {
  display: grid;
  gap: 10px;
  padding: 13px;
}

.knowledge-page__base-card--active {
  border-color: rgba(154, 52, 18, 0.24);
  background: rgba(255, 255, 255, 0.86);
}

.knowledge-page__base-select {
  appearance: none;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 5px;
  min-width: 0;
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 0;
  text-align: left;
  cursor: pointer;
}

.knowledge-page__base-select strong,
.knowledge-page__result-heading h4 {
  overflow-wrap: anywhere;
}

.knowledge-page__base-select small,
.knowledge-page__base-meta,
.knowledge-page__embedding-label,
.knowledge-page__result-card p,
.knowledge-page__result-meta,
.knowledge-page__source-line {
  color: var(--toograph-text-muted);
  line-height: 1.5;
}

.knowledge-page__base-kind,
.knowledge-page__base-meta span,
.knowledge-page__result-meta span,
.knowledge-page__status,
.knowledge-page__score {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border-radius: 999px;
  padding: 4px 8px;
  background: var(--toograph-status-bg, rgba(148, 163, 184, 0.16));
  color: var(--toograph-status-fg, var(--toograph-text-muted));
  font-size: 0.76rem;
  font-weight: 700;
}

.knowledge-page__base-kind {
  min-width: 0;
  display: block;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-page__status--indexed {
  --toograph-status-bg: rgba(16, 185, 129, 0.12);
  --toograph-status-fg: #047857;
}

.knowledge-page__status--needs_rebuild {
  --toograph-status-bg: rgba(245, 158, 11, 0.14);
  --toograph-status-fg: #92400e;
}

.knowledge-page__embedding-label,
.knowledge-page__citation-id {
  overflow-wrap: anywhere;
  font-family: var(--toograph-font-mono);
  font-size: 0.76rem;
}

.knowledge-page__citation-id {
  color: var(--toograph-accent-strong);
  font-weight: 800;
}

.knowledge-page__search-bar {
  display: grid;
  grid-template-columns: minmax(180px, 0.28fr) minmax(0, 1fr) auto;
  gap: 10px;
  margin-top: 14px;
  align-items: center;
}

.knowledge-page__base-picker {
  width: 100%;
}

.knowledge-page__result-card {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.knowledge-page__result-card p {
  margin: 0;
}

.knowledge-page__source-line {
  justify-content: space-between;
}

.knowledge-page__source-line a {
  color: var(--toograph-accent-strong);
  font-weight: 800;
  text-decoration: none;
}

@media (max-width: 1020px) {
  .knowledge-page {
    padding: 16px;
  }

  .knowledge-page__header,
  .knowledge-page__layout {
    grid-template-columns: 1fr;
  }

  .knowledge-page__overview {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .knowledge-page__search-panel {
    order: -1;
  }
}

@media (max-width: 720px) {
  .knowledge-page__search-bar {
    grid-template-columns: 1fr;
  }

  .knowledge-page__overview {
    grid-template-columns: 1fr;
  }

  .knowledge-page__header-actions,
  .knowledge-page__panel-heading,
  .knowledge-page__result-heading,
  .knowledge-page__source-line {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
