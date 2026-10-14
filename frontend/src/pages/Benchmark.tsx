import { useEffect, useState } from "react";
import { api, GITHUB_URL } from "../api";
import type { Benchmark as BenchmarkData } from "../types";

interface ModeStats {
  accuracy?: number;
  abstain_rate?: number;
  avg_cost_usd?: number;
  avg_time_s?: number;
}

interface Metric {
  key: keyof ModeStats;
  label: string;
  format: (v: number) => string;
  better: "higher" | "lower";
}

const METRICS: Metric[] = [
  { key: "accuracy", label: "Accuracy", format: pct, better: "higher" },
  { key: "abstain_rate", label: "Abstain rate", format: pct, better: "lower" },
  { key: "avg_cost_usd", label: "Avg. cost per claim", format: (v) => `$${v.toFixed(4)}`, better: "lower" },
  { key: "avg_time_s", label: "Avg. time per claim", format: (v) => `${v.toFixed(1)} s`, better: "lower" },
];

function pct(v: number): string {
  // Accept 0..1 fractions or 0..100 percentages.
  return `${(v <= 1 ? v * 100 : v).toFixed(1)}%`;
}

function num(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function stats(v: unknown): ModeStats | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const s: ModeStats = {
    accuracy: num(o.accuracy),
    abstain_rate: num(o.abstain_rate),
    avg_cost_usd: num(o.avg_cost_usd),
    avg_time_s: num(o.avg_time_s),
  };
  return Object.values(s).some((x) => x !== undefined) ? s : null;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v : typeof v === "number" ? String(v) : undefined;
}

function Bars({ metric, single, jury }: { metric: Metric; single?: number; jury?: number }) {
  const max = Math.max(single ?? 0, jury ?? 0) || 1;
  const rows = [
    { name: "Single model", value: single, accent: false },
    { name: "Two-model jury", value: jury, accent: true },
  ];
  return (
    <figure className="rounded-xl border border-line bg-surface p-5">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">{metric.label}</span>
        <span className="text-xs text-muted">{metric.better} is better</span>
      </figcaption>
      <div className="mt-4 space-y-3">
        {rows.map((r) => (
          <div key={r.name}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-muted">{r.name}</span>
              <span className="font-medium tabular-nums">{r.value === undefined ? "—" : metric.format(r.value)}</span>
            </div>
            <svg viewBox="0 0 100 6" preserveAspectRatio="none" className="block h-2.5 w-full" role="img" aria-label={`${r.name}: ${r.value === undefined ? "no data" : metric.format(r.value)}`}>
              <rect x="0" y="0" width="100" height="6" rx="3" className="fill-line" />
              {r.value !== undefined && (
                <rect
                  x="0"
                  y="0"
                  width={Math.max(1.5, (r.value / max) * 100)}
                  height="6"
                  rx="3"
                  className={r.accent ? "fill-accent" : "fill-muted"}
                />
              )}
            </svg>
          </div>
        ))}
      </div>
    </figure>
  );
}

function ComingSoon() {
  return (
    <div className="mt-10 rounded-2xl border border-dashed border-line bg-surface p-8 sm:p-10">
      <p className="font-serif text-2xl tracking-tight">Benchmark coming soon</p>
      <p className="mt-3 max-w-xl leading-relaxed text-muted">
        We're running Verity on a labeled set of claims to compare a single model against the
        two-model jury. Real numbers will appear here once the run is done. We don't publish
        estimates.
      </p>
    </div>
  );
}

export default function Benchmark() {
  const [data, setData] = useState<BenchmarkData | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    api
      .benchmark()
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, []);

  const single = data ? stats(data.single) : null;
  const jury = data ? stats(data.jury) : null;
  const hasData = !!(single || jury);
  const n = data ? str(data.n) : undefined;
  const date = data ? str(data.date) : undefined;
  const description = data ? str(data.description) : undefined;
  const metrics = METRICS.filter((m) => single?.[m.key] !== undefined || jury?.[m.key] !== undefined);

  return (
    <article className="pt-6 sm:pt-12">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-ink">Benchmark</p>
      <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-[1.1] tracking-tight sm:text-5xl">
        Measured, not claimed.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
        One fast model alone versus the two-model jury, on the same claims and the same sources.
      </p>

      {data === undefined ? (
        <div className="mt-10 grid gap-4 sm:grid-cols-2" aria-busy="true" aria-label="Loading benchmark">
          {[0, 1].map((i) => (
            <div key={i} className="h-36 animate-pulse rounded-xl bg-line" />
          ))}
        </div>
      ) : !hasData ? (
        <ComingSoon />
      ) : (
        <>
          <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-3 text-sm">
            {n && (
              <div>
                <dt className="text-muted">Labeled claims</dt>
                <dd className="font-semibold tabular-nums">{n}</dd>
              </div>
            )}
            {date && (
              <div>
                <dt className="text-muted">Run on</dt>
                <dd className="font-semibold">{date}</dd>
              </div>
            )}
          </dl>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {metrics.map((m) => (
              <Bars key={m.key} metric={m} single={single?.[m.key]} jury={jury?.[m.key]} />
            ))}
          </div>
          {description && <p className="mt-8 max-w-2xl leading-relaxed text-muted">{description}</p>}
        </>
      )}

      <p className="mt-10 text-sm text-muted">
        The test set is public:{" "}
        <a
          href={`${GITHUB_URL}/blob/main/eval/claims.jsonl`}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-ink underline decoration-accent underline-offset-4"
        >
          eval/claims.jsonl
        </a>
      </p>
    </article>
  );
}
