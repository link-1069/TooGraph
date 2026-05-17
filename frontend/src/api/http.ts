export const API_BASE = import.meta.env?.VITE_API_BASE_URL?.trim() || "";

const MAX_HTTP_ERROR_DETAIL_LENGTH = 1200;

export type ApiValidationIssue = {
  code: string;
  message: string;
  path: string | null;
};

type ApiHttpErrorInput = {
  message: string;
  method: string;
  path: string;
  status: number;
  payload: unknown;
};

export class ApiHttpError extends Error {
  readonly method: string;
  readonly path: string;
  readonly status: number;
  readonly payload: unknown;
  readonly detail: unknown;
  readonly validationIssues: ApiValidationIssue[];

  constructor(input: ApiHttpErrorInput) {
    super(input.message);
    this.name = "ApiHttpError";
    this.method = input.method;
    this.path = input.path;
    this.status = input.status;
    this.payload = input.payload;
    this.detail = isRecord(input.payload) && "detail" in input.payload ? input.payload.detail : input.payload;
    this.validationIssues = extractApiValidationIssues(this.detail);
    Object.setPrototypeOf(this, ApiHttpError.prototype);
  }
}

function buildApiUrl(path: string): string {
  if (!API_BASE) {
    return path;
  }

  return `${API_BASE.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function truncateHttpErrorDetail(value: string): string {
  if (value.length <= MAX_HTTP_ERROR_DETAIL_LENGTH) {
    return value;
  }
  return `${value.slice(0, MAX_HTTP_ERROR_DETAIL_LENGTH - 1)}...`;
}

function extractApiValidationIssues(value: unknown): ApiValidationIssue[] {
  if (!isRecord(value) || !Array.isArray(value.issues)) {
    return [];
  }

  return value.issues
    .map((issue) => {
      if (!isRecord(issue)) {
        return null;
      }
      const code = typeof issue.code === "string" ? issue.code.trim() : "";
      const message = typeof issue.message === "string" ? issue.message.trim() : "";
      const path = typeof issue.path === "string" ? issue.path.trim() : null;
      if (!code && !message && !path) {
        return null;
      }
      return { code, message, path } satisfies ApiValidationIssue;
    })
    .filter((issue): issue is ApiValidationIssue => issue !== null);
}

function formatValidationIssues(value: unknown): string {
  const issues = extractApiValidationIssues(value);
  if (!issues.length) {
    return "";
  }

  const issueMessages = issues.slice(0, 5).map((issue) => {
    const label = issue.message || issue.code;
    if (!label) {
      return "";
    }
    return issue.path ? `${label} (${issue.path})` : label;
  });

  const formattedIssues = issueMessages.filter(Boolean);
  if (issues.length > formattedIssues.length) {
    formattedIssues.push(`还有 ${issues.length - formattedIssues.length} 个问题`);
  }
  return formattedIssues.join("; ");
}

function formatFastApiValidationDetails(value: unknown): string {
  if (!Array.isArray(value)) {
    return "";
  }

  const detailMessages = value.slice(0, 5).map((detail) => {
    if (!isRecord(detail)) {
      return "";
    }
    const message = typeof detail.msg === "string" ? detail.msg.trim() : "";
    const type = typeof detail.type === "string" ? detail.type.trim() : "";
    const label = message || type;
    if (!label) {
      return "";
    }
    const location = Array.isArray(detail.loc)
      ? detail.loc
          .map((part) => (typeof part === "string" || typeof part === "number" ? String(part) : ""))
          .filter(Boolean)
          .join(".")
      : "";
    return location ? `${label} (${location})` : label;
  });

  const formattedDetails = detailMessages.filter(Boolean);
  if (value.length > formattedDetails.length) {
    formattedDetails.push(`还有 ${value.length - formattedDetails.length} 个问题`);
  }
  return formattedDetails.join("; ");
}

function formatHttpErrorPayload(payload: unknown): string {
  const detail = isRecord(payload) && "detail" in payload ? payload.detail : payload;

  if (typeof detail === "string") {
    return detail.trim();
  }

  const validationMessage = formatValidationIssues(detail);
  if (validationMessage) {
    return validationMessage;
  }

  const fastApiValidationMessage = formatFastApiValidationDetails(detail);
  if (fastApiValidationMessage) {
    return fastApiValidationMessage;
  }

  if (isRecord(detail)) {
    if (typeof detail.message === "string") {
      return detail.message.trim();
    }
    if (typeof detail.error === "string") {
      return detail.error.trim();
    }
  }

  if (isRecord(payload)) {
    if (typeof payload.message === "string") {
      return payload.message.trim();
    }
    if (typeof payload.error === "string") {
      return payload.error.trim();
    }
  }

  try {
    return JSON.stringify(payload);
  } catch {
    return "";
  }
}

async function buildHttpError(response: Response, method: string, path: string): Promise<ApiHttpError> {
  const baseMessage = `${method} ${path} failed with status ${response.status}`;
  let responseText = "";

  try {
    responseText = await response.text();
  } catch {
    return new ApiHttpError({
      message: baseMessage,
      method,
      path,
      status: response.status,
      payload: null,
    });
  }

  const trimmedText = responseText.trim();
  if (!trimmedText) {
    return new ApiHttpError({
      message: baseMessage,
      method,
      path,
      status: response.status,
      payload: null,
    });
  }

  let detail = "";
  let payload: unknown = trimmedText;
  try {
    payload = JSON.parse(trimmedText) as unknown;
    detail = formatHttpErrorPayload(payload);
  } catch {
    detail = trimmedText;
  }

  const trimmedDetail = truncateHttpErrorDetail(detail.trim());
  return new ApiHttpError({
    message: trimmedDetail ? `${baseMessage}: ${trimmedDetail}` : baseMessage,
    method,
    path,
    status: response.status,
    payload,
  });
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), init);
  if (!response.ok) {
    throw await buildHttpError(response, "GET", path);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await buildHttpError(response, "POST", path);
  }
  return response.json() as Promise<T>;
}

export async function apiPut<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await buildHttpError(response, "PUT", path);
  }
  return response.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await buildHttpError(response, "PATCH", path);
  }
  return response.json() as Promise<T>;
}

export async function apiPostText(path: string, payload: unknown): Promise<string> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await buildHttpError(response, "POST", path);
  }
  return response.text();
}

export async function apiPostForm<T>(path: string, payload: FormData): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    body: payload,
  });
  if (!response.ok) {
    throw await buildHttpError(response, "POST", path);
  }
  return response.json() as Promise<T>;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "DELETE",
  });
  if (!response.ok) {
    throw await buildHttpError(response, "DELETE", path);
  }
  return response.json() as Promise<T>;
}
