/**
 * Shared HTTP client for the local VideoFlow API.
 *
 * The domain modules import `request`; the UI imports `ApiError`,
 * `formatBackendDetail`, and `describeError` through `$lib/api`.
 */

export class ApiError extends Error {
  code: string;
  status: number;
  detail: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    status = 0,
    detail: Record<string, unknown> = {}
  ) {
    super(message);
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

function apiDetail(payload: unknown): Record<string, unknown> {
  if (!payload || typeof payload !== "object") return {};
  const detail = (payload as { detail?: unknown }).detail;
  if (Array.isArray(detail)) {
    return {
      code: "request_invalid",
      message: detail
        .map((item) => {
          if (!item || typeof item !== "object") return String(item);
          const entry = item as { msg?: unknown; loc?: unknown };
          const location = Array.isArray(entry.loc)
            ? entry.loc.map((part) => String(part)).join(".")
            : "";
          const message = String(entry.msg ?? "Invalid request");
          return location ? `${location}: ${message}` : message;
        })
        .join("; "),
      errors: detail
    };
  }
  if (detail && typeof detail === "object") {
    return detail as Record<string, unknown>;
  }
  if (typeof detail === "string") return { message: detail };
  return {};
}

function emitApiError(error: ApiError, path: string, title: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("videoflow:api-error", {
      detail: {
        title,
        code: error.code,
        message: error.message,
        detail: describeError(error),
        path
      }
    })
  );
}

export function raiseApiError(
  response: Response,
  payload: unknown,
  path: string,
  fallbackCode = "http_error",
  init?: RequestInit
): never {
  const detail = apiDetail(payload);
  detail.path = path;
  detail.method = String(init?.method ?? "GET").toUpperCase();
  if (init?.body) {
    try {
      detail.request_body = JSON.parse(String(init.body));
    } catch {
      detail.request_body = String(init.body);
    }
  }
  const error = new ApiError(
    String(detail.code ?? fallbackCode),
    String(detail.message ?? response.statusText ?? "Request failed"),
    response.status,
    detail
  );
  emitApiError(error, path, `Backend error ${response.status}`);
  throw error;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = init?.signal ? null : new AbortController();
  const timer = controller
    ? setTimeout(() => controller.abort(), 10 * 60 * 1000)
    : undefined;
  let response: Response;
  try {
    response = await fetch(path, {
      headers:
        init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" },
      ...init,
      signal: init?.signal ?? controller?.signal
    });
  } catch (reason) {
    const timedOut = controller?.signal.aborted ?? false;
    const error = new ApiError(
      timedOut ? "request_timeout" : "network_error",
      timedOut
        ? "The backend did not answer within ten minutes."
        : reason instanceof Error
          ? reason.message
          : "The backend is unreachable."
    );
    emitApiError(error, path, timedOut ? "Backend timeout" : "Backend unreachable");
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) raiseApiError(response, payload, path, "http_error", init);
  return payload as T;
}

export function formatBackendDetail(detail: Record<string, unknown> | null | undefined): string {
  if (!detail) return "";
  const lines: string[] = [];
  if (detail.code) lines.push(`code: ${String(detail.code)}`);
  if (detail.message) lines.push(`message: ${String(detail.message)}`);
  if (detail.command) lines.push(`command: ${String(detail.command)}`);
  if (detail.returncode !== undefined) {
    lines.push(`returncode: ${String(detail.returncode)}`);
  }
  if (detail.signal !== undefined) lines.push(`signal: ${String(detail.signal)}`);
  if (detail.stderr) lines.push(`stderr:\n${String(detail.stderr)}`);
  if (detail.errors) lines.push(`errors: ${JSON.stringify(detail.errors)}`);
  return lines.join("\n");
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const lines = [
      `HTTP ${error.status}`,
      `code: ${error.code}`,
      `message: ${error.message}`
    ];
    const detail = error.detail;
    if (detail.command) lines.push(`command: ${String(detail.command)}`);
    if (detail.returncode !== undefined) {
      lines.push(`returncode: ${String(detail.returncode)}`);
    }
    if (detail.signal !== undefined) lines.push(`signal: ${String(detail.signal)}`);
    if (detail.stderr) lines.push(`stderr:\n${String(detail.stderr)}`);
    if (detail.errors) lines.push(`errors: ${JSON.stringify(detail.errors)}`);
    return lines.join("\n");
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
