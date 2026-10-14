import JuryStatus from "./JuryStatus";
import SourceList from "./SourceList";
import VerdictBadge from "./VerdictBadge";
import { VERDICT } from "../lib/verdict";
import type { ClaimProgress } from "../lib/useCheck";
import type { ClaimResult } from "../types";

const RUNNING_TEXT: Record<string, string> = {
  planning: "Planning searches…",
  searching: "Searching the web…",
  assessing: "Reading sources and checking quotes…",
  jury: "Two models are deciding independently…",
  debating: "The jury disagreed — searching for more evidence…",
  done: "Finishing…",
};

function ConfidenceBar({ value, label }: { value: number; label: keyof typeof VERDICT }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label="Confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
        className="h-1.5 w-full max-w-48 overflow-hidden rounded-full bg-line"
      >
        <div className={`h-full rounded-full bg-current ${VERDICT[label].text}`} style={{ width: `${v}%` }} />
      </div>
      <span className="shrink-0 text-xs text-muted">{v}% confidence</span>
    </div>
  );
}

export function ClaimSkeleton({ claim }: { claim: ClaimProgress }) {
  return (
    <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-busy="true">
      <p className="mb-1 font-mono text-xs text-muted">Claim {claim.id}</p>
      <p className="font-serif text-lg leading-snug sm:text-xl">{claim.text || "…"}</p>
      <div className="mt-4 flex items-center gap-2 text-sm text-muted">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
        {RUNNING_TEXT[claim.stage]}
      </div>
      <div className="mt-4 space-y-2" aria-hidden>
        <div className="h-3 w-3/4 animate-pulse rounded bg-line motion-reduce:animate-none" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-line motion-reduce:animate-none" />
      </div>
    </article>
  );
}

export default function ClaimCard({ claim }: { claim: ClaimResult }) {
  const v = claim.result.final;
  return (
    <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="font-mono text-xs text-muted">Claim {claim.id}</p>
        <VerdictBadge label={v.label} />
      </div>
      <p className="mt-2 font-serif text-lg leading-snug sm:text-xl">{claim.text}</p>
      <div className="mt-4">
        <ConfidenceBar value={v.confidence} label={v.label} />
      </div>
      <p className="mt-4 leading-relaxed">{v.explanation}</p>
      <div className="mt-5">
        <JuryStatus result={claim.result} />
      </div>
      <div className="mt-6 border-t border-line pt-5">
        <SourceList evidence={claim.evidence} cited={v.cited_source_ids} />
      </div>
    </article>
  );
}
