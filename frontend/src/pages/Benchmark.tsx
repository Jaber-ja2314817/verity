import { useEffect, useState } from "react";
import { api, ApiError, GITHUB_URL } from "../api";
import { parseBenchmark, pct, type BenchmarkSummary, type ModeStats } from "../lib/benchmark";
import { shortModel } from "../lib/format";
import { useTitle } from "../lib/useTitle";

interface Metric {
  key: keyof ModeStats;
  label: string;
  hint: string;
  format: (v: number) => string;
  better: "higher" | "lower";
  rate: boolean; // 0..1 values: bars use an absolute 0-100% scale
}

const METRICS: Metric[] = [
  { key: "accuracy", label: "Accuracy", hint: "Correct verdicts out of all claims (Unverified counts as not correct).", format: pct, better: "higher", rate: true },
  { key: "accuracy_when_answered", label: "Accuracy when answered", hint: "Correct verdicts among claims that got True, False or Misleading.", format: pct, better: "higher", rate: true },
  { key: "abstain_rate", label: "Abstain rate", hint: "Share of claims left Unverified.", format: pct, better: "lower", rate: true },
  { key: "avg_cost_usd", label: "Avg. cost per claim", hint: "Token Factory cost, including the shared search and evidence steps.", format: (v) => `$${v.toFixed(4)}`, better: "lower", rate: false },
  { key: "avg_time_s", label: "Avg. time per claim", hint: "Wall-clock time, including the shared steps.", format: (v) => `${v.toFixed(1)} s`, better: "lower", rate: false },
];

function Bars({ metric, single, jury }: { metric: Metric; single?: number; jury?: number }) {
  // Rates are drawn on a fixed 0-100% scale so small gaps aren't visually exaggerated.
  const max = metric.rate ? 1 : Math.max(single ?? 0, jury ?? 0) || 1;
  const rows = [
    { name: "Single model", value: single, accent: false },
    { name: "Two-model jury", value: jury, accent: true },
  ];
  return (
    <figure className="rounded-xl border border-line bg-surface p-5">
      <figcaption>
        <span className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-semibold">{metric.label}</span>
          <span className="shrink-0 text-xs text-muted">{metric.better} is better</span>
        </span>
        <span className="mt-1 block text-xs leading-relaxed text-muted">{metric.hint}</span>
      </figcaption>
      <div className="mt-4 space-y-3">
        {rows.map((r) => (
          <div key={r.name}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-muted">{r.name}</span>
              <span className="font-medium tabular-nums">{r.value === undefined ? "—" : metric.format(r.value)}</span>
            </div>
            <svg
              viewBox="0 0 100 6"
              preserveAspectRatio="none"
              className="block h-2.5 w-full"
              role="img"
              aria-label={`${r.name}: ${r.value === undefined ? "no data" : metric.format(r.value)}`}
            >
              <rect x="0" y="0" width="100" height="6" rx="3" className="fill-line" />
              {r.value !== undefined && (
                <rect
                  x="0"
                  y="0"
                  width={Math.min(100, Math.max(1.5, (r.value / max) * 100))}
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

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{term}</dt>
      <dd className="break-words font-semibold tabular-nums">{children}</dd>
    </div>
  );
}

function Results({ b }: { b: BenchmarkSummary }) {
  const { single, jury } = b;
  const metrics = METRICS.filter((m) => single?.[m.key] !== undefined || jury?.[m.key] !== undefined);
  const errors = (single?.errors ?? 0) + (jury?.errors ?? 0);
  const count = (s: ModeStats | null) =>
    s && s.correct !== undefined && s.n !== undefined ? `${s.correct} / ${s.n}` : "—";
  return (
    <>
      <dl className="mt-10 grid grid-cols-2 gap-x-10 gap-y-4 text-sm sm:flex sm:flex-wrap">
        {b.n !== undefined && (
          <Fact term="Labeled claims">
            {b.n}
            {b.claimsTotal !== undefined && b.claimsTotal !== b.n && (
              <span className="font-normal text-muted"> of {b.claimsTotal}</span>
            )}
          </Fact>
        )}
        {b.date && <Fact term="Run on">{b.date}</Fact>}
        <Fact term="Correct · single">{count(single)}</Fact>
        <Fact term="Correct · jury">{count(jury)}</Fact>
        {jury?.agreement_rate !== undefined && <Fact term="Models agreed">{pct(jury.agreement_rate)}</Fact>}
        {jury?.debate_rate !== undefined && <Fact term="Needed a debate">{pct(jury.debate_rate)}</Fact>}
      </dl>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {metrics.map((m) => (
          <Bars key={m.key} metric={m} single={single?.[m.key]} jury={jury?.[m.key]} />
        ))}
      </div>
      <div className="mt-8 max-w-2xl space-y-3 text-sm leading-relaxed text-muted">
        {b.description && <p>{b.description}</p>}
        {b.rule && (
          <p>
            <span className="font-medium text-ink">Scoring rule.</span> {b.rule}
          </p>
        )}
        {(b.models?.fast || b.models?.judge) && (
          <p>
            <span className="font-medium text-ink">Models.</span>{" "}
            {b.models.fast && <>fast <code className="break-all font-mono text-xs">{shortModel(b.models.fast)}</code></>}
            {b.models.fast && b.models.judge && ", "}
            {b.models.judge && <>judge <code className="break-all font-mono text-xs">{shortModel(b.models.judge)}</code></>}
          </p>
        )}
        {errors > 0 && (
          <p>
            {errors} run{errors === 1 ? "" : "s"} failed with an error and {errors === 1 ? "is" : "are"} excluded
            from the numbers above.
          </p>
        )}
      </div>
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
        . Numbers are written by <code className="font-mono text-xs">scripts/run_eval.py</code> and never
        edited by hand.
      </p>
    </>
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

type Load = { state: "loading" } | { state: "empty" } | { state: "error" } | { state: "ready"; b: BenchmarkSummary };

export default function Benchmark() {
  useTitle("Benchmark");
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    let alive = true;
    api
      .benchmark()
      .then((d) => {
        if (!alive) return;
        const b = parseBenchmark(d);
        setLoad(b ? { state: "ready", b } : { state: "empty" });
      })
      .catch((e) => {
        if (!alive) return;
        // 404 = no results file yet; anything else is a real failure to load.
        setLoad(e instanceof ApiError && e.status === 404 ? { state: "empty" } : { state: "error" });
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <article className="pt-6 sm:pt-12">
      <p className="eyebrow text-accent">Benchmark</p>
      <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-[1.1] tracking-tight sm:text-5xl">
        Measured, not claimed.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
        One fast model alone versus the two-model jury, on the same claims and the same sources.
      </p>

      {load.state === "loading" ? (
        <div role="status" className="mt-10 grid gap-4 sm:grid-cols-2" aria-busy="true" aria-label="Loading benchmark">
          {[0, 1].map((i) => (
            <div key={i} className="h-36 animate-pulse rounded-xl bg-line motion-reduce:animate-none" />
          ))}
        </div>
      ) : load.state === "error" ? (
        <div role="alert" className="mt-10 rounded-2xl border border-line bg-surface p-8">
          <p className="font-semibold">Couldn't load the benchmark.</p>
          <p className="mt-2 text-sm text-muted">Check your connection and reload the page.</p>
        </div>
      ) : load.state === "empty" ? (
        <ComingSoon />
      ) : (
        <Results b={load.b} />
      )}
    </article>
  );
}
