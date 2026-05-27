import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const componentSource = readFileSync(resolve(currentDirectory, "CuratorReportsPage.vue"), "utf8");

test("CuratorReportsPage loads curator template runs and selected run details", () => {
  assert.match(componentSource, /fetchRuns\(\{\s*templateId:\s*CURATOR_REPORT_TEMPLATE_ID,\s*includeInternal:\s*true\s*\}\)/);
  assert.match(componentSource, /fetchRun\(selectedRunId\.value/);
  assert.match(componentSource, /buildCuratorReportItems/);
  assert.match(componentSource, /buildCuratorReportDetail/);
  assert.match(componentSource, /v-for="report in reportItems"/);
});

test("CuratorReportsPage keeps report, candidates, health, scheduler recommendation and source run inspectable", () => {
  assert.match(componentSource, /curatorReports\.report/);
  assert.match(componentSource, /curatorReports\.healthReport/);
  assert.match(componentSource, /curatorReports\.improvementCandidates/);
  assert.match(componentSource, /curatorReports\.schedulerRecommendation/);
  assert.match(componentSource, /:to="runHref\(selectedReportDetail\.runId\)"/);
  assert.match(componentSource, /JSON\.stringify\(selectedReportDetail\.improvementCandidates/);
});

test("CuratorReportsPage has an empty state that points back to scheduled curator runs", () => {
  assert.match(componentSource, /curatorReports\.empty/);
  assert.match(componentSource, /to="\/scheduler"/);
});
