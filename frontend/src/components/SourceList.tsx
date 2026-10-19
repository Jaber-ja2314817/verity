import { useId, useState } from "react";
import {
  formatPublished,
  organizeEvidence,
  reliabilityBadge,
  type UsableStance,
} from "../lib/evidence";
import type { Evidence } from "../types";

const STANCE: Record<UsableStance, { title: string; dot: string; text: string }> = {
  supports: { title: "Supports the claim", dot: "bg-v-true", text: "text-v-true" },
  refutes: { title: "Contradicts the claim", dot: "bg-v-false", text: "text-v-false" },
  mixed: { title: "Mixed or partial", dot: "bg-v-misleading", text: "text-v-misleading" },
};

const TONE = {
  good: "border-v-true/30 text-v-true",
  neutral: "border-line text-muted",
  warn: "border-v-misleading/40 text-v-misleading",
} as const;

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

function CheckIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      <path d="M3 8.5l3 3L13 4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SourceLink({ e, className = "" }: { e: Evidence; className?: string }) {
  return (
    <a
      href={e.source.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`break-words underline decoration-line underline-offset-4 hover:decoration-ink ${className}`}
    >
      {e.source.title || e.source.url}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

/** Domain, reliability tier, publication date and "cited" marker for one source. */
function SourceMeta({ e, cited }: { e: Evidence; cited: boolean }) {
  const tier = reliabilityBadge(e.source.reliability);
  const published = formatPublished(e.source.published_date);
  const chip = "rounded-full border px-2 py-px text-[11px] leading-4";
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <Favicon src={e.source.favicon} domain={e.source.domain} />
      <span className="text-muted">{e.source.domain}</span>
      {tier && (
        <span className={`${chip} ${TONE[tier.tone]}`} title={tier.title}>
          {tier.text}
        </span>
      )}
      {published && (
        <span className="text-xs text-muted">
          <span aria-hidden>· </span>
          <span className="sr-only">Published </span>
          <time dateTime={e.source.published_date ?? undefined}>{published}</time>
        </span>
      )}
      {cited && (
        <span className={`${chip} border-accent/50 bg-accent/10 font-medium text-accent-ink`}>
          Cited in verdict
        </span>
      )}
    </div>
  );
}

function SetAside({ unverified, irrelevant }: { unverified: Evidence[]; irrelevant: Evidence[] }) {
  const n = unverified.length + irrelevant.length;
  if (n === 0) return null;
  return (
    <details className="group mt-5 rounded-xl border border-line px-4 py-3">
      <summary className="cursor-pointer list-none text-xs text-muted [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="mr-1.5 inline-block transition-transform group-open:rotate-90">›</span>
        {n} source{n === 1 ? "" : "s"} set aside
        {unverified.length > 0 && ` · ${unverified.length} unverified quote${unverified.length === 1 ? "" : "s"} discarded`}
      </summary>
      <div className="mt-3 space-y-4 text-sm">
        {unverified.length > 0 && (
          <div>
            <p className="text-xs text-muted">
              Quote not found on the page. The model's quote didn't match the source text, so it was
              thrown out and never reached the jury.
            </p>
            <ul className="mt-2 space-y-1.5">
              {unverified.map((e) => (
                <li key={e.source.id} className="flex min-w-0 items-start gap-2">
                  <Favicon src={e.source.favicon} domain={e.source.domain} />
                  <span className="min-w-0">
                    <span className="text-muted">{e.source.domain} · </span>
                    <SourceLink e={e} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {irrelevant.length > 0 && (
          <div>
            <p className="text-xs text-muted">Didn't address the claim.</p>
            <ul className="mt-2 space-y-1.5">
              {irrelevant.map((e) => (
                <li key={e.source.id} className="flex min-w-0 items-start gap-2">
                  <Favicon src={e.source.favicon} domain={e.source.domain} />
                  <span className="min-w-0">
                    <span className="text-muted">{e.source.domain} · </span>
                    <SourceLink e={e} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

export default function SourceList({ evidence, cited }: { evidence: Evidence[]; cited: number[] }) {
  const view = organizeEvidence(evidence, cited);
  const citedSet = new Set(cited);
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h4 id={headingId} className="text-xs font-medium uppercase tracking-wide text-muted">
          Evidence
        </h4>
        {view.verified > 0 && (
          <p className="text-xs text-muted">
            {view.verified} verified quote{view.verified === 1 ? "" : "s"}
            {view.cited > 0 && ` · ${view.cited} cited in the verdict`}
          </p>
        )}
      </div>

      {view.verified === 0 ? (
        <p className="mt-3 text-sm text-muted">
          {evidence.length === 0
            ? "No sources were found for this claim."
            : "No source had a verifiable quote that addresses this claim."}
        </p>
      ) : (
        <>
          <p className="mt-2 flex items-start gap-1.5 text-xs text-accent-ink">
            <CheckIcon className="mt-px h-3.5 w-3.5 shrink-0" />
            Every quote below was found word for word on its source page, checked by code.
          </p>
          <div className="mt-5 space-y-6">
            {view.groups.map((g) => {
              const s = STANCE[g.stance];
              return (
                <div key={g.stance}>
                  <h5 className={`flex items-center gap-2 text-[13px] font-semibold ${s.text}`}>
                    <span aria-hidden className={`h-2 w-2 rounded-full ${s.dot}`} />
                    {s.title}
                    <span className="font-normal text-muted">({g.items.length})</span>
                  </h5>
                  <ul className="mt-3 space-y-5">
                    {g.items.map((e) => (
                      <li key={e.source.id} className="min-w-0">
                        <SourceMeta e={e} cited={citedSet.has(e.source.id)} />
                        <SourceLink e={e} className="mt-1 block font-medium" />
                        <blockquote className="mt-2 border-l-2 border-accent pl-3 font-serif text-[15px] leading-relaxed italic">
                          “{e.quote}”
                          <span className="sr-only"> (verified on the page)</span>
                        </blockquote>
                        {e.note && <p className="mt-1 text-xs text-muted">{e.note}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </>
      )}

      <SetAside unverified={view.unverified} irrelevant={view.irrelevant} />
    </section>
  );
}
