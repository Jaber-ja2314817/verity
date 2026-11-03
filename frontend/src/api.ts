import type {
  AdminKey,
  Benchmark,
  CheckRecord,
  CheckRequest,
  CreatedKey,
  Example,
  Health,
  NewKey,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

// Same-origin /api by default (Vite dev proxy locally, Vercel rewrite in production).
// VITE_API_URL points the client at another backend, e.g. http://localhost:8000.
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

const UNREACHABLE = "Can't reach Verity. Check your connection and try again.";

async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, init);
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* non-JSON error body */
    }
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(message, res.status, Number.isFinite(retry) && retry > 0 ? retry : undefined);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  examples: () => request<Example[]>("/api/examples"),
  benchmark: () => request<Benchmark>("/api/benchmark"),
  getCheck: (id: string) => request<CheckRecord>(`/api/checks/${encodeURIComponent(id)}`),
  /** Start a check that runs inside this request; the response is its event stream. */
  startCheck: async (body: CheckRequest, signal?: AbortSignal): Promise<ReadableStream<Uint8Array>> => {
    const res = await send("/api/checks/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.body) throw new ApiError(UNREACHABLE, 0);
    return res.body;
  },
  eventsUrl: (id: string) => `${API_BASE}/api/checks/${encodeURIComponent(id)}/events`,
};

const adminAuth = (secret: string) => ({ Authorization: `Bearer ${secret}` });

/** Key management. The admin secret is sent per request and never stored by the server's UI. */
export const adminApi = {
  list: (secret: string) => request<AdminKey[]>("/api/admin/keys", { headers: adminAuth(secret) }),
  create: (secret: string, body: NewKey) =>
    request<CreatedKey>("/api/admin/keys", {
      method: "POST",
      headers: { ...adminAuth(secret), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  revoke: (secret: string, id: string) =>
    request<{ revoked: boolean }>(`/api/admin/keys/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: adminAuth(secret),
    }),
};

export const GITHUB_URL = "https://github.com/Jaber-ja2314817/verity";
