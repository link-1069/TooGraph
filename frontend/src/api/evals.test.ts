import test from "node:test";
import assert from "node:assert/strict";

import {
  collectEvalCaseResult,
  collectEvalRunCases,
  createEvalRun,
  fetchEvalCases,
  fetchEvalRuns,
  fetchEvalSuites,
  runEvalCase,
  runEvalRunCases,
} from "./evals.ts";

const originalFetch = globalThis.fetch;

test("eval API client fetches suites, cases, and suite runs", async () => {
  const requestedUrls: string[] = [];

  globalThis.fetch = (async (input: string | URL | Request) => {
    requestedUrls.push(String(input));
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    await fetchEvalSuites();
    await fetchEvalCases("suite one");
    await fetchEvalRuns("suite one");

    assert.deepEqual(requestedUrls, [
      "/api/evals/suites",
      "/api/evals/suites/suite%20one/cases",
      "/api/evals/suites/suite%20one/runs",
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("eval API client creates runs and posts case run/collect actions", async () => {
  const requests: Array<{ url: string; body: unknown }> = [];

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify({ eval_run_id: "evalrun_1", case_results: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    await createEvalRun("suite one");
    await runEvalCase("evalrun_1", "case one");
    await collectEvalCaseResult("evalrun_1", "case one", { runLlmJudge: true });

    assert.deepEqual(requests, [
      { url: "/api/evals/runs", body: { suite_id: "suite one" } },
      { url: "/api/evals/runs/evalrun_1/cases/case%20one/run", body: {} },
      { url: "/api/evals/runs/evalrun_1/cases/case%20one/collect", body: { run_llm_judge: true } },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("eval API client posts batch run and collect actions", async () => {
  const requests: Array<{ url: string; body: unknown }> = [];

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify({ eval_run_id: "evalrun_1", results: [], errors: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    await runEvalRunCases("evalrun_1");
    await collectEvalRunCases("evalrun_1", { runLlmJudge: true });

    assert.deepEqual(requests, [
      { url: "/api/evals/runs/evalrun_1/cases/run", body: {} },
      { url: "/api/evals/runs/evalrun_1/cases/collect", body: { run_llm_judge: true } },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
