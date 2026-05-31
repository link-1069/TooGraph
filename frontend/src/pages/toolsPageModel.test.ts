import test from "node:test";
import assert from "node:assert/strict";

import {
  buildToolOverview,
  buildToolSourceOptions,
  buildToolStatusOptions,
  filterToolsForManagement,
  resolveToolDisplayText,
} from "./toolsPageModel.ts";
import type { ToolDefinition } from "@/types/tools";

function createTool(overrides: Partial<ToolDefinition> = {}): ToolDefinition {
  return {
    toolKey: "json_passthrough",
    name: "JSON Passthrough",
    description: "Return JSON input.",
    schemaVersion: "toograph.tool/v1",
    version: "1.0.0",
    permissions: ["local-file-read"],
    runtime: { type: "python", entrypoint: "run.py", timeoutSeconds: 30 },
    localized: {},
    inputSchema: [{ key: "value", name: "Value", valueType: "json", description: "Input value." }],
    outputSchema: [{ key: "result", name: "Result", valueType: "json", description: "Output value." }],
    sourceScope: "official",
    sourcePath: "/tool/official/json_passthrough/tool.json",
    runtimeReady: true,
    runtimeRegistered: true,
    status: "active",
    canManage: false,
    ...overrides,
  };
}

test("filterToolsForManagement filters by status source and searchable manifest fields", () => {
  const tools = [
    createTool(),
    createTool({
      toolKey: "local_writer",
      name: "Local Writer",
      description: "Write a local artifact.",
      sourceScope: "user",
      sourcePath: "/tool/user/local_writer/tool.json",
      status: "disabled",
      canManage: true,
      permissions: ["local-file-write"],
      inputSchema: [{ key: "artifact_path", name: "Artifact Path", valueType: "text", description: "Output path." }],
    }),
  ];

  assert.deepEqual(
    filterToolsForManagement(tools, { query: "artifact", status: "all", source: "all" }).map((tool) => tool.toolKey),
    ["local_writer"],
  );
  assert.deepEqual(
    filterToolsForManagement(tools, { query: "", status: "disabled", source: "user" }).map((tool) => tool.toolKey),
    ["local_writer"],
  );
  assert.deepEqual(
    filterToolsForManagement(tools, { query: "", status: "active", source: "official" }).map((tool) => tool.toolKey),
    ["json_passthrough"],
  );
});

test("resolveToolDisplayText switches tool names and descriptions by locale", () => {
  const tool = createTool({
    localized: {
      "zh-CN": {
        name: "JSON 透传",
        description: "返回 JSON 输入。",
      },
      "en-US": {
        name: "JSON Passthrough",
        description: "Return JSON input.",
      },
    },
  });

  assert.deepEqual(resolveToolDisplayText(tool, "zh-CN"), {
    name: "JSON 透传",
    description: "返回 JSON 输入。",
  });
  assert.deepEqual(resolveToolDisplayText(tool, "en-US"), {
    name: "JSON Passthrough",
    description: "Return JSON input.",
  });
  assert.deepEqual(resolveToolDisplayText(tool, "ja-JP"), {
    name: "JSON Passthrough",
    description: "Return JSON input.",
  });
});

test("filterToolsForManagement searches localized tool introductions", () => {
  const tools = [
    createTool({
      localized: {
        "zh-CN": {
          name: "记忆搜索上下文加载器",
          description: "搜索结构化长期记忆并返回可审计上下文包。",
        },
        "en-US": {
          name: "Memory Search Context Loader",
          description: "Searches structured long-term memories and returns an auditable context package.",
        },
      },
    }),
  ];

  assert.deepEqual(
    filterToolsForManagement(tools, { query: "长期记忆", status: "all", source: "all" }).map((tool) => tool.toolKey),
    ["json_passthrough"],
  );
  assert.deepEqual(
    filterToolsForManagement(tools, { query: "auditable context", status: "all", source: "all" }).map((tool) => tool.toolKey),
    ["json_passthrough"],
  );
});

test("buildToolOverview reports total active and source counts", () => {
  const overview = buildToolOverview([
    createTool(),
    createTool({ toolKey: "local_writer", sourceScope: "user", status: "disabled", canManage: true }),
  ]);

  assert.deepEqual(overview, {
    total: 2,
    active: 1,
    visibleTools: 1,
    userTools: 1,
    officialTools: 1,
  });
});

test("tool management filters expose status and source options", () => {
  assert.deepEqual(buildToolStatusOptions(), ["all", "active", "disabled"]);
  assert.deepEqual(buildToolSourceOptions(), ["all", "user", "official"]);
});
