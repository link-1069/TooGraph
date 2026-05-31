import type { ToolDefinition } from "../types/tools.ts";

export type ToolStatusFilter = "all" | "active" | "disabled";
export type ToolSourceFilter = "all" | "user" | "official";

export type ToolManagementFilters = {
  query: string;
  status: ToolStatusFilter;
  source: ToolSourceFilter;
};

export type ToolOverview = {
  total: number;
  active: number;
  visibleTools: number;
  userTools: number;
  officialTools: number;
};

export type ToolDisplayText = {
  name: string;
  description: string;
};

export function buildToolStatusOptions(): ToolStatusFilter[] {
  return ["all", "active", "disabled"];
}

export function buildToolSourceOptions(): ToolSourceFilter[] {
  return ["all", "user", "official"];
}

export function filterToolsForManagement(tools: ToolDefinition[], filters: ToolManagementFilters): ToolDefinition[] {
  const normalizedQuery = filters.query.trim().toLowerCase();

  return tools.filter((tool) => {
    if (!matchesToolStatus(tool, filters.status)) {
      return false;
    }
    if (!matchesToolSource(tool, filters.source)) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return buildToolSearchText(tool).includes(normalizedQuery);
  });
}

export function buildToolOverview(tools: ToolDefinition[]): ToolOverview {
  return {
    total: tools.length,
    active: tools.filter((tool) => tool.status === "active").length,
    visibleTools: tools.filter((tool) => tool.status === "active").length,
    userTools: tools.filter((tool) => tool.sourceScope === "user").length,
    officialTools: tools.filter((tool) => tool.sourceScope === "official").length,
  };
}

export function resolveToolDisplayText(tool: ToolDefinition, locale: string): ToolDisplayText {
  const localizedText = resolveLocalizedToolText(tool, locale);
  return {
    name: localizedText?.name.trim() || tool.name,
    description: localizedText?.description.trim() || tool.description,
  };
}

function matchesToolStatus(tool: ToolDefinition, filter: ToolStatusFilter): boolean {
  if (filter === "active") {
    return tool.status === "active";
  }
  if (filter === "disabled") {
    return tool.status === "disabled";
  }
  return true;
}

function matchesToolSource(tool: ToolDefinition, filter: ToolSourceFilter): boolean {
  if (filter === "user") {
    return tool.sourceScope === "user";
  }
  if (filter === "official") {
    return tool.sourceScope === "official";
  }
  return true;
}

function resolveLocalizedToolText(tool: ToolDefinition, locale: string) {
  const localized = tool.localized ?? {};
  for (const candidate of buildLocaleCandidates(locale)) {
    const text = localized[candidate];
    if (text && (text.name.trim() || text.description.trim())) {
      return text;
    }
  }
  return null;
}

function buildLocaleCandidates(locale: string): string[] {
  const normalizedLocale = locale.trim();
  const language = normalizedLocale.split("-")[0] ?? "";
  const candidates = [
    normalizedLocale,
    language,
    language === "zh" ? "zh-CN" : "",
    language === "en" ? "en-US" : "",
    "en-US",
    "zh-CN",
  ];
  return candidates.filter((candidate, index) => Boolean(candidate) && candidates.indexOf(candidate) === index);
}

function buildToolSearchText(tool: ToolDefinition): string {
  return [
    tool.toolKey,
    tool.name,
    tool.description,
    ...Object.values(tool.localized ?? {}).flatMap((localizedText) => [localizedText.name, localizedText.description]),
    tool.version,
    tool.sourceScope,
    tool.sourcePath,
    tool.status,
    tool.runtime.type,
    tool.runtime.entrypoint,
    ...(tool.runtime.command ?? []),
    ...tool.permissions,
    ...tool.inputSchema.map((field) => `${field.key} ${field.name} ${field.valueType} ${field.description}`),
    ...tool.outputSchema.map((field) => `${field.key} ${field.name} ${field.valueType} ${field.description}`),
  ]
    .join(" ")
    .toLowerCase();
}
