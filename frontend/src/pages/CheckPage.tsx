import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import ClaimCard, { ClaimSkeleton } from "../components/ClaimCard";
import ProgressStepper from "../components/ProgressStepper";
import ShareButton from "../components/ShareButton";
import TracePanel from "../components/TracePanel";
import { formatDate, formatSeconds } from "../lib/format";
import { currentStep, useCheck } from "../lib/useCheck";
import type { CheckRecord } from "../types";

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
      <Link
        to="/"
        className="mt-6 inline-flex items-center rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-paper hover:opacity-90"
      >
        {tone === "error" ? "Try again" : "Check something"}
      </Link>
    </div>
  );
}

function Header({ record }: { record: CheckRecord }) {
  return (
    <header className="mb-6">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">
        Fact-check · {formatDate(record.created_at)}
        {record.input_type === "url" ? " · from a web page" : ""}
      </p>
      <p className="mt-3 line-clamp-4 break-words border-l-2 border-line pl-4 font-serif text-lg leading-relaxed text-muted sm:text-xl">
        {record.input_preview}
      </p>
    </header>
  );
}

function CheckView({ id }: { id: string }) {
  const { state, loading, notFound, loadError } = useCheck(id);
  const { record, progress } = state;

  if (loading)
    return (
      <div className="mt-10 space-y-4" aria-busy="true" aria-label="Loading check">
        <div className="h-4 w-48 animate-pulse rounded bg-line" />
        <div className="h-20 animate-pulse rounded-2xl bg-line/60" />
        <div className="h-40 animate-pulse rounded-2xl bg-line/60" />
      </div>
    );
  if (notFound)
    return (
      <Notice title="Check not found">
        This link doesn't match any fact-check. Results are kept for a limited time, so it may have
        expired.
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

  return (
    <div>
      <Header record={record} />

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
          <Link
            to="/"
            className="mt-4 inline-flex rounded-full bg-ink px-4 py-2 text-sm font-semibold text-paper hover:opacity-90"
          >
            Try again
          </Link>
        </div>
      )}

      {done && (
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted">
            {claims.length} claim{claims.length === 1 ? "" : "s"} checked
            {totals?.duration_s !== undefined && ` in ${formatSeconds(totals.duration_s)}`}
          </p>
          <ShareButton record={record} />
        </div>
      )}

      {done && claims.length === 0 && (
        <div className="rounded-2xl border border-line bg-surface p-6 text-center sm:p-8">
          <p className="font-semibold">No checkable factual claims found.</p>
          <p className="mt-2 text-sm text-muted">
            Verity checks statements of fact — numbers, dates, events, scientific facts. Opinions
            and predictions can't be fact-checked.
          </p>
          {record.skipped_claims[0] && (
            <p className="mt-3 text-sm">
              Why: <span className="text-muted">{record.skipped_claims[0].reason}</span>
            </p>
          )}
          <p className="mt-3 text-sm text-muted">
            Try writing it as a statement, e.g. “Coffee stunts your growth.”
          </p>
        </div>
      )}

      <div className="space-y-6">
        {claims.map((c) => (
          <ClaimCard key={c.id} claim={c} />
        ))}
        {running && pending.map((c) => <ClaimSkeleton key={c.id} claim={c} />)}
      </div>

      {record.skipped_claims.length > 0 && (
        <details className="mt-8 rounded-2xl border border-line bg-surface px-5 py-4 sm:px-6">
          <summary className="cursor-pointer text-sm font-medium">
            {record.skipped_claims.length} statement{record.skipped_claims.length === 1 ? "" : "s"}{" "}
            not checked
          </summary>
          <ul className="mt-4 space-y-3">
            {record.skipped_claims.map((c) => (
              <li key={c.id} className="text-sm">
                <p className="font-serif">{c.text}</p>
                <p className="text-xs text-muted">{c.reason}</p>
              </li>
            ))}
          </ul>
        </details>
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
