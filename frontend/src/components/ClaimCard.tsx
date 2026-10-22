import JuryStatus from "./JuryStatus";
import SourceList from "./SourceList";
import VerdictBadge from "./VerdictBadge";
import { confidenceLevel, type JuryModels } from "../lib/claims";
import { VERDICT } from "../lib/verdict";
import type { ClaimProgress } from "../lib/useCheck";
import type { ClaimResult, Label, Verdict } from "../types";

const RUNNING_TEXT: Record<string, string> = {
  planning: "Planning searches…",
  searching: "Searching the web…",
  assessing: "Reading sources and checking quotes…",
  jury: "Two models are deciding independently…",
  debating: "The models disagreed — searching for more evidence…",
  done: "Finishing…",
};

function ConfidenceBar({ value, label }: { value: number; label: Label }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const level = confidenceLevel(v);
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label="Confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
        aria-valuetext={`${v}% (${level})`}
        className="h-1.5 w-full max-w-48 overflow-hidden rounded-full bg-line"
      >
        <div className={`h-full rounded-full bg-current ${VERDICT[label].text}`} style={{ width: `${v}%` }} />
      </div>
      <span className="shrink-0 text-xs text-muted">
        {v}% confidence · {level}
      </span>
    </div>
  );
}

/** UNVERIFIED is "we couldn't tell", not "false". Say so, and show what would settle it. */
function UnverifiedNote({ verdict }: { verdict: Verdict }) {
  const queries = verdict.missing_evidence_queries.filter((q) => q.trim());
  return (
    <div className="rounded-xl border border-v-unverified/30 bg-v-unverified-bg px-4 py-3 text-sm">
      <p>
        <span className="font-medium">Unverified is not the same as false.</span>{" "}
        <span className="text-muted">
          Verity couldn't find enough reliable, verified evidence to call this either way.
        </span>
      </p>
      {queries.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-muted">Searches that could settle it:</p>
          <ul className="mt-1 space-y-0.5">
            {queries.map((q) => (
              <li key={q} className="font-mono text-xs break-words">
                “{q}”
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ClaimSkeleton({ claim }: { claim: ClaimProgress }) {
  return (
    <article className="rounded-2xl border border-line bg-surface p-5 sm:p-6" aria-busy="true">
      <p className="mb-1 font-mono text-xs text-muted">Claim {claim.id}</p>
      <h2 className="font-serif text-lg leading-snug sm:text-xl">{claim.text || "…"}</h2>
      <div className="mt-4 flex items-center gap-2 text-sm text-muted">
        <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
        {claim.stage === "debating" && claim.rechecked
          ? "Both models found too little evidence — searching again…"
          : RUNNING_TEXT[claim.stage]}
      </div>
      <div className="mt-4 space-y-2" aria-hidden>
        <div className="h-3 w-3/4 animate-pulse rounded bg-line motion-reduce:animate-none" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-line motion-reduce:animate-none" />
      </div>
    </article>
  );
}

export default function ClaimCard({ claim, models }: { claim: ClaimResult; models?: JuryModels }) {
  const v = claim.result.final;
  return (
    <article
      id={`claim-${claim.id}`}
      aria-labelledby={`claim-${claim.id}-text`}
      className="scroll-mt-6 rounded-2xl border border-line bg-surface p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="font-mono text-xs text-muted">Claim {claim.id}</p>
        <VerdictBadge label={v.label} />
      </div>
      <h2 id={`claim-${claim.id}-text`} className="mt-2 font-serif text-lg leading-snug sm:text-xl">
        {claim.text}
      </h2>
      <div className="mt-4">
        {v.label === "UNVERIFIED" ? <UnverifiedNote verdict={v} /> : <ConfidenceBar value={v.confidence} label={v.label} />}
      </div>
      <p className="mt-4 leading-relaxed">{v.explanation}</p>
      <div className="mt-5">
        <JuryStatus result={claim.result} models={models} />
      </div>
      <div className="mt-6 border-t border-line pt-5">
        <SourceList evidence={claim.evidence} cited={v.cited_source_ids} />
      </div>
    </article>
  );
}
