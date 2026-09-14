import type { ErrorResponse } from "./contracts";

export class ResearchOpsApiError extends Error {
  status: number;
  code: string;
  requestId: string;
  details: Record<string, unknown>;

  constructor(status: number, payload?: Partial<ErrorResponse>) {
    const error = payload?.error;
    super(error?.message ?? `ResearchOps request failed with HTTP ${status}`);
    this.name = "ResearchOpsApiError";
    this.status = status;
    this.code = error?.code ?? "HTTP_ERROR";
    this.requestId = error?.request_id ?? "unknown";
    this.details = error?.details ?? {};
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

function buildUrl(path: string, query?: QueryParams) {
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  const url = new URL(`/api/researchops/${normalized}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  }
  return `${url.pathname}${url.search}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    throw new ResearchOpsApiError(response.status, typeof body === "object" ? body : undefined);
  }
  return body as T;
}

export async function apiGet<T>(path: string, query?: QueryParams, signal?: AbortSignal): Promise<T> {
  return parseResponse<T>(await fetch(buildUrl(path, query), { method: "GET", cache: "no-store", signal }));
}

export async function apiPost<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  return parseResponse<T>(await fetch(buildUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
    cache: "no-store",
  }));
}

export function newCommandId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `cmd_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}
