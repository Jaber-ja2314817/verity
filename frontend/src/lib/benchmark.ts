import type { Benchmark } from "../types";

/** One mode's metrics, as written by scripts/run_eval.py compute_metrics (rates are 0..1). */
export interface ModeStats {
  n?: number;
  errors?: number;
  correct?: number;
  abstained?: number;
  accuracy?: number;
  abstain_rate?: number;
  accuracy_when_answered?: number;
  avg_cost_usd?: number;
  avg_time_s?: number;
  agreement_rate?: number;
  debate_rate?: number;
}

/** The summary written to eval/results/latest.json by build_summary. */
export interface BenchmarkSummary {
  single: ModeStats | null;
  jury: ModeStats | null;
  n?: number;
  claimsTotal?: number;
  date?: string;
  models?: { fast?: string; judge?: string };
  rule?: string;
  description?: string;
}

const STAT_KEYS: (keyof ModeStats)[] = [
  "n",
  "errors",
  "correct",
  "abstained",
  "accuracy",
  "abstain_rate",
  "accuracy_when_answered",
  "avg_cost_usd",
  "avg_time_s",
  "agreement_rate",
  "debate_rate",
];

function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v.trim() : undefined;
}

function stats(v: unknown): ModeStats | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const s: ModeStats = {};
  for (const k of STAT_KEYS) {
    const x = num(o[k]);
    if (x !== undefined) s[k] = x;
  }
  // A mode with no evaluated claims carries no information.
  if (s.n === 0 || Object.keys(s).every((k) => k === "n" || k === "errors")) return null;
  return s;
}

/** Tolerant parse: unknown fields are ignored, wrong types become undefined. */
export function parseBenchmark(data: Benchmark | null | undefined): BenchmarkSummary | null {
  if (!data || typeof data !== "object") return null;
  const single = stats(data.single);
  const jury = stats(data.jury);
  if (!single && !jury) return null;
  const m = data.models && typeof data.models === "object" ? (data.models as Record<string, unknown>) : null;
  return {
    single,
    jury,
    n: num(data.n),
    claimsTotal: num(data.claims_total),
    date: str(data.date),
    models: m ? { fast: str(m.fast), judge: str(m.judge) } : undefined,
    rule: str(data.rule),
    description: str(data.description),
  };
}

export function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}
