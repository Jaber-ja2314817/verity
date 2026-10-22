import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import ClaimCard, { ClaimSkeleton } from "../components/ClaimCard";
import ProgressStepper from "../components/ProgressStepper";
import ShareButton from "../components/ShareButton";
import TracePanel from "../components/TracePanel";
import VerdictBadge from "../components/VerdictBadge";
import { juryModels, skipInfo } from "../lib/claims";
import { formatDate, formatSeconds, fullInput } from "../lib/format";
import { currentStep, useCheck } from "../lib/useCheck";
import { useTitle } from "../lib/useTitle";
import type { CheckRecord, ClaimResult, ExtractedClaim } from "../types";

const button =
  "inline-flex items-center rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper hover:opacity-90";

function Notice({
  title,
  children,
  tone = "neutral",
}: {
  title: string;
  children?: ReactNode;
  tone?: "neutral" | "error";
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className="mx-auto mt-10 max-w-xl rounded-2xl border border-line bg-surface p-6 text-center sm:p-8"
    >
      <h1 className={`text-xl font-semibold ${tone === "error" ? "text-v-false" : ""}`}>{title}</h1>
      {children && <div className="mt-3 text-muted">{children}</div>}
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        {tone === "error" && (
          <button type="button" onClick={() => window.location.reload()} className={button}>
            Retry
          </button>
        )}
        <Link
          to="/"
          className={
            tone === "error"
              ? "inline-flex items-center rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-ink"
              : button
          }
        >
          Check something else
        </Link>
      </div>
    </div>
  );
}

function Header({ record }: { record: CheckRecord }) {
  const isUrl = record.input_type === "url";
  const url = isUrl ? (fullInput(record) ?? record.input_preview) : "";
  return (
    <header className="mb-6">
      <h1 className="text-xs font-medium uppercase tracking-wide text-muted">
        Fact-check · {formatDate(record.created_at)}
        {isUrl ? " · from a web page" : ""}
      </h1>
      {isUrl && /^https?:\/\//i.test(url) ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 line-clamp-3 break-all border-l-2 border-line pl-4 font-serif text-lg leading-relaxed text-muted underline decoration-line underline-offset-4 hover:text-ink sm:text-xl"
        >
          {url}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : (
        <p className="mt-3 line-clamp-4 break-words border-l-2 border-line pl-4 font-serif text-lg leading-relaxed text-muted sm:text-xl">
          {record.input_preview}
        </p>
      )}
    </header>
  );
}

/** One line per claim with its verdict, linking to the full card. */
function Summary({ claims }: { claims: ClaimResult[] }) {
  return (
    <nav aria-label="Verdicts" className="mb-8 rounded-2xl border border-line bg-surface px-5 py-4 sm:px-6">
      <ol className="space-y-2.5">
        {claims.map((c) => (
          <li key={c.id}>
            <a href={`#claim-${c.id}`} className="group flex items-start gap-3 text-sm">
              <span className="w-[7.5rem] shrink-0">
                <VerdictBadge label={c.result.final.label} size="sm" />
              </span>
              <span className="min-w-0 line-clamp-2 font-serif text-[15px] leading-snug group-hover:underline group-hover:decoration-line group-hover:underline-offset-4">
                {c.text}
              </span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Skipped({ claims }: { claims: ExtractedClaim[] }) {
  return (
    <section aria-labelledby="skipped-heading" className="rounded-2xl border border-line bg-surface px-5 py-4 sm:px-6">
      <h2 id="skipped-heading" className="text-sm font-medium">
        {claims.length} statement{claims.length === 1 ? "" : "s"} not checked
      </h2>
      <ul className="mt-3 space-y-4">
        {claims.map((c) => {
          const info = skipInfo(c);
          return (
            <li key={c.id} className="text-sm">
              <p className="font-serif">“{c.text}”</p>
              <p className="mt-0.5 text-xs text-muted">{info.reason}</p>
              {info.hint && <p className="mt-0.5 text-xs text-note">{info.hint}</p>}
              <Link
                to="/"
                state={{ prefill: c.text }}
                className="mt-1.5 inline-block text-xs font-medium text-accent-ink underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
              >
                {c.checkworthy ? "Check this on its own" : "Rephrase and check"} →
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CheckView({ id }: { id: string }) {
  const { state, loading, notFound, loadError, reconnecting } = useCheck(id);
  const { record, progress } = state;
  const status = record?.status;
  useTitle(
    notFound
      ? "Check not found"
      : loadError
        ? "Couldn't load this check"
        : status === "done"
          ? "Fact-check results"
          : status === "error"
            ? "Check failed"
            : "Checking…",
  );

  if (loading)
    return (
      <div role="status" className="mt-10 space-y-4" aria-busy="true" aria-label="Loading check">
        <div className="h-4 w-48 animate-pulse rounded bg-line motion-reduce:animate-none" />
        <div className="h-20 animate-pulse rounded-2xl bg-line/60 motion-reduce:animate-none" />
        <div className="h-40 animate-pulse rounded-2xl bg-line/60 motion-reduce:animate-none" />
      </div>
    );
  if (notFound)
    return (
      <Notice title="Check not found">
        This link doesn't match any fact-check. Check that the address is complete, or the result
        may no longer be stored.
      </Notice>
    );
  if (loadError || !record)
    return (
      <Notice title="Couldn't load this check" tone="error">
        {loadError ?? "Something went wrong."}
      </Notice>
    );

  const done = record.status === "done";
  const failed = record.status === "error" || (progress.finished && !!progress.message && !done);
  const running = !done && !failed;
  const claims = [...record.claims].sort((a, b) => a.id - b.id);
  const finishedIds = new Set(claims.map((c) => c.id));
  const pending = progress.claims.filter((c) => !finishedIds.has(c.id));
  const trace = record.trace.length ? record.trace : progress.trace;
  const totals = Object.keys(record.totals).length ? record.totals : progress.totals;
  const retry = fullInput(record); // put back in the input box for "try again" only when we have all of it

  return (
    <div>
      <Header record={record} />

      {running && reconnecting && (
        <p role="status" className="mb-4 rounded-xl border border-v-misleading/30 bg-v-misleading-bg px-4 py-2.5 text-sm text-v-misleading">
          Connection lost. Reconnecting… The check keeps running on the server.
        </p>
      )}

      {running && (
        <div className="mb-8">
          <ProgressStepper
            step={currentStep(state)}
            claims={progress.claims}
            queued={record.status === "queued"}
          />
        </div>
      )}

      {failed && (
        <div role="alert" className="mb-8 rounded-2xl border border-v-false/30 bg-v-false-bg p-5 sm:p-6">
          <p className="font-semibold text-v-false">This check didn't finish.</p>
          <p className="mt-1 text-sm">{record.error ?? progress.message ?? "Something went wrong."}</p>
          <Link to="/" state={retry ? { prefill: retry } : undefined} className={`mt-4 ${button}`}>
            Try again
          </Link>
        </div>
      )}

      {done && (
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted">
            {claims.length === 0 ? "No claims" : `${claims.length} claim${claims.length === 1 ? "" : "s"}`} checked
            {totals?.duration_s !== undefined && ` in ${formatSeconds(totals.duration_s)}`}
          </p>
          <ShareButton record={record} />
        </div>
      )}

      {done && claims.length > 1 && <Summary claims={claims} />}

      {done && claims.length === 0 && (
        <div className="rounded-2xl border border-line bg-surface p-6 text-center sm:p-8">
          <p className="font-semibold">No checkable factual claims found.</p>
          <p className="mt-2 text-sm text-muted">
            Verity checks statements of fact — numbers, dates, events, scientific facts. Opinions,
            predictions and open questions can't be fact-checked.
          </p>
          {record.skipped_claims.length === 0 && (
            <p className="mt-3 text-sm text-muted">
              Try writing it as a statement, e.g. “Coffee stunts your growth.”
            </p>
          )}
          <Link to="/" state={retry ? { prefill: retry } : undefined} className={`mt-5 ${button}`}>
            Rephrase and try again
          </Link>
        </div>
      )}

      <div className="space-y-6">
        {claims.map((c) => (
          <ClaimCard key={c.id} claim={c} models={juryModels(trace, c.id)} />
        ))}
        {running && pending.map((c) => <ClaimSkeleton key={c.id} claim={c} />)}
      </div>

      {record.skipped_claims.length > 0 && (
        <div className="mt-8">
          <Skipped claims={record.skipped_claims} />
        </div>
      )}

      {(trace.length > 0 || done) && (
        <div className="mt-8">
          <TracePanel trace={trace} totals={totals} />
        </div>
      )}
    </div>
  );
}

export default function CheckPage() {
  const { id = "" } = useParams();
  // key resets all state when navigating between two checks.
  return <CheckView key={id} id={id} />;
}
