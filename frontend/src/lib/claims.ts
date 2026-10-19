import type { ExtractedClaim, JuryResult, TraceEntry } from "../types";

/** Matches backend Settings.max_claims (default). Used only for copy. */
export const MAX_CLAIMS = 3;

/**
 * How the final verdict was reached:
 * - settled: decided in code without a vote (no sources / no usable evidence / claim failed)
 * - agreed: draft and jury reached the same label independently
 * - debated: they disagreed, extra evidence was searched, the judge made a final ruling
 * - disagreed: they disagreed and the judge ruled without extra search
 * - rechecked: both said UNVERIFIED, so Verity searched again (and the judge ruled if the new
 *   search found usable evidence)
 */
export type JuryOutcome = "settled" | "agreed" | "rechecked" | "debated" | "disagreed";

export function juryOutcome(r: JuryResult): JuryOutcome {
  if (r.agreed && JSON.stringify(r.draft) === JSON.stringify(r.jury)) return "settled";
  if (r.rechecked) return "rechecked";
  if (r.agreed) return "agreed";
  return r.debated ? "debated" : "disagreed";
}

export type ConfidenceLevel = "high" | "moderate" | "low";

export function confidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 80) return "high";
  if (confidence >= 50) return "moderate";
  return "low";
}

export interface SkipInfo {
  reason: string;
  hint: string | null; // what the user can do about it
}

/** Why a statement wasn't checked, and how to get it checked. */
export function skipInfo(c: ExtractedClaim): SkipInfo {
  // select_claims also skips checkworthy claims beyond the per-check limit; their model
  // reason ("specific historical fact") would read as if they were uncheckable.
  if (c.checkworthy)
    return {
      reason: `Each check covers up to ${MAX_CLAIMS} claims; this one was over the limit.`,
      hint: "Check it on its own.",
    };
  const reason = c.reason.trim() || "Not a checkable factual statement.";
  const r = reason.toLowerCase();
  let hint: string | null = null;
  if (r.includes("question"))
    hint = r.includes("rephrase")
      ? "For example, instead of “When was the Eiffel Tower built?” write “The Eiffel Tower was finished in 1889.”"
      : "Rephrase it as a statement, e.g. “The Eiffel Tower was finished in 1889.”";
  else if (r.includes("opinion") || r.includes("subjective"))
    hint = "Opinions can't be fact-checked. State the fact behind it, if there is one.";
  else if (r.includes("predict") || r.includes("future"))
    hint = "Predictions can't be checked yet. Check the facts they rely on instead.";
  else if (r.includes("vague") || r.includes("specific"))
    hint = "Add specifics: who, what, when, where, or a number.";
  return { reason, hint };
}

const OPEN_QUESTION = /^(who|what|when|where|why|how|which|whose|whom)\b/i;
const YES_NO_QUESTION = /^(is|are|was|were|do|does|did|can|could|has|have|had|will|should)\b/i;

/** Gentle advice while typing; null when the input looks fine. URLs are never flagged. */
export function phrasingHint(value: string): string | null {
  const v = value.trim();
  if (!v || /^https?:\/\//i.test(v)) return null;
  const sentences = v.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (sentences.length !== 1 || !v.endsWith("?")) return null;
  if (OPEN_QUESTION.test(v))
    return "Open questions can't be checked. State the answer you heard instead, e.g. “The Eiffel Tower was finished in 1889.”";
  if (YES_NO_QUESTION.test(v)) return "Yes/no questions are checked as the statement they ask about.";
  return null;
}

export interface JuryModels {
  draft?: string;
  jury?: string;
  final?: string;
}

/** Which model played which role for a claim, read from the trace (model ids come from env). */
export function juryModels(trace: TraceEntry[], claimId: number): JuryModels {
  const find = (step: string) => {
    const e = trace.find((t) => t.step === `${step}[claim ${claimId}]`);
    return e?.model;
  };
  return { draft: find("verdict_draft"), jury: find("verdict_jury"), final: find("final_ruling") };
}
