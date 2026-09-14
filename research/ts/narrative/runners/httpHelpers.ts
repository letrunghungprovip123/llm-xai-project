import { sleep } from "../../common/utils";

export interface HttpRequestOptions {
  url: string;
  headers: Record<string, string>;
  body: unknown;
  timeout_ms: number;
  max_retries: number;
  retry_delay_ms: number;
}

export interface HttpResponseResult {
  ok: boolean;
  status_code: number | null;
  response_json: unknown | null;
  response_text: string | null;
  retry_count: number;
  latency_ms: number;
  error_type: string | null;
  error_message: string | null;
}

// Gọi JSON API với backoff tuyến tính và giữ đúng số lần retry đã thực sự xảy ra.
export async function postJsonWithRetry(
  options: HttpRequestOptions,
): Promise<HttpResponseResult> {
  const startedAt = Date.now();
  let lastErrorType: string | null = null;
  let lastErrorMessage: string | null = null;
  let lastStatusCode: number | null = null;
  let lastResponseText: string | null = null;
  let actualRetryCount = 0;

  for (let attempt = 0; attempt <= options.max_retries; attempt += 1) {
    actualRetryCount = attempt;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout_ms);

    try {
      const response = await fetch(options.url, {
        method: "POST",
        headers: options.headers,
        body: JSON.stringify(options.body),
        signal: controller.signal,
      });

      clearTimeout(timeout);
      lastStatusCode = response.status;
      lastResponseText = await response.text();

      let responseJson: unknown | null = null;
      if (lastResponseText) {
        try {
          responseJson = JSON.parse(lastResponseText);
        } catch {
          responseJson = null;
        }
      }

      if (response.ok) {
        return {
          ok: true,
          status_code: response.status,
          response_json: responseJson,
          response_text: lastResponseText,
          retry_count: attempt,
          latency_ms: Date.now() - startedAt,
          error_type: null,
          error_message: null,
        };
      }

      lastErrorType = `HTTP_${response.status}`;
      lastErrorMessage =
        readApiErrorMessage(responseJson) ||
        lastResponseText ||
        response.statusText;

      if (
        !shouldRetryStatus(response.status) ||
        attempt >= options.max_retries
      ) {
        break;
      }
    } catch (error) {
      clearTimeout(timeout);
      const message = error instanceof Error ? error.message : String(error);
      const isTimeout = error instanceof Error && error.name === "AbortError";

      lastErrorType = isTimeout ? "TIMEOUT" : "NETWORK_ERROR";
      lastErrorMessage = message;

      if (attempt >= options.max_retries) {
        break;
      }
    }

    await sleep(options.retry_delay_ms * (attempt + 1));
  }

  return {
    ok: false,
    status_code: lastStatusCode,
    response_json: null,
    response_text: lastResponseText,
    retry_count: actualRetryCount,
    latency_ms: Date.now() - startedAt,
    error_type: lastErrorType || "UNKNOWN_HTTP_ERROR",
    error_message: lastErrorMessage || "Request failed.",
  };
}

function shouldRetryStatus(status: number): boolean {
  return status === 408 || status === 409 || status === 429 || status >= 500;
}

function readApiErrorMessage(value: unknown): string | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const source = value as Record<string, unknown>;
  const error = source.error;

  if (typeof error === "string") {
    return error;
  }

  if (error && typeof error === "object") {
    const errorObject = error as Record<string, unknown>;
    if (typeof errorObject.message === "string") {
      return errorObject.message;
    }
  }

  return null;
}
