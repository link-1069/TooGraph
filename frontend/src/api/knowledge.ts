import type {
  KnowledgeBaseRecord,
  KnowledgeDeleteReport,
  KnowledgeImportReport,
  KnowledgeRebuildReport,
  KnowledgeSearchResult,
} from "@/types/knowledge";

import { apiDelete, apiGet, apiPost } from "./http.ts";

export async function fetchKnowledgeBases(): Promise<KnowledgeBaseRecord[]> {
  return apiGet<KnowledgeBaseRecord[]>("/api/knowledge/bases");
}

export async function searchKnowledge(input: {
  query: string;
  knowledgeBase?: string;
  limit?: number;
}): Promise<KnowledgeSearchResult[]> {
  const searchParams = new URLSearchParams();
  searchParams.set("query", input.query);
  if (input.knowledgeBase) {
    searchParams.set("knowledge_base", input.knowledgeBase);
  }
  if (input.limit) {
    searchParams.set("limit", String(input.limit));
  }
  return apiGet<KnowledgeSearchResult[]>(`/api/knowledge?${searchParams.toString()}`);
}

export async function rebuildKnowledgeBase(
  knowledgeBase: string,
  input: { provider?: string; model?: string; dimension?: number } = {},
): Promise<KnowledgeRebuildReport> {
  return apiPost<KnowledgeRebuildReport>(`/api/knowledge/bases/${encodeURIComponent(knowledgeBase)}/rebuild`, input);
}

export async function importOfficialKnowledgeBases(): Promise<KnowledgeImportReport> {
  return apiPost<KnowledgeImportReport>("/api/knowledge/bases/import-official", {});
}

export async function deleteKnowledgeBase(knowledgeBase: string): Promise<KnowledgeDeleteReport> {
  return apiDelete<KnowledgeDeleteReport>(`/api/knowledge/bases/${encodeURIComponent(knowledgeBase)}`);
}
