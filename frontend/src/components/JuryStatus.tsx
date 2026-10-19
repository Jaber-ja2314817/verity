import { useId, useState } from "react";
import VerdictBadge from "./VerdictBadge";
import { juryOutcome, type JuryModels } from "../lib/claims";
import { shortModel } from "../lib/format";
import { VERDICT } from "../lib/verdict";
import type { JuryResult, Verdict } from "../types";

const SUMMARY = {
  settled: "No jury vote: not enough verified evidence to judge",
  agreed: "Both models agreed independently",
  rechecked: "Both found too little evidence → extra search → final ruling",
  debated: "Models disagreed → searched for more evidence → final ruling",
  disagreed: "Models disagreed → final ruling by the judge model",
} as const;

function name(model: string | undefined, fallback: string): string {
  return model ? shortModel(model) : fallback;
}

/** "True 82%" in the verdict's color; compact enough for one line. */
function Mini({ role, v }: { role: string; v: Verdict }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-muted">{role} </span>
      <span className={`font-semibold ${VERDICT[v.label].text}`}>{VERDICT[v.label].title}</span>
      <span className="text-muted"> {v.confidence}%</span>
    </span>
  );
}

export default function JuryStatus({ result, models = {} }: { result: JuryResult; models?: JuryModels }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const outcome = juryOutcome(result);
  // A recheck only ends in a judge ruling when the extra search found usable evidence.
  const recheckRuled =
    outcome === "rechecked" && (!!models.final || result.final.label !== "UNVERIFIED");
  const split = outcome === "debated" || outcome === "disagreed";
  const showFinal = split || recheckRuled;
  const summary =
    outcome === "rechecked" && !recheckRuled
      ? "Both found too little evidence → extra search → still not enough"
      : SUMMARY[outcome];
  const tone =
    outcome === "settled" || outcome === "rechecked" ? "text-muted" : split ? "text-v-misleading" : "text-accent-ink";
  return (
    <div className="rounded-xl border border-line">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left text-sm"
      >
        <span className="min-w-0">
          <span className={`block font-medium ${tone}`}>{summary}</span>
          {outcome !== "settled" && (
            <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
              <Mini role="Draft" v={result.draft} />
              <span aria-hidden className="text-muted">·</span>
              <Mini role="Jury" v={result.jury} />
              {showFinal && (
                <>
                  <span aria-hidden className="text-muted">→</span>
                  <Mini role="Final" v={result.final} />
                </>
              )}
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-xs text-muted">
          {open ? "Hide" : "Details"}
          <svg
            viewBox="0 0 16 16"
            className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden
          >
            <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div id={panelId} className="border-t border-line px-4 py-4">
          {outcome === "settled" ? (
            <p className="text-sm text-muted">
              There was no verified evidence for the models to judge, so Verity set this verdict in
              code instead of asking them to guess.
            </p>
          ) : (
            <>
              <p className="mb-4 text-xs text-muted">
                Two different NVIDIA Nemotron models read the same verified quotes in parallel,
                without seeing each other's answer.
                {outcome === "agreed" && " The final confidence is the average of both."}
                {outcome === "rechecked" &&
                  (recheckRuled
                    ? " Both said the evidence was too thin, so Verity searched for what they said was missing, then the judge model ruled on all the evidence."
                    : " Both said the evidence was too thin, so Verity searched for what they said was missing. The extra search found nothing usable, so the verdict stays Unverified.")}
                {outcome === "debated" &&
                  " Because they disagreed, Verity searched for the evidence they said was missing, then the judge model weighed both opinions and all the evidence."}
                {outcome === "disagreed" &&
                  " Because they disagreed, the judge model weighed both opinions and all the evidence."}
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Opinion title={`Draft · ${name(models.draft, "fast model")}`} verdict={result.draft} />
                <Opinion title={`Jury · ${name(models.jury, "judge model")} (independent)`} verdict={result.jury} />
              </div>
              {showFinal && (
                <div className="mt-4 border-t border-line pt-4">
                  <Opinion
                    title={`Final ruling · ${name(models.final ?? models.jury, "judge model")}`}
                    verdict={result.final}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Opinion({ title, verdict }: { title: string; verdict: Verdict }) {
  return (
    <div className="min-w-0">
      <p className="mb-2 break-words text-xs font-medium uppercase tracking-wide text-muted">{title}</p>
      <div className="mb-2 flex items-center gap-2">
        <VerdictBadge label={verdict.label} size="sm" />
        <span className="text-xs text-muted">{verdict.confidence}% confident</span>
      </div>
      <p className="text-sm leading-relaxed">{verdict.explanation}</p>
    </div>
  );
}
