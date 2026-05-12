import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import path from "node:path";
import { spawnSync } from "node:child_process";

const LOCALE_STORAGE_KEY = "toograph:locale";
const FIXTURE_LABEL = "E2E Knowledge Fixture";

test("knowledge center searches citations and deletes a temporary base", async ({ page, request }, testInfo) => {
  const problems = collectBrowserProblems(page);
  const kbId = uniqueKnowledgeBaseId(testInfo);
  await seedKnowledgeBase(kbId);

  try {
    await openKnowledgeCenter(page);
    await chooseFixtureBase(page);
    await expectNoHorizontalOverflow(page);

    await page.getByLabel("Search knowledge bases").fill("approval graph operations");
    await page.getByRole("button", { name: "Search" }).click();

    await expect(page.locator(".knowledge-page__citation-id").filter({ hasText: `kb:${kbId}:1` })).toBeVisible();
    await expect(page.locator(".knowledge-page__result-card").filter({ hasText: "E2E Approval Graph Operations" })).toBeVisible();
    await expect(page.locator(".knowledge-page__source-line").filter({ hasText: "https://example.invalid/toograph/e2e/approval" })).toBeVisible();

    const card = fixtureCard(page);
    await card.getByRole("button", { name: "Delete base" }).click();
    const confirm = page.locator(".el-popconfirm").filter({ hasText: "Delete E2E Knowledge Fixture" });
    await expect(confirm).toBeVisible();
    await expectPopoverWithinViewport(page, confirm);

    await confirm.getByRole("button", { name: "Delete base" }).click();
    await expect(page.getByText(`Deleted knowledge base: ${kbId}`)).toBeVisible();
    await expect(page.locator(".knowledge-page__base-card").filter({ hasText: FIXTURE_LABEL })).toHaveCount(0);
    expect(problems).toEqual([]);
  } finally {
    await deleteKnowledgeBase(request, kbId);
  }
});

test("knowledge center remains usable on mobile", async ({ page, request }, testInfo) => {
  const problems = collectBrowserProblems(page);
  const kbId = uniqueKnowledgeBaseId(testInfo);
  await seedKnowledgeBase(kbId);

  try {
    await page.setViewportSize({ width: 390, height: 844 });
    await openKnowledgeCenter(page);
    await chooseFixtureBase(page);
    await expectNoHorizontalOverflow(page);

    await page.getByLabel("Search knowledge bases").fill("audit trail");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.locator(".knowledge-page__citation-id").filter({ hasText: `kb:${kbId}:1` })).toBeVisible();
    await expect(page.locator(".knowledge-page__search-panel")).toBeInViewport();

    const card = fixtureCard(page);
    await card.getByRole("button", { name: "Delete base" }).click();
    const confirm = page.locator(".el-popconfirm").filter({ hasText: "Delete E2E Knowledge Fixture" });
    await expect(confirm).toBeVisible();
    await expectPopoverWithinViewport(page, confirm);
    await confirm.getByRole("button", { name: "Cancel" }).click();

    await expectNoHorizontalOverflow(page);
    expect(problems).toEqual([]);
  } finally {
    await deleteKnowledgeBase(request, kbId);
  }
});

async function openKnowledgeCenter(page: Page) {
  await page.addInitScript(
    ({ localeKey }) => {
      window.localStorage.setItem(localeKey, "en-US");
    },
    { localeKey: LOCALE_STORAGE_KEY },
  );
  await page.goto("/knowledge");
  await expect(page.locator(".knowledge-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Knowledge Center" })).toBeVisible();
}

async function chooseFixtureBase(page: Page) {
  const card = fixtureCard(page);
  await expect(card).toBeVisible();
  await card.locator(".knowledge-page__base-select").click();
  await expect(card).toHaveClass(/knowledge-page__base-card--active/);
}

function fixtureCard(page: Page) {
  return page.locator(".knowledge-page__base-card").filter({ hasText: FIXTURE_LABEL }).first();
}

async function expectNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(hasOverflow).toBe(false);
}

async function expectPopoverWithinViewport(page: Page, popover: ReturnType<Page["locator"]>) {
  const bounds = await popover.boundingBox();
  expect(bounds).not.toBeNull();
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  expect((bounds?.x ?? -1) >= 0).toBe(true);
  expect((bounds?.y ?? -1) >= 0).toBe(true);
  expect((bounds?.x ?? 0) + (bounds?.width ?? 0) <= (viewport?.width ?? 0) + 1).toBe(true);
  expect((bounds?.y ?? 0) + (bounds?.height ?? 0) <= (viewport?.height ?? 0) + 1).toBe(true);
}

function collectBrowserProblems(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      problems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    problems.push(`pageerror: ${error.message}`);
  });
  return problems;
}

function uniqueKnowledgeBaseId(testInfo: TestInfo) {
  const suffix = `${Date.now().toString(36)}-${testInfo.workerIndex}-${Math.random().toString(36).slice(2, 8)}`;
  return `e2e-knowledge-${suffix}`;
}

async function deleteKnowledgeBase(request: APIRequestContext, kbId: string) {
  const response = await request.delete(`/api/knowledge/bases/${encodeURIComponent(kbId)}`);
  if (!response.ok() && response.status() !== 404) {
    throw new Error(`Failed to clean up ${kbId}: ${response.status()} ${await response.text()}`);
  }
}

async function seedKnowledgeBase(kbId: string) {
  const rootDir = path.resolve(process.cwd(), "..");
  const python = process.env.PYTHON || "python";
  const result = spawnSync(python, ["-c", SEED_KNOWLEDGE_BASE_PYTHON], {
    cwd: rootDir,
    encoding: "utf-8",
    env: {
      ...process.env,
      E2E_KB_ID: kbId,
      PYTHONPATH: path.join(rootDir, "backend"),
    },
  });

  if (result.status !== 0) {
    throw new Error(`Failed to seed knowledge base:\n${result.stdout}\n${result.stderr}`);
  }
}

const SEED_KNOWLEDGE_BASE_PYTHON = String.raw`
import os

from app.knowledge.loader import (
    KnowledgeBaseRecord,
    KnowledgeDocument,
    _replace_knowledge_base,
    rebuild_knowledge_base_embeddings,
)

kb_id = os.environ["E2E_KB_ID"]
record = KnowledgeBaseRecord(
    kb_id=kb_id,
    label="E2E Knowledge Fixture",
    description="Temporary deterministic fixture for Playwright knowledge center coverage.",
    source_kind="e2e_fixture",
    source_url="https://example.invalid/toograph/e2e",
    version="playwright",
    payload={"fixture": "knowledge-management"},
)
documents = [
    KnowledgeDocument(
        doc_id="approval-flow",
        title="E2E Approval Graph Operations",
        url="https://example.invalid/toograph/e2e/approval",
        section="Graph Operations",
        content=(
            "TooGraph approval graph operations keep file writes, graph edits, and knowledge updates behind "
            "visible review steps. The audit trail records command drafts, revision ids, result packages, "
            "and citation evidence so a production operator can inspect what changed after an approval graph "
            "operation completes."
        ),
        source_path="e2e/approval.md",
        metadata={"source_path": "e2e/approval.md", "source_kind": "e2e_fixture"},
    ),
    KnowledgeDocument(
        doc_id="citation-flow",
        title="E2E Citation Search Surface",
        url="https://example.invalid/toograph/e2e/citation",
        section="Citation Search",
        content=(
            "The knowledge center exposes citation identifiers, chunk ids, retrieval modes, and source links "
            "for Hybrid RAG validation. Search results should remain readable on mobile screens and destructive "
            "knowledge base controls must require confirmation before deleting indexed data."
        ),
        source_path="e2e/citation.md",
        metadata={"source_path": "e2e/citation.md", "source_kind": "e2e_fixture"},
    ),
]
_replace_knowledge_base(record, documents)
rebuild_knowledge_base_embeddings(kb_id)
`;
