import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { delimiter, resolve } from "node:path";
import test from "node:test";

import { createCommandEnvironment, parseGitChangedPaths, resolveOfficialAssetGatePlan } from "./official-asset-gate.mjs";

test("official asset gate runs template layout checks for official template changes", () => {
  const plan = resolveOfficialAssetGatePlan({
    changedPaths: [
      "graph_template/official/embedding_maintenance/template.json",
      "docs/hermes-agent-capability-parity-roadmap.md",
    ],
  });

  assert.deepEqual(plan.changedAssetKinds, ["official_template"]);
  assert.deepEqual(
    plan.commands.map((command) => command.args.join(" ")),
    [
      "diff --check",
      "-m unittest backend.tests.test_template_layouts",
    ],
  );
});

test("official asset gate keeps template changes on the template gate", () => {
  const plan = resolveOfficialAssetGatePlan({
    changedPaths: ["graph_template/official/embedding_maintenance/template.json"],
  });

  assert.deepEqual(
    plan.commands.map((command) => command.args.join(" ")),
    [
      "diff --check",
      "-m unittest backend.tests.test_template_layouts",
    ],
  );
});

test("official asset gate includes untracked official assets when building the git change list", () => {
  assert.deepEqual(
    parseGitChangedPaths({
      diffOutput: "docs/README.md\n",
      untrackedOutput: "graph_template/official/new_template/template.json\n",
    }),
    ["docs/README.md", "graph_template/official/new_template/template.json"],
  );
});

test("official asset gate runs action and tool contract checks for official capability package changes", () => {
  const plan = resolveOfficialAssetGatePlan({
    changedPaths: [
      "action/official/toograph_capability_selector/action.json",
      "tool/official/buddy_history_context_loader/tool.json",
    ],
  });

  assert.deepEqual(plan.changedAssetKinds, ["official_action", "official_tool"]);
  assert.deepEqual(
    plan.commands.map((command) => command.args.join(" ")),
    [
      "diff --check",
      "-m unittest backend.tests.test_action_manifest_contract backend.tests.test_backend_action_package_naming backend.tests.test_node_system_validator_actions",
      "-m unittest backend.tests.test_toograph_capability_selector_action",
      "-m unittest backend.tests.test_tool_catalog_routes backend.tests.test_node_system_validator_tools backend.tests.test_tool_node_runtime",
      "-m unittest backend.tests.test_buddy_history_context_loader_tool",
    ],
  );
});

test("official asset gate adds package-specific tests for changed official action and tool packages", () => {
  const plan = resolveOfficialAssetGatePlan({
    changedPaths: [
      "action/official/buddy_session_recall/after_llm.py",
      "tool/official/session_search_context_loader/run.py",
    ],
  });

  assert.deepEqual(
    plan.commands.map((command) => command.args.join(" ")),
    [
      "diff --check",
      "-m unittest backend.tests.test_action_manifest_contract backend.tests.test_backend_action_package_naming backend.tests.test_node_system_validator_actions",
      "-m unittest backend.tests.test_buddy_session_recall_action",
      "-m unittest backend.tests.test_tool_catalog_routes backend.tests.test_node_system_validator_tools backend.tests.test_tool_node_runtime",
      "-m unittest backend.tests.test_session_search_context_loader_tool",
    ],
  );
});

test("official asset gate runs manifest-declared verification commands for capability packages", () => {
  const plan = resolveOfficialAssetGatePlan({
    changedPaths: ["action/official/toograph_graph_template_reader/action.json"],
  });

  assert.deepEqual(
    plan.commands.map((command) => command.args.join(" ")),
    [
      "diff --check",
      "-m unittest backend.tests.test_action_manifest_contract backend.tests.test_backend_action_package_naming backend.tests.test_node_system_validator_actions",
      "-m unittest backend.tests.test_toograph_graph_template_actions",
    ],
  );
});

test("root package exposes the official asset verification gate", () => {
  const rootPackage = JSON.parse(readFileSync(resolve("package.json"), "utf8"));

  assert.equal(rootPackage.scripts["verify:official-assets"], "node scripts/official-asset-gate.mjs --run");
});

test("official asset gate runs Python checks with backend on PYTHONPATH", () => {
  const env = createCommandEnvironment({ PYTHONPATH: "/existing/path" });

  assert.equal(env.PYTHONPATH, `${resolve("backend")}${delimiter}/existing/path`);
});
