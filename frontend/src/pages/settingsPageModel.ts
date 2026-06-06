import type { SettingsModelProviderUpdate } from "../api/settings.ts";
import type {
  ModelProviderTransport,
  OpenAICodexAuthStatus,
  SettingsModelProvider,
  SettingsPayload,
  SettingsProviderCredential,
  SettingsProviderModel,
  StructuredOutputMode,
} from "../types/settings.ts";

const DEFAULT_AGENT_TEMPERATURE = 0.2;
const DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS = 180;
export const DEFAULT_MODEL_COMPRESSION_THRESHOLD = 0.9;
export const DEFAULT_STRUCTURED_OUTPUT_MODE: StructuredOutputMode = "validate_then_repair";
type SettingsProvider = SettingsModelProvider;

export type ModelCapabilityKey =
  | "chat"
  | "embedding"
  | "rerank"
  | "vision"
  | "tool_call"
  | "structured_output";

export type ProviderModelCapabilities = Record<ModelCapabilityKey, boolean>;
export type ModelPurpose = "chat" | "embedding" | "rerank";

export type ProviderModelEmbeddingDraft = {
  dimensions: number | null;
};

export type ProviderModelDraft = {
  model: string;
  reasoning: boolean | null;
  context_window_ktokens: number | null;
  compression_threshold: number;
  capabilities: ProviderModelCapabilities;
  embedding: ProviderModelEmbeddingDraft;
};

export type ProviderDraft = {
  provider_id: string;
  label: string;
  transport: ModelProviderTransport;
  structured_output_mode: StructuredOutputMode;
  base_url: string;
  enabled: boolean;
  saved?: boolean;
  auth_header: string;
  auth_scheme: string;
  auth_mode?: string;
  requires_login?: boolean;
  auth_status?: OpenAICodexAuthStatus;
  request_timeout_seconds?: number;
  credential_pool: SettingsProviderCredential[];
  api_key: string;
  api_key_configured: boolean;
  api_key_preview?: string;
  discovered_models: string[];
  selected_models: string[];
  model_settings: Record<string, ProviderModelDraft>;
};

const DEFAULT_PROVIDER_CARD_IDS = new Set(["deepseek", "local"]);
const PROVIDER_CARD_ORDER: Record<string, number> = {
  "openai-codex": 0,
  deepseek: 1,
  local: 2,
};

function normalizeProviderId(value: unknown) {
  return String(value || "").trim().toLowerCase();
}

export function isDefaultProviderCardVisible(provider: { provider_id?: unknown }) {
  return DEFAULT_PROVIDER_CARD_IDS.has(normalizeProviderId(provider.provider_id));
}

export function isProviderApiKeyOptional(
  provider: Pick<ProviderDraft, "provider_id" | "base_url"> & Partial<Pick<ProviderDraft, "auth_mode" | "requires_login">>,
) {
  if (normalizeProviderId(provider.provider_id) === "local") {
    return true;
  }
  if (provider.requires_login || String(provider.auth_mode || "").trim().toLowerCase() === "chatgpt") {
    return true;
  }
  const baseUrl = String(provider.base_url || "").trim().toLowerCase();
  return baseUrl.includes("localhost") || baseUrl.includes("127.0.0.1") || baseUrl.startsWith("http://0.0.0.0");
}

export function isSignedOutLoginProvider(
  provider: Partial<Pick<SettingsProvider, "auth_mode" | "requires_login" | "auth_status">>,
) {
  const loginProvider = Boolean(provider.requires_login) || String(provider.auth_mode || "").trim().toLowerCase() === "chatgpt";
  if (!loginProvider) {
    return false;
  }
  return !provider.auth_status?.authenticated && !provider.auth_status?.configured;
}

export function compareProviderDraftCards(left: ProviderDraft, right: ProviderDraft) {
  const leftRank = PROVIDER_CARD_ORDER[normalizeProviderId(left.provider_id)] ?? 100;
  const rightRank = PROVIDER_CARD_ORDER[normalizeProviderId(right.provider_id)] ?? 100;
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  const labelCompare = left.label.localeCompare(right.label);
  if (labelCompare !== 0) {
    return labelCompare;
  }
  return left.provider_id.localeCompare(right.provider_id);
}

export function dedupeStrings(values: string[]) {
  const items: string[] = [];
  const seen = new Set<string>();
  for (const rawValue of values) {
    const value = String(rawValue || "").trim();
    if (!value) {
      continue;
    }
    const identity = value.toLowerCase();
    if (seen.has(identity)) {
      continue;
    }
    seen.add(identity);
    items.push(value);
  }
  return items;
}

export function clearProviderModelSelection(
  provider: Pick<ProviderDraft, "discovered_models" | "selected_models" | "model_settings">,
) {
  provider.discovered_models = [];
  provider.selected_models = [];
  provider.model_settings = {};
}

export function buildApiKeyPreview(value: unknown) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= 4) {
    return "*".repeat(text.length);
  }
  if (text.length <= 8) {
    return `${text.slice(0, 2)}${"*".repeat(text.length - 4)}${text.slice(-2)}`;
  }
  if (text.length <= 12) {
    return `${text.slice(0, 3)}${"*".repeat(text.length - 6)}${text.slice(-3)}`;
  }
  return `${text.slice(0, 8)}${"*".repeat(text.length - 12)}${text.slice(-4)}`;
}

export function clampSettingsTemperature(value: number) {
  if (!Number.isFinite(value)) {
    return DEFAULT_AGENT_TEMPERATURE;
  }
  return Math.min(2, Math.max(0, value));
}

export function clampProviderRequestTimeoutSeconds(value: number | null | undefined) {
  if (!Number.isFinite(value)) {
    return DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS;
  }
  return Math.min(3600, Math.max(1, Number(value)));
}

export function clampModelCompressionThreshold(value: number | null | undefined) {
  if (!Number.isFinite(value)) {
    return DEFAULT_MODEL_COMPRESSION_THRESHOLD;
  }
  return Math.min(1, Math.max(0.01, Number(value)));
}

export function normalizeContextWindowKTokens(value: number | null | undefined) {
  if (!Number.isFinite(value)) {
    return null;
  }
  const normalized = Math.round(Number(value));
  return normalized > 0 ? normalized : null;
}

export function normalizeStructuredOutputMode(value: unknown): StructuredOutputMode {
  return value === "native_schema_first" ? "native_schema_first" : DEFAULT_STRUCTURED_OUTPUT_MODE;
}

const MODEL_CAPABILITY_KEYS: ModelCapabilityKey[] = [
  "chat",
  "embedding",
  "rerank",
  "vision",
  "tool_call",
  "structured_output",
];
const MODEL_PURPOSE_KEYS: ModelPurpose[] = ["chat", "embedding", "rerank"];

const EMBEDDING_MODEL_PATTERNS = [
  "embedding",
  "embed",
  "text-embedding",
  "qwen3-embedding",
  "bge",
  "e5",
  "gte",
  "jina-embeddings",
  "nomic-embed",
  "snowflake-arctic-embed",
  "voyage",
  "mxbai-embed",
];

const RERANK_MODEL_PATTERNS = [
  "rerank",
  "reranker",
  "bge-reranker",
  "gte-rerank",
  "qwen-rerank",
];

function defaultModelCapabilities(chat = true): ProviderModelCapabilities {
  return {
    chat,
    embedding: false,
    rerank: false,
    vision: false,
    tool_call: false,
    structured_output: false,
  };
}

export function isModelPurposeKey(value: ModelCapabilityKey): value is ModelPurpose {
  return MODEL_PURPOSE_KEYS.includes(value as ModelPurpose);
}

export function resolveModelPurpose(capabilities: ProviderModelCapabilities): ModelPurpose {
  if (capabilities.embedding) {
    return "embedding";
  }
  if (capabilities.rerank) {
    return "rerank";
  }
  return "chat";
}

export function applyModelPurpose(
  capabilities: ProviderModelCapabilities,
  purpose: ModelPurpose,
): ProviderModelCapabilities {
  const next: ProviderModelCapabilities = {
    ...capabilities,
    chat: purpose === "chat",
    embedding: purpose === "embedding",
    rerank: purpose === "rerank",
  };
  if (purpose !== "chat") {
    next.vision = false;
    next.tool_call = false;
    next.structured_output = false;
  }
  return next;
}

function normalizeModelCapabilities(value: unknown, fallback: ProviderModelCapabilities): ProviderModelCapabilities {
  const normalized = { ...fallback };
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return applyModelPurpose(normalized, resolveModelPurpose(normalized));
  }
  const record = value as Record<string, unknown>;
  for (const key of MODEL_CAPABILITY_KEYS) {
    if (key in record) {
      normalized[key] = Boolean(record[key]);
    }
  }
  return applyModelPurpose(normalized, resolveModelPurpose(normalized));
}

function includesAnyPattern(modelName: string, patterns: string[]) {
  const normalized = modelName.trim().toLowerCase();
  return patterns.some((pattern) => normalized.includes(pattern));
}

export function inferModelCapabilities(modelName: string, explicit?: unknown): ProviderModelCapabilities {
  const normalizedModel = String(modelName || "").trim();
  const rerank = includesAnyPattern(normalizedModel, RERANK_MODEL_PATTERNS);
  const embedding = !rerank && includesAnyPattern(normalizedModel, EMBEDDING_MODEL_PATTERNS);
  const inferred = defaultModelCapabilities(!embedding && !rerank);
  inferred.embedding = embedding;
  inferred.rerank = rerank;
  return normalizeModelCapabilities(explicit, inferred);
}

function defaultEmbeddingDraft(): ProviderModelEmbeddingDraft {
  return {
    dimensions: null,
  };
}

function normalizeEmbeddingDraft(value: unknown): ProviderModelEmbeddingDraft {
  const fallback = defaultEmbeddingDraft();
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return fallback;
  }
  const record = value as Partial<ProviderModelEmbeddingDraft>;
  const dimensions = Number(record.dimensions);
  return {
    dimensions: Number.isFinite(dimensions) && dimensions > 0 ? Math.trunc(dimensions) : null,
  };
}

function normalizeProviderCredentialPool(value: unknown): SettingsProviderCredential[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const credentials: SettingsProviderCredential[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      continue;
    }
    const record = item as Partial<SettingsProviderCredential>;
    const credentialId = String(record.credential_id || "").trim();
    if (!credentialId) {
      continue;
    }
    const identity = credentialId.toLowerCase();
    if (seen.has(identity)) {
      continue;
    }
    seen.add(identity);
    const failureCount = Number(record.failure_count);
    credentials.push({
      credential_id: credentialId,
      status: String(record.status || "active").trim() || "active",
      cooldown_until: record.cooldown_until ? String(record.cooldown_until).trim() : null,
      failure_count: Number.isFinite(failureCount) ? Math.max(0, Math.trunc(failureCount)) : 0,
    });
  }
  return credentials;
}

function buildDefaultProviderModelDraft(model: string, capabilities?: unknown): ProviderModelDraft {
  return {
    model,
    reasoning: null,
    context_window_ktokens: null,
    compression_threshold: DEFAULT_MODEL_COMPRESSION_THRESHOLD,
    capabilities: inferModelCapabilities(model, capabilities),
    embedding: defaultEmbeddingDraft(),
  };
}

function normalizeModelReasoning(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function modelSettingsKey(model: string) {
  return String(model || "").trim().toLowerCase();
}

function findProviderModelDraft(provider: ProviderDraft, modelName: string): ProviderModelDraft | null {
  const normalizedModel = modelName.trim();
  if (!normalizedModel || !provider.model_settings) {
    return null;
  }
  const existing = provider.model_settings[normalizedModel];
  if (existing) {
    return existing;
  }
  const matchingKey = Object.keys(provider.model_settings).find(
    (key) => modelSettingsKey(key) === modelSettingsKey(normalizedModel),
  );
  return matchingKey ? provider.model_settings[matchingKey] ?? null : null;
}

function buildProviderModelSettings(provider: SettingsProvider, selectedModels: string[]) {
  const settings: Record<string, ProviderModelDraft> = {};
  const sourceModels = [
    ...(provider.discovered_models ?? []),
    ...provider.models,
  ];
  for (const model of sourceModels) {
    const modelName = String(model.model || "").trim();
    if (!modelName) {
      continue;
    }
    const contextWindowTokens = Number(model.context_window);
    const rawEmbedding = "embedding" in model ? (model as { embedding?: unknown }).embedding : undefined;
    settings[modelName] = {
      model: modelName,
      reasoning: normalizeModelReasoning(model.reasoning),
      context_window_ktokens: Number.isFinite(contextWindowTokens) && contextWindowTokens > 0
        ? Math.round(contextWindowTokens / 1000)
        : null,
      compression_threshold: clampModelCompressionThreshold(model.compression_threshold),
      capabilities: inferModelCapabilities(modelName, model.capabilities),
      embedding: normalizeEmbeddingDraft(rawEmbedding),
    };
  }
  for (const modelName of selectedModels) {
    if (!settings[modelName]) {
      settings[modelName] = buildDefaultProviderModelDraft(modelName);
    }
  }
  return settings;
}

export function ensureProviderModelDraft(provider: ProviderDraft, modelName: string): ProviderModelDraft {
  const normalizedModel = modelName.trim();
  if (!normalizedModel) {
    return buildDefaultProviderModelDraft("");
  }
  provider.model_settings = provider.model_settings ?? {};
  const existing = provider.model_settings[normalizedModel];
  if (existing) {
    existing.reasoning = normalizeModelReasoning(existing.reasoning);
    existing.capabilities = normalizeModelCapabilities(existing.capabilities, inferModelCapabilities(normalizedModel));
    existing.embedding = normalizeEmbeddingDraft(existing.embedding);
    return existing;
  }
  const matchingKey = Object.keys(provider.model_settings).find(
    (key) => modelSettingsKey(key) === modelSettingsKey(normalizedModel),
  );
  if (matchingKey) {
    const matched = provider.model_settings[matchingKey];
    provider.model_settings[normalizedModel] = { ...matched, model: normalizedModel };
    return provider.model_settings[normalizedModel];
  }
  provider.model_settings[normalizedModel] = buildDefaultProviderModelDraft(normalizedModel);
  return provider.model_settings[normalizedModel];
}

export function readProviderModelDraft(provider: ProviderDraft, modelName: string): ProviderModelDraft {
  const normalizedModel = modelName.trim();
  const existing = findProviderModelDraft(provider, normalizedModel);
  if (!existing) {
    return buildDefaultProviderModelDraft(normalizedModel);
  }
  return {
    ...existing,
    model: normalizedModel || existing.model,
    reasoning: normalizeModelReasoning(existing.reasoning),
    capabilities: normalizeModelCapabilities(existing.capabilities, inferModelCapabilities(normalizedModel)),
    embedding: normalizeEmbeddingDraft(existing.embedding),
  };
}

export function modelHasCapability(provider: ProviderDraft, modelName: string, capability: ModelCapabilityKey) {
  return Boolean(readProviderModelDraft(provider, modelName).capabilities[capability]);
}

export function applyDiscoveredModelItemsToDraft(
  provider: ProviderDraft,
  modelItems: Array<Partial<SettingsProviderModel> & { model: string }> | undefined,
) {
  if (!Array.isArray(modelItems)) {
    return;
  }
  for (const item of modelItems) {
    const modelName = String(item.model || "").trim();
    if (!modelName) {
      continue;
    }
    const modelSettings = ensureProviderModelDraft(provider, modelName);
    const contextWindow = Number(item.context_window);
    const reasoning = normalizeModelReasoning(item.reasoning);
    if (reasoning !== null) {
      modelSettings.reasoning = reasoning;
    }
    modelSettings.context_window_ktokens = Number.isFinite(contextWindow) && contextWindow > 0
      ? Math.round(contextWindow / 1000)
      : modelSettings.context_window_ktokens;
    modelSettings.compression_threshold = clampModelCompressionThreshold(
      typeof item.compression_threshold === "number" ? item.compression_threshold : modelSettings.compression_threshold,
    );
    modelSettings.capabilities = inferModelCapabilities(modelName, item.capabilities);
    if (item.embedding) {
      const dimensions = Number(item.embedding.dimensions);
      modelSettings.embedding = {
        dimensions: Number.isFinite(dimensions) && dimensions > 0 ? Math.trunc(dimensions) : null,
      };
    }
  }
}

export function listProviderModelBadges(
  provider: SettingsProvider,
  modelDisplayLookup: Record<string, string>,
) {
  if (provider.models.length > 0) {
    return provider.models.map((model) => modelDisplayLookup[model.model_ref] || model.model_ref);
  }
  return provider.example_model_refs;
}

export function buildProviderDraftsFromSettings(payload: SettingsPayload): Record<string, ProviderDraft> {
  const providers = payload.model_catalog?.providers ?? [];
  return Object.fromEntries(
    providers
      .filter((provider) => provider.configured || provider.saved || isDefaultProviderCardVisible(provider))
      .map((provider) => {
        const signedOutLoginProvider = isSignedOutLoginProvider(provider);
        const enabledModels = signedOutLoginProvider ? [] : dedupeStrings(provider.models.map((model) => model.model));
        const discoveredModels = signedOutLoginProvider
          ? []
          : dedupeStrings(
              (provider.discovered_models && provider.discovered_models.length > 0
                ? provider.discovered_models
                : provider.models
              ).map((model) => model.model),
            );
        const modelSettings = signedOutLoginProvider ? {} : buildProviderModelSettings(provider, enabledModels);
        return [
          provider.provider_id,
          {
            provider_id: provider.provider_id,
            label: provider.label,
            transport: provider.transport,
            structured_output_mode: normalizeStructuredOutputMode(provider.structured_output_mode),
            base_url: provider.base_url,
            enabled: provider.enabled,
            saved: Boolean(provider.saved),
            auth_header: provider.auth_header ?? "Authorization",
            auth_scheme: provider.auth_scheme ?? "Bearer",
            auth_mode: provider.auth_mode ?? (provider.requires_login ? "chatgpt" : "api_key"),
            requires_login: Boolean(provider.requires_login),
            auth_status: provider.auth_status,
            request_timeout_seconds: clampProviderRequestTimeoutSeconds(provider.request_timeout_seconds),
            credential_pool: normalizeProviderCredentialPool(provider.credential_pool),
            api_key: "",
            api_key_configured: Boolean(provider.api_key_configured),
            api_key_preview: String(provider.api_key_preview || "").trim(),
            discovered_models: discoveredModels,
            selected_models: enabledModels,
            model_settings: modelSettings,
          },
        ];
      }),
  );
}

export function buildProviderSavePayload(drafts: Record<string, ProviderDraft>): Record<string, SettingsModelProviderUpdate> {
  return Object.fromEntries(
    Object.entries(drafts).map(([providerId, draft]) => [
      providerId,
      {
        label: draft.label,
        transport: draft.transport,
        structured_output_mode: normalizeStructuredOutputMode(draft.structured_output_mode),
        base_url: draft.base_url,
        api_key: draft.requires_login ? undefined : draft.api_key.trim() || undefined,
        enabled: draft.enabled,
        auth_header: draft.auth_header,
        auth_scheme: draft.auth_scheme,
        auth_mode: draft.auth_mode ?? (draft.requires_login ? "chatgpt" : "api_key"),
        request_timeout_seconds: clampProviderRequestTimeoutSeconds(draft.request_timeout_seconds),
        credential_pool: normalizeProviderCredentialPool(draft.credential_pool),
        models: dedupeStrings(draft.selected_models).map((model) => {
          const modelSettings = ensureProviderModelDraft(draft, model);
          const contextWindowKTokens = normalizeContextWindowKTokens(modelSettings.context_window_ktokens);
          return {
            model,
            label: model,
            reasoning: modelSettings.reasoning,
            modalities: modelSettings.capabilities.vision ? ["text", "image"] : ["text"],
            capabilities: { ...modelSettings.capabilities },
            context_window: modelSettings.capabilities.chat && contextWindowKTokens !== null ? contextWindowKTokens * 1000 : null,
            compression_threshold: modelSettings.capabilities.chat
              ? clampModelCompressionThreshold(modelSettings.compression_threshold)
              : null,
            embedding: modelSettings.capabilities.embedding ? { dimensions: modelSettings.embedding.dimensions } : undefined,
          };
        }),
      },
    ]),
  );
}

export function listAddableProviderTemplates(
  payload: SettingsPayload,
  drafts: Record<string, ProviderDraft>,
): SettingsModelProvider[] {
  const existing = new Set(Object.keys(drafts));
  return (payload.model_catalog?.provider_templates ?? []).filter((provider) => !existing.has(provider.provider_id));
}

export function providerDraftsFingerprint(drafts: Record<string, ProviderDraft>): string {
  return JSON.stringify(buildProviderSavePayload(drafts));
}
