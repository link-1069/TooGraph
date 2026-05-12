export type KnowledgeBaseRecord = {
  name: string;
  kb_id: string;
  label: string;
  description: string;
  sourceKind: string;
  sourceUrl: string;
  version: string;
  documentCount: number;
  chunkCount: number;
  importedAt: string;
  embeddingProvider: string;
  embeddingModel: string;
  embeddingDimension: number;
  embeddingCount: number;
  embeddingUpdatedAt: string;
};

export type KnowledgeSearchResult = {
  citation_id: string;
  chunk_id: string;
  title: string;
  section: string;
  summary: string;
  source: string;
  url: string;
  score: number;
  metadata: Record<string, unknown>;
  retrieval: Record<string, unknown>;
};

export type KnowledgeRebuildReport = {
  kb_id: string;
  provider?: string;
  model?: string;
  dimension?: number;
  documentCount?: number;
  chunkCount?: number;
  embeddingCount?: number;
};

export type KnowledgeDeleteReport = {
  kb_id: string;
  deleted: boolean;
  documentCount?: number;
  chunkCount?: number;
  embeddingCount?: number;
};

export type KnowledgeImportReport = {
  imported: KnowledgeBaseRecord[];
};
