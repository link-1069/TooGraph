import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentFilePath = fileURLToPath(import.meta.url);
const currentDirectory = dirname(currentFilePath);
const componentSource = readFileSync(resolve(currentDirectory, "KnowledgePage.vue"), "utf8");

test("KnowledgePage exposes import, rebuild, search, and citation result controls", () => {
  assert.match(componentSource, /<AppShell>/);
  assert.match(componentSource, /fetchKnowledgeBases/);
  assert.match(componentSource, /importOfficialKnowledgeBases/);
  assert.match(componentSource, /rebuildKnowledgeBase/);
  assert.match(componentSource, /deleteKnowledgeBase/);
  assert.match(componentSource, /searchKnowledge/);
  assert.match(componentSource, /class="knowledge-page__search-bar"/);
  assert.match(componentSource, /data-virtual-affordance-id="knowledge\.action\.importOfficial"/);
  assert.match(componentSource, /:data-virtual-affordance-id="`knowledge\.base\.\$\{row\.id\}\.rebuild`"/);
  assert.match(componentSource, /:data-virtual-affordance-id="`knowledge\.base\.\$\{row\.id\}\.delete`"/);
  assert.match(componentSource, /data-virtual-affordance-id="knowledge\.action\.search"/);
  assert.match(componentSource, /class="knowledge-page__citation-id"/);
  assert.match(componentSource, /{{ row\.retrievalLabel }}/);
});

test("KnowledgePage uses responsive management layout without raw browser controls", () => {
  assert.match(componentSource, /class="knowledge-page__layout"/);
  assert.match(componentSource, /<ElInput/);
  assert.match(componentSource, /<ElSelect/);
  assert.match(componentSource, /<ElButton/);
  assert.match(componentSource, /<ElPopconfirm/);
  assert.match(componentSource, /<ElPopconfirm[\s\S]*:width="280"/);
  assert.match(componentSource, /<ElPopconfirm[\s\S]*confirm-button-type="danger"/);
  assert.match(componentSource, /\.knowledge-page__layout \{[\s\S]*grid-template-columns:\s*minmax\(280px,\s*0\.36fr\) minmax\(0,\s*1fr\);/);
  assert.match(componentSource, /@media \(max-width:\s*1020px\) \{[\s\S]*\.knowledge-page__layout \{[\s\S]*grid-template-columns:\s*1fr;/);
  assert.doesNotMatch(componentSource, /<input\s/);
  assert.doesNotMatch(componentSource, /<select\s/);
});

test("KnowledgePage keeps long knowledge metadata readable on narrow screens", () => {
  assert.match(componentSource, /\.knowledge-page__base-select \{[\s\S]*?min-width:\s*0;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-select \{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\);[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?min-width:\s*0;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?display:\s*block;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?width:\s*100%;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?overflow:\s*hidden;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?text-overflow:\s*ellipsis;[\s\S]*?\}/);
  assert.match(componentSource, /\.knowledge-page__base-kind \{[\s\S]*?white-space:\s*nowrap;[\s\S]*?\}/);
  assert.match(componentSource, /@media \(max-width:\s*1020px\) \{[\s\S]*\.knowledge-page__search-panel \{[\s\S]*order:\s*-1;/);
});
