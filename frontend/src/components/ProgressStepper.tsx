import { STEPS, type ClaimProgress, type ClaimStage } from "../lib/useCheck";

const STAGE_TEXT: Record<ClaimStage, string> = {
  planning: "Planning searches",
  searching: "Searching the web",
  assessing: "Reading sources",
  jury: "Jury deliberating",
  debating: "Jury disagreed: searching again",
  done: "Done",
};

function claimDetail(c: ClaimProgress): string | null {
  if (c.stage === "assessing" && c.sourceCount !== undefined)
    return `${c.sourceCount} source${c.sourceCount === 1 ? "" : "s"}`;
  if ((c.stage === "jury" || c.stage === "debating") && c.verified !== undefined)
    return `${c.verified} verified quote${c.verified === 1 ? "" : "s"}`;
  if (c.stage === "searching" && c.queries?.length) return `${c.queries.length} queries`;
  return null;
}

function Dot({ state }: { state: "done" | "current" | "todo" }) {
  if (state === "done")
    return (
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent text-white">
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden>
          <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  if (state === "current")
    return (
      <span className="relative grid h-5 w-5 shrink-0 place-items-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/30 motion-reduce:animate-none" />
        <span className="h-2.5 w-2.5 rounded-full bg-accent" />
      </span>
    );
  return <span className="h-5 w-5 shrink-0 rounded-full border-2 border-line" />;
}

export default function ProgressStepper({
  step,
  claims,
  queued,
}: {
  step: number;
  claims: ClaimProgress[];
  queued?: boolean;
}) {
  const status = queued
    ? "Waiting in line — other checks are running."
    : step >= STEPS.length - 1
      ? "Done."
      : `${STEPS[step]}…`;
  return (
    <section aria-label="Progress" className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <p className="sr-only" aria-live="polite">
        {status}
      </p>
      <ol className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-5 sm:gap-y-3">
        {STEPS.map((label, i) => {
          const state = queued ? "todo" : i < step || (i === step && i === STEPS.length - 1) ? "done" : i === step ? "current" : "todo";
          return (
            <li
              key={label}
              aria-current={state === "current" ? "step" : undefined}
              className={`flex items-center gap-2 text-sm ${state === "todo" ? "text-muted" : "text-ink"} ${state === "current" ? "font-semibold" : ""}`}
            >
              <Dot state={state} />
              {label}
            </li>
          );
        })}
      </ol>
      {queued && <p className="mt-4 text-sm text-muted">{status}</p>}
      {claims.length > 0 && (
        <ul className="mt-5 space-y-2 border-t border-line pt-4">
          {claims.map((c) => {
            const detail = claimDetail(c);
            return (
              <li key={c.id} className="flex items-start gap-3 text-sm">
                <span className="mt-0.5 font-mono text-xs text-muted">#{c.id}</span>
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 font-serif text-ink">{c.text || `Claim ${c.id}`}</span>
                  <span className={`text-xs ${c.stage === "done" ? "text-accent-ink" : "text-muted"}`}>
                    {STAGE_TEXT[c.stage]}
                    {detail ? ` · ${detail}` : ""}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
