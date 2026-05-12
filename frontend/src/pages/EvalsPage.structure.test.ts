import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentFilePath = fileURLToPath(import.meta.url);
const currentDirectory = dirname(currentFilePath);
const componentSource = readFileSync(resolve(currentDirectory, "EvalsPage.vue"), "utf8");

test("EvalsPage loads suites, cases, and selected suite runs", () => {
  assert.match(componentSource, /import \{[\s\S]*fetchEvalSuites[\s\S]*fetchEvalCases[\s\S]*fetchEvalRuns[\s\S]*createEvalRun[\s\S]*runEvalCase[\s\S]*collectEvalCaseResult[\s\S]*\} from "@\/api\/evals";/);
  assert.match(componentSource, /const suites = ref<EvalSuite\[\]>\(\[\]\);/);
  assert.match(componentSource, /const selectedSuiteId = ref\(""\);/);
  assert.match(componentSource, /async function loadEvalWorkspace\(\)/);
  assert.match(componentSource, /async function loadSelectedSuiteDetail\(\)/);
  assert.match(componentSource, /watch\(selectedSuiteId/);
});

test("EvalsPage exposes run, rerun, collect, batch, and graph-run navigation controls", () => {
  assert.match(componentSource, /data-virtual-affordance-id="evals\.action\.refresh"/);
  assert.match(componentSource, /data-virtual-affordance-id="evals\.action\.createRun"/);
  assert.match(componentSource, /data-virtual-affordance-id="evals\.action\.runAllCases"/);
  assert.match(componentSource, /data-virtual-affordance-id="evals\.action\.collectAllCases"/);
  assert.match(componentSource, /data-virtual-affordance-id="evals\.action\.llmJudgeToggle"/);
  assert.match(componentSource, /:data-virtual-affordance-id="`evals\.case\.\$\{card\.caseId\}\.run`"/);
  assert.match(componentSource, /:data-virtual-affordance-id="`evals\.case\.\$\{card\.caseId\}\.collect`"/);
  assert.match(componentSource, /:to="`\/runs\/\$\{encodeURIComponent\(card\.graphRunId\)\}`"/);
  assert.match(componentSource, /@click="runSelectedRunCases"/);
  assert.match(componentSource, /@click="collectSelectedRunCases"/);
  assert.match(componentSource, /@click="startEvalCase\(card\.caseId\)"/);
  assert.match(componentSource, /@click="collectEvalCase\(card\.caseId\)"/);
  assert.match(componentSource, /const runLlmJudgeOnCollect = ref\(false\);/);
  assert.match(componentSource, /runLlmJudge: runLlmJudgeOnCollect\.value/);
  assert.match(componentSource, /function mergeCaseResults\(results: EvalRun\["case_results"\]\)/);
});

test("EvalsPage renders compact case expected and actual comparison details", () => {
  assert.match(componentSource, /class="evals-page__comparison"/);
  assert.match(componentSource, /v-if="card\.expectedPreview \|\| card\.actualPreview \|\| card\.checkComparisons\.length > 0"/);
  assert.match(componentSource, /class="evals-page__comparison-grid"/);
  assert.match(componentSource, /{{ t\("evals\.expected"\) }}/);
  assert.match(componentSource, /{{ t\("evals\.actual"\) }}/);
  assert.match(componentSource, /v-for="comparison in card\.checkComparisons"/);
  assert.match(componentSource, /class="evals-page__check-comparison"/);
});

test("EvalsPage renders failed case diagnostics before comparison details", () => {
  assert.match(componentSource, /class="evals-page__failure-diagnostics"/);
  assert.match(componentSource, /v-if="card\.failureDiagnostics\.length > 0"/);
  assert.match(componentSource, /{{ t\("evals\.failureDiagnostics"\) }}/);
  assert.match(componentSource, /{{ card\.primaryFailure }}/);
  assert.match(componentSource, /v-for="diagnostic in card\.failureDiagnostics"/);
  assert.match(componentSource, /class="evals-page__failure-row"/);
  assert.match(componentSource, /{{ diagnostic\.message }}/);
});

test("EvalsPage uses a dense dashboard layout without nested cards", () => {
  assert.match(componentSource, /class="evals-page__suite-list"/);
  assert.match(componentSource, /class="evals-page__case-grid"/);
  assert.match(componentSource, /\.evals-page__layout \{[\s\S]*grid-template-columns:\s*minmax\(260px,\s*0\.34fr\) minmax\(0,\s*1fr\);/);
  assert.match(componentSource, /\.evals-page__case-card \{[\s\S]*border-radius:\s*8px;/);
  assert.match(componentSource, /@media \(max-width:\s*1020px\) \{[\s\S]*\.evals-page__layout \{[\s\S]*grid-template-columns:\s*1fr;/);
  assert.doesNotMatch(componentSource, /evals-page__card-card/);
});
