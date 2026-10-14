import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Health } from "../types";

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export const STEP_ICONS: Record<"claims" | "search" | "jury" | "verdict", ReactNode> = {
  claims: (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden {...stroke}>
      <path d="M5 6h14M5 11h9M5 16h11" />
      <circle cx="18.5" cy="16" r="1.4" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden {...stroke}>
      <circle cx="10.5" cy="10.5" r="5.5" />
      <path d="M15 15l4.5 4.5" />
    </svg>
  ),
  jury: (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden {...stroke}>
      <circle cx="8" cy="8.5" r="2.6" />
      <circle cx="16" cy="8.5" r="2.6" />
      <path d="M3.5 18.5c.6-3 2.4-4.6 4.5-4.6s3.9 1.6 4.5 4.6M11.5 18.5c.6-3 2.4-4.6 4.5-4.6s3.9 1.6 4.5 4.6" />
    </svg>
  ),
  verdict: (
    <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden {...stroke}>
      <path d="M12 3.5l7 3v5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9v-5l7-3z" />
      <path d="M8.8 12.2l2.2 2.2 4.2-4.4" />
    </svg>
  ),
};

interface Stage {
  n: string;
  title: string;
  model: "fast" | "judge" | "code" | "search";
  body: string;
  highlight?: boolean;
}

const STAGES: Stage[] = [
  { n: "01", title: "Read", model: "code", body: "Your text, or the article behind a link, is cleaned up and trimmed." },
  { n: "02", title: "Find claims", model: "fast", body: "The text is split into self-contained, checkable factual claims. Opinions and predictions are set aside." },
  { n: "03", title: "Plan searches", model: "fast", body: "Three queries per claim: one neutral, one looking for support, one looking for debunks." },
  { n: "04", title: "Search the web", model: "search", body: "Results are merged, de-duplicated and capped per site so one source can't dominate." },
  { n: "05", title: "Check evidence", model: "fast", body: "For each source the model copies the one sentence that matters, word for word. Code then confirms the sentence really is on the page.", highlight: true },
  { n: "06", title: "Two-model jury", model: "judge", body: "A fast model drafts a verdict while Nemotron Ultra judges the same evidence on its own, without seeing the draft.", highlight: true },
  { n: "07", title: "Debate if needed", model: "judge", body: "If they disagree, Verity searches for the missing evidence and Ultra makes the final ruling." },
];

function modelName(stage: Stage, health: Health | null, failed: boolean): string {
  if (stage.model === "code") return "Plain code";
  if (stage.model === "search") return "Tavily search";
  if (health) return stage.model === "fast" ? health.models.fast : health.models.judge;
  if (failed) return stage.model === "fast" ? "Fast Nemotron model" : "Judge Nemotron model";
  return "Loading…";
}

export default function HowItWorks() {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <article className="pt-6 sm:pt-12">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-ink">How it works</p>
      <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-[1.1] tracking-tight sm:text-5xl">
        Every verdict shows its work.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
        Verity doesn't give one confident answer. It breaks your text into claims, gathers evidence
        from the live web, and has two different NVIDIA Nemotron models judge each claim.
      </p>

      <ol className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        {STAGES.map((s) => (
          <li key={s.n} className={`flex flex-col gap-3 p-5 sm:p-6 ${s.highlight ? "bg-surface" : "bg-paper"}`}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-serif text-2xl text-muted tabular-nums">{s.n}</span>
              <span
                className={`max-w-[70%] truncate rounded-full border px-2 py-0.5 font-mono text-[11px] ${
                  s.model === "judge"
                    ? "border-accent/40 text-accent-ink"
                    : "border-line text-muted"
                }`}
                title={modelName(s, health, failed)}
              >
                {modelName(s, health, failed)}
              </span>
            </div>
            <h2 className="text-lg font-semibold tracking-tight">{s.title}</h2>
            <p className="text-sm leading-relaxed text-muted">{s.body}</p>
          </li>
        ))}
        <li className="flex flex-col justify-center gap-2 bg-ink p-5 text-paper sm:p-6">
          <span className="text-accent">{STEP_ICONS.verdict}</span>
          <h2 className="text-lg font-semibold">Verdict</h2>
          <p className="text-sm leading-relaxed opacity-80">
            True, False, Misleading or Unverified, with confidence, sources and the full model trace.
          </p>
        </li>
      </ol>

      <div className="mt-16 grid gap-10 md:grid-cols-2">
        <section>
          <h2 className="font-serif text-2xl tracking-tight">Quotes are checked by code</h2>
          <p className="mt-3 leading-relaxed text-muted">
            Language models sometimes invent quotes. So the model must copy a sentence from the
            source exactly, and Verity then searches the page for that sentence, ignoring only case,
            spacing and punctuation. If it isn't there, the quote is thrown out and never reaches the
            jury. You see a small count of discarded quotes on every claim.
          </p>
        </section>
        <section>
          <h2 className="font-serif text-2xl tracking-tight">Two models, judged independently</h2>
          <p className="mt-3 leading-relaxed text-muted">
            The fast model drafts a verdict. At the same time,{" "}
            <span className="font-medium text-ink">{health ? health.models.judge : "the judge model"}</span>{" "}
            reads the same evidence without seeing that draft. If they agree, you get their shared
            verdict. If they don't, Verity runs extra searches for what's missing and the judge
            makes a final ruling. Every claim shows whether the jury agreed.
          </p>
        </section>
      </div>

      <p className="mt-14 text-sm text-muted">
        Every AI call is shown in the model trace on each result: model, tokens, time and cost.{" "}
        <Link to="/" className="font-medium text-ink underline decoration-accent underline-offset-4">
          Try a check →
        </Link>
      </p>
    </article>
  );
}
