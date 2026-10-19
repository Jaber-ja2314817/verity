import { juryOutcome, skipInfo } from "./claims";
import { VERDICT } from "./verdict";
import type { CheckRecord } from "../types";

const DASH = "—";

export function formatCost(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  if (v === 0) return "$0";
  if (v < 0.0001) return "<$0.0001";
  if (v < 0.01) return `$${v.toFixed(4)}`;
  if (v < 1) return `$${v.toFixed(3)}`;
  return `$${v.toFixed(2)}`;
}

export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return DASH;
  return Math.round(n).toLocaleString("en-US");
}

export function formatSeconds(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return DASH;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s - m * 60);
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function relativeTime(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}

/** "nvidia/Nemotron-3-Ultra-550b-a55b" -> "Nemotron-3-Ultra-550b-a55b" */
export function shortModel(model: string): string {
  return model.replace(/^nvidia\//i, "");
}

/** "Please wait 412 seconds" -> "Please wait about 7 minutes" (rate-limit messages). */
export function humanizeWait(message: string): string {
  return message.replace(/\b(\d+) seconds?\b/, (m, n: string) => {
    const s = Number(n);
    if (s < 90) return m;
    const mins = Math.ceil(s / 60);
    return `about ${mins} minute${mins === 1 ? "" : "s"}`;
  });
}

const OUTCOME_TEXT = {
  settled: "Decided without a jury vote (not enough usable evidence).",
  agreed: "Both models agreed independently.",
  rechecked: "Both models found too little evidence, so Verity searched again before the final verdict.",
  debated: "The models disagreed; after an extra search the judge model made the final ruling.",
  disagreed: "The models disagreed; the judge model made the final ruling.",
} as const;

/** Plain-text summary for "Copy as text" (chat-friendly). */
export function checkToText(record: CheckRecord, url: string): string {
  const lines: string[] = ["Verity fact-check", ""];
  if (record.claims.length === 0) lines.push("No checkable factual claims found.", "");
  for (const c of [...record.claims].sort((a, b) => a.id - b.id)) {
    const v = c.result.final;
    lines.push(`${c.id}. "${c.text}"`);
    lines.push(`   ${VERDICT[v.label].title.toUpperCase()} (confidence ${v.confidence}%)`);
    if (v.explanation) lines.push(`   ${v.explanation}`);
    lines.push(`   ${OUTCOME_TEXT[juryOutcome(c.result)]}`);
    const cited = c.evidence.filter(
      (e) => e.quote_verified && v.cited_source_ids.includes(e.source.id),
    );
    for (const e of cited) lines.push(`   - ${e.source.domain}: ${e.source.url}`);
    lines.push("");
  }
  if (record.skipped_claims.length) {
    lines.push("Not checked:");
    for (const c of record.skipped_claims) lines.push(`- "${c.text}" (${skipInfo(c).reason})`);
    lines.push("");
  }
  lines.push(`Full result: ${url}`);
  return lines.join("\n");
}
