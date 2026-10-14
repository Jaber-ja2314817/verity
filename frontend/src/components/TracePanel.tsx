import { formatCost, formatSeconds, formatTokens, shortModel } from "../lib/format";
import type { Totals, TraceEntry } from "../types";

export default function TracePanel({ trace, totals }: { trace: TraceEntry[]; totals?: Totals }) {
  const sum = (f: (e: TraceEntry) => number | null) => trace.reduce((a, e) => a + (f(e) ?? 0), 0);
  const tin = totals?.input_tokens ?? sum((e) => e.input_tokens);
  const tout = totals?.output_tokens ?? sum((e) => e.output_tokens);
  const cost = totals?.cost_usd ?? sum((e) => e.cost_usd);
  return (
    <details className="group rounded-2xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 sm:px-6 [&::-webkit-details-marker]:hidden">
        <span>
          <span className="font-semibold">Model trace</span>
          <span className="ml-2 text-sm text-muted">
            {trace.length} call{trace.length === 1 ? "" : "s"} · {formatCost(cost)}
          </span>
        </span>
        <svg
          viewBox="0 0 16 16"
          className="h-4 w-4 shrink-0 text-muted transition-transform group-open:rotate-180"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <div className="border-t border-line px-5 pb-5 pt-4 sm:px-6">
        <p className="mb-4 text-sm text-accent-ink">
          100% of AI calls served by NVIDIA Nemotron on Nebius Token Factory.
        </p>
        {trace.length === 0 ? (
          <p className="text-sm text-muted">No model calls recorded yet.</p>
        ) : (
          <div className="-mx-5 overflow-x-auto px-5 sm:-mx-6 sm:px-6">
            <table className="w-full min-w-[560px] text-left text-sm tabular-nums">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="py-2 pr-3 font-medium">Step</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Model</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Tokens in</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Tokens out</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Time</th>
                  <th scope="col" className="py-2 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {trace.map((e, i) => (
                  <tr key={i} className="border-b border-line/60">
                    <td className="py-2 pr-3 font-mono text-xs">{e.step}</td>
                    <td className="py-2 pr-3 text-xs">{shortModel(e.model)}</td>
                    <td className="py-2 pr-3 text-right">{formatTokens(e.input_tokens)}</td>
                    <td className="py-2 pr-3 text-right">{formatTokens(e.output_tokens)}</td>
                    <td className="py-2 pr-3 text-right">{formatSeconds(e.latency_s)}</td>
                    <td className="py-2 text-right">{formatCost(e.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold">
                  <td className="pt-3 pr-3" colSpan={2}>
                    Total
                    {totals?.duration_s !== undefined && (
                      <span className="ml-2 font-normal text-muted">
                        · check took {formatSeconds(totals.duration_s)}
                      </span>
                    )}
                  </td>
                  <td className="pt-3 pr-3 text-right">{formatTokens(tin)}</td>
                  <td className="pt-3 pr-3 text-right">{formatTokens(tout)}</td>
                  <td className="pt-3 pr-3 text-right">{formatSeconds(sum((e) => e.latency_s))}</td>
                  <td className="pt-3 text-right">{formatCost(cost)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </details>
  );
}
