import test from "node:test";
import assert from "node:assert/strict";

import {
  buildKnowledgeBaseRows,
  buildKnowledgeOverview,
  buildKnowledgeSearchRows,
  chooseInitialKnowledgeBase,
} from "./knowledgePageModel.ts";
import type { KnowledgeBaseRecord, KnowledgeSearchResult } from "@/types/knowledge";

const bases: KnowledgeBaseRecord[] = [
  {
    name: "docs",
    kb_id: "docs",
    label: "Docs",
    description: "Project docs.",
    sourceKind: "repo",
    sourceUrl: "https://example.test/docs",
    version: "v1",
    documentCount: 2,
    chunkCount: 5,
    importedAt: "2026-05-19T00:00:00Z",
    embeddingProvider: "local-hash",
    embeddingModel: "hashing-v1",
    embeddingDimension: 64,
    embeddingCount: 5,
    embeddingUpdatedAt: "2026-05-19T00:01:00Z",
  },
  {
    name: "drafts",
    kb_id: "drafts",
    label: "",
    description: "",
    sourceKind: "local",
    sourceUrl: "",
    version: "",
    documentCount: 1,
    chunkCount: 2,
    importedAt: "",
    embeddingProvider: "",
    embeddingModel: "",
    embeddingDimension: 0,
    embeddingCount: 0,
    embeddingUpdatedAt: "",
  },
];

test("knowledge page model summarizes base and embedding inventory", () => {
  assert.equal(chooseInitialKnowledgeBase(bases, ""), "docs");
  assert.equal(chooseInitialKnowledgeBase(bases, "drafts"), "drafts");
  assert.deepEqual(buildKnowledgeOverview(bases), [
    { key: "bases", label: "知识库", value: 2 },
    { key: "documents", label: "文档", value: 3 },
    { key: "chunks", label: "Chunks", value: 7 },
    { key: "indexed", label: "已索引", value: 1 },
  ]);
});

test("knowledge page model builds readable base rows", () => {
  const rows = buildKnowledgeBaseRows(bases);

  assert.deepEqual(rows.map((row) => ({
    id: row.id,
    title: row.title,
    status: row.status,
    documentCount: row.documentCount,
    chunkCount: row.chunkCount,
    embeddingLabel: row.embeddingLabel,
  })), [
    {
      id: "docs",
      title: "Docs",
      status: "indexed",
      documentCount: 2,
      chunkCount: 5,
      embeddingLabel: "local-hash · hashing-v1 · 64d",
    },
    {
      id: "drafts",
      title: "drafts",
      status: "needs_rebuild",
      documentCount: 1,
      chunkCount: 2,
      embeddingLabel: "未索引",
    },
  ]);
});

test("knowledge page model keeps citation metadata visible in search rows", () => {
  const rows = buildKnowledgeSearchRows([
    {
      citation_id: "kb:docs:1",
      chunk_id: "docs:intro:1",
      title: "Intro",
      section: "Overview",
      summary: "Graph templates use auditable runs.",
      source: "docs/intro.md",
      url: "https://example.test/intro",
      score: 0.842,
      metadata: { source_path: "docs/intro.md" },
      retrieval: { mode: "hybrid", keyword_score: 0.7, vector_score: 0.9 },
    },
  ] as KnowledgeSearchResult[]);

  assert.deepEqual(rows, [
    {
      key: "kb:docs:1",
      citationId: "kb:docs:1",
      chunkId: "docs:intro:1",
      title: "Intro",
      section: "Overview",
      summary: "Graph templates use auditable runs.",
      source: "docs/intro.md",
      url: "https://example.test/intro",
      scoreLabel: "0.842",
      retrievalLabel: "hybrid · keyword 0.700 · vector 0.900",
    },
  ]);
});
