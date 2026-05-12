import { translate } from "../i18n/index.ts";
import type { KnowledgeBaseRecord, KnowledgeSearchResult } from "@/types/knowledge";

export type KnowledgeOverviewItem = {
  key: string;
  label: string;
  value: number;
};

export type KnowledgeBaseRow = {
  id: string;
  title: string;
  description: string;
  sourceKind: string;
  sourceUrl: string;
  version: string;
  status: "indexed" | "needs_rebuild";
  documentCount: number;
  chunkCount: number;
  embeddingLabel: string;
};

export type KnowledgeSearchRow = {
  key: string;
  citationId: string;
  chunkId: string;
  title: string;
  section: string;
  summary: string;
  source: string;
  url: string;
  scoreLabel: string;
  retrievalLabel: string;
};

export function chooseInitialKnowledgeBase(bases: KnowledgeBaseRecord[], currentBase: string): string {
  if (currentBase && bases.some((base) => base.name === currentBase || base.kb_id === currentBase)) {
    return currentBase;
  }
  return bases[0]?.name || bases[0]?.kb_id || "";
}

export function buildKnowledgeOverview(bases: KnowledgeBaseRecord[]): KnowledgeOverviewItem[] {
  return [
    { key: "bases", label: translate("knowledge.basesMetric"), value: bases.length },
    { key: "documents", label: translate("knowledge.documentsMetric"), value: sumNumber(bases, "documentCount") },
    { key: "chunks", label: translate("knowledge.chunksMetric"), value: sumNumber(bases, "chunkCount") },
    { key: "indexed", label: translate("knowledge.indexedMetric"), value: bases.filter((base) => Number(base.embeddingCount || 0) > 0).length },
  ];
}

export function buildKnowledgeBaseRows(bases: KnowledgeBaseRecord[]): KnowledgeBaseRow[] {
  return bases.map((base) => {
    const id = base.name || base.kb_id;
    const embeddingLabel = base.embeddingProvider
      ? `${base.embeddingProvider} · ${base.embeddingModel || translate("common.none")} · ${base.embeddingDimension || 0}d`
      : translate("knowledge.notIndexed");
    return {
      id,
      title: base.label?.trim() || id,
      description: base.description || "",
      sourceKind: base.sourceKind || "",
      sourceUrl: base.sourceUrl || "",
      version: base.version || "",
      status: Number(base.embeddingCount || 0) > 0 ? "indexed" : "needs_rebuild",
      documentCount: Number(base.documentCount || 0),
      chunkCount: Number(base.chunkCount || 0),
      embeddingLabel,
    };
  });
}

export function buildKnowledgeSearchRows(results: KnowledgeSearchResult[]): KnowledgeSearchRow[] {
  return results.map((result, index) => {
    const citationId = result.citation_id || `citation-${index + 1}`;
    return {
      key: citationId,
      citationId,
      chunkId: result.chunk_id || "",
      title: result.title || citationId,
      section: result.section || "",
      summary: result.summary || "",
      source: result.source || "",
      url: result.url || "",
      scoreLabel: formatScore(result.score),
      retrievalLabel: formatRetrieval(result.retrieval),
    };
  });
}

function sumNumber(bases: KnowledgeBaseRecord[], key: "documentCount" | "chunkCount"): number {
  return bases.reduce((total, base) => total + Math.max(0, Number(base[key] || 0)), 0);
}

function formatScore(value: unknown): string {
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(3) : "0.000";
}

function formatRetrieval(retrieval: Record<string, unknown> | undefined): string {
  const mode = typeof retrieval?.mode === "string" && retrieval.mode ? retrieval.mode : translate("common.none");
  const keyword = formatScore(retrieval?.keyword_score);
  const vector = formatScore(retrieval?.vector_score);
  return `${mode} · keyword ${keyword} · vector ${vector}`;
}
