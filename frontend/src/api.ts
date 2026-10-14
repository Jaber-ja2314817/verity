import type { Benchmark, CheckRecord, CheckRequest, Example, Health } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter?: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach Verity. Check your connection and try again.", 0);
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
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  examples: () => request<Example[]>("/api/examples"),
  benchmark: () => request<Benchmark>("/api/benchmark"),
  getCheck: (id: string) => request<CheckRecord>(`/api/checks/${encodeURIComponent(id)}`),
  createCheck: (body: CheckRequest) =>
    request<{ id: string }>("/api/checks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  eventsUrl: (id: string) => `/api/checks/${encodeURIComponent(id)}/events`,
};

export const GITHUB_URL = "https://github.com/Jaber-ja2314817/verity";
