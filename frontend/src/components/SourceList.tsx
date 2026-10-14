import { useState } from "react";
import type { Evidence, Stance } from "../types";

const STANCE: Record<Exclude<Stance, "irrelevant">, { text: string; cls: string }> = {
  supports: { text: "Supports", cls: "text-v-true bg-v-true-bg" },
  refutes: { text: "Refutes", cls: "text-v-false bg-v-false-bg" },
  mixed: { text: "Mixed", cls: "text-v-misleading bg-v-misleading-bg" },
};

function Favicon({ src, domain }: { src: string | null; domain: string }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed)
    return (
      <img
        src={src}
        alt=""
        width={16}
        height={16}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="h-4 w-4 shrink-0 rounded-sm"
      />
    );
  return (
    <span
      aria-hidden
      className="grid h-4 w-4 shrink-0 place-items-center rounded-sm bg-line text-[10px] font-semibold uppercase text-muted"
    >
      {domain.charAt(0) || "?"}
    </span>
  );
}

export function visibleEvidence(evidence: Evidence[], cited: number[]): Evidence[] {
  const usable = evidence.filter((e) => e.quote_verified && e.stance !== "irrelevant");
  const rank = (e: Evidence) => (cited.includes(e.source.id) ? 0 : 1);
  return [...usable].sort((a, b) => rank(a) - rank(b) || a.source.id - b.source.id);
}

export function discardedCount(evidence: Evidence[]): number {
  return evidence.filter((e) => !e.quote_verified && e.quote.trim() !== "").length;
}

export default function SourceList({
  evidence,
  cited,
}: {
  evidence: Evidence[];
  cited: number[];
}) {
  const shown = visibleEvidence(evidence, cited);
  const discarded = discardedCount(evidence);
  return (
    <div>
      <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
        Sources with verified quotes
      </h4>
      {shown.length === 0 ? (
        <p className="text-sm text-muted">No verified quotes for this claim.</p>
      ) : (
        <ul className="space-y-4">
          {shown.map((e) => {
            const stance = STANCE[e.stance as Exclude<Stance, "irrelevant">];
            return (
              <li key={e.source.id} className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  <Favicon src={e.source.favicon} domain={e.source.domain} />
                  <span className="text-muted">{e.source.domain}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${stance.cls}`}
                  >
                    {stance.text}
                  </span>
                  {cited.includes(e.source.id) && (
                    <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
                      · cited
                    </span>
                  )}
                </div>
                <a
                  href={e.source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 block break-words font-medium underline decoration-line underline-offset-4 hover:decoration-ink"
                >
                  {e.source.title || e.source.url}
                </a>
                <blockquote className="mt-2 border-l-2 border-accent pl-3 font-serif text-[15px] leading-relaxed italic">
                  “{e.quote}”
                </blockquote>
                {e.note && <p className="mt-1 text-xs text-muted">{e.note}</p>}
              </li>
            );
          })}
        </ul>
      )}
      {discarded > 0 && (
        <p className="mt-4 text-xs text-muted">
          {discarded} unverified quote{discarded === 1 ? "" : "s"} discarded
        </p>
      )}
    </div>
  );
}
