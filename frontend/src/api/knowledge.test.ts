import test from "node:test";
import assert from "node:assert/strict";

import {
  deleteKnowledgeBase,
  fetchKnowledgeBases,
  importOfficialKnowledgeBases,
  rebuildKnowledgeBase,
  searchKnowledge,
} from "./knowledge.ts";

const originalFetch = globalThis.fetch;

test("fetchKnowledgeBases requests the knowledge bases endpoint", async () => {
  let requestedUrl = "";

  globalThis.fetch = (async (input: string | URL | Request) => {
    requestedUrl = String(input);
    return new Response(
      JSON.stringify([
        {
          name: "toograph-official",
          kb_id: "toograph-official",
          label: "TooGraph Project Docs",
          description: "Project-specific TooGraph documentation and current implementation notes.",
          sourceKind: "toograph_project_docs",
          sourceUrl: "https://github.com/OoABYSSoO/TooGraph",
          version: "v1",
          documentCount: 9,
          chunkCount: 16,
          importedAt: "2026-04-13T15:58:47.035074+00:00",
          embeddingProvider: "local-hash",
          embeddingModel: "hashing-v1",
          embeddingDimension: 384,
          embeddingCount: 16,
          embeddingUpdatedAt: "2026-04-13T16:00:00.000000+00:00",
        },
      ]),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      },
    );
  }) as typeof fetch;

  const knowledgeBases = await fetchKnowledgeBases();

  assert.equal(requestedUrl, "/api/knowledge/bases");
  assert.deepEqual(knowledgeBases, [
    {
      name: "toograph-official",
      kb_id: "toograph-official",
      label: "TooGraph Project Docs",
      description: "Project-specific TooGraph documentation and current implementation notes.",
      sourceKind: "toograph_project_docs",
      sourceUrl: "https://github.com/OoABYSSoO/TooGraph",
      version: "v1",
      documentCount: 9,
      chunkCount: 16,
      importedAt: "2026-04-13T15:58:47.035074+00:00",
      embeddingProvider: "local-hash",
      embeddingModel: "hashing-v1",
      embeddingDimension: 384,
      embeddingCount: 16,
      embeddingUpdatedAt: "2026-04-13T16:00:00.000000+00:00",
    },
  ]);

  globalThis.fetch = originalFetch;
});

test("knowledge API searches citations, rebuilds indexes, imports official bases, and deletes bases", async () => {
  const requests: Array<{ url: string; method: string; body: unknown }> = [];

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({
      url: String(input),
      method: init?.method || "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (String(input).includes("/rebuild")) {
      return new Response(JSON.stringify({ kb_id: "docs", embeddingCount: 3 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (String(input).includes("/import-official")) {
      return new Response(JSON.stringify({ imported: [{ name: "docs" }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (init?.method === "DELETE") {
      return new Response(JSON.stringify({ kb_id: "docs", deleted: true, documentCount: 2, chunkCount: 5 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify([{ citation_id: "kb:docs:1", title: "Citation", score: 0.8 }]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const results = await searchKnowledge({ query: "graph revisions", knowledgeBase: "docs", limit: 5 });
    const rebuild = await rebuildKnowledgeBase("docs", { dimension: 64 });
    const imported = await importOfficialKnowledgeBases();
    const deleted = await deleteKnowledgeBase("docs");

    assert.deepEqual(results, [{ citation_id: "kb:docs:1", title: "Citation", score: 0.8 }]);
    assert.deepEqual(rebuild, { kb_id: "docs", embeddingCount: 3 });
    assert.deepEqual(imported, { imported: [{ name: "docs" }] });
    assert.deepEqual(deleted, { kb_id: "docs", deleted: true, documentCount: 2, chunkCount: 5 });
    assert.deepEqual(requests, [
      { url: "/api/knowledge?query=graph+revisions&knowledge_base=docs&limit=5", method: "GET", body: null },
      { url: "/api/knowledge/bases/docs/rebuild", method: "POST", body: { dimension: 64 } },
      { url: "/api/knowledge/bases/import-official", method: "POST", body: {} },
      { url: "/api/knowledge/bases/docs", method: "DELETE", body: null },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
