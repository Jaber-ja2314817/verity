import { useId, useState } from "react";
import VerdictBadge from "./VerdictBadge";
import type { JuryResult } from "../types";

export default function JuryStatus({ result }: { result: JuryResult }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const summary = result.agreed
    ? "Jury agreed ✓"
    : result.debated
      ? "Jury disagreed → extra search → final ruling by Nemotron Ultra"
      : "Jury disagreed → final ruling by Nemotron Ultra";
  // Decided in code without a jury vote: draft, jury and final are the same verdict.
  const same = JSON.stringify(result.draft) === JSON.stringify(result.jury);
  return (
    <div className="rounded-xl border border-line">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm"
      >
        <span className={result.agreed ? "font-medium text-accent-ink" : "font-medium text-v-misleading"}>
          {summary}
        </span>
        <svg
          viewBox="0 0 16 16"
          className={`h-4 w-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div id={panelId} className="grid gap-4 border-t border-line px-4 py-4 sm:grid-cols-2">
          {same ? (
            <p className="text-sm text-muted sm:col-span-2">
              This verdict was decided without a jury vote (not enough usable evidence).
            </p>
          ) : (
            <>
              <Opinion title="Draft · fast model" verdict={result.draft} />
              <Opinion title="Jury · Nemotron Ultra (independent)" verdict={result.jury} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Opinion({ title, verdict }: { title: string; verdict: JuryResult["draft"] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{title}</p>
      <div className="mb-2 flex items-center gap-2">
        <VerdictBadge label={verdict.label} size="sm" />
        <span className="text-xs text-muted">{verdict.confidence}% confident</span>
      </div>
      <p className="text-sm leading-relaxed">{verdict.explanation}</p>
    </div>
  );
}
