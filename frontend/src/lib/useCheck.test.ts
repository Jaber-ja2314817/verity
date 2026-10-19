import { describe, expect, it } from "vitest";
import { checkReducer, currentStep, initialState, type CheckAction, type CheckState } from "./useCheck";
import type { CheckRecord, Verdict } from "../types";

const record = (over: Partial<CheckRecord> = {}): CheckRecord => ({
  id: "abc", created_at: "2026-10-14T12:00:00Z", status: "running", input_type: "text",
  input_preview: "text", language: null, claims: [], skipped_claims: [], trace: [], totals: {},
  error: null, ...over,
});
const verdict: Verdict = { label: "TRUE", confidence: 90, explanation: "e", cited_source_ids: [1], missing_evidence_queries: [] };

function run(events: CheckAction[], start: CheckState = initialState): CheckState {
  return events.reduce(checkReducer, start);
}

describe("checkReducer", () => {
  it("walks one claim through every stage", () => {
    let s = run([{ type: "snapshot", record: record() }]);
    expect(currentStep(s)).toBe(0);
    s = run([{ type: "ingest_done", chars: 100 }], s);
    expect(currentStep(s)).toBe(1);
    s = run([{ type: "claims_found", claims: [{ id: 1, text: "c1" }, { id: 2, text: "c2" }], skipped: 1, language: "en" }], s);
    expect(s.progress.claims.map((c) => c.stage)).toEqual(["planning", "planning"]);
    expect(s.progress.skipped).toBe(1);
    expect(currentStep(s)).toBe(2);
    s = run([
      { type: "queries_planned", claim_id: 1, queries: ["q"] },
      { type: "sources_found", claim_id: 1, count: 4, domains: ["a.org"] },
      { type: "evidence_ready", claim_id: 1, verified: 2, discarded: 1 },
      { type: "verdicts_drafted", claim_id: 1, draft_label: "TRUE", jury_label: "FALSE", agreed: false },
      { type: "debate_started", claim_id: 1, queries: ["x"] },
    ], s);
    const c1 = s.progress.claims[0];
    expect(c1.stage).toBe("debating");
    expect([c1.sourceCount, c1.verified, c1.discarded, c1.debated]).toEqual([4, 2, 1, true]);
    expect(currentStep(s)).toBe(2); // claim 2 is still planning
    s = run([
      { type: "queries_planned", claim_id: 2, queries: ["q"] },
      { type: "sources_found", claim_id: 2, count: 0, domains: [] },
      { type: "claim_done", claim_id: 2, final: verdict, agreed: true, debated: false },
    ], s);
    expect(currentStep(s)).toBe(4);
    s = run([{ type: "claim_done", claim_id: 1, final: verdict, agreed: false, debated: true }], s);
    s = run([{ type: "done", totals: { cost_usd: 0.01 } }], s);
    expect(s.progress.finished).toBe(true);
    expect(currentStep(s)).toBe(5);
  });

  it("marks a recheck when both models found too little evidence", () => {
    let s = run([{ type: "claims_found", claims: [{ id: 1, text: "c" }], skipped: 0, language: "en" }]);
    s = run([
      { type: "verdicts_drafted", claim_id: 1, draft_label: "UNVERIFIED", jury_label: "UNVERIFIED", agreed: true },
      { type: "recheck_started", claim_id: 1, queries: ["q"] },
    ], s);
    expect(s.progress.claims[0]).toMatchObject({ stage: "debating", rechecked: true, debated: true });
    expect(currentStep(s)).toBe(4);
  });

  it("never moves a claim backwards", () => {
    let s = run([{ type: "claims_found", claims: [{ id: 1, text: "c" }], skipped: 0, language: "en" }]);
    s = run([{ type: "claim_done", claim_id: 1, final: verdict, agreed: true, debated: false }], s);
    s = run([{ type: "queries_planned", claim_id: 1, queries: [] }], s);
    expect(s.progress.claims[0].stage).toBe("done");
  });

  it("collects live model calls", () => {
    const s = run([{ type: "model_call", step: "extract_claims", model: "nvidia/x", input_tokens: 1, output_tokens: 2, latency_s: 0.5, cost_usd: null }]);
    expect(s.progress.trace).toEqual([{ step: "extract_claims", model: "nvidia/x", input_tokens: 1, output_tokens: 2, latency_s: 0.5, cost_usd: null }]);
  });

  it("is idempotent when a reconnect replays the event history", () => {
    const call = { type: "model_call" as const, step: "extract_claims", model: "nvidia/x", input_tokens: 1, output_tokens: 2, latency_s: 0.5, cost_usd: null };
    const history: CheckAction[] = [
      { type: "snapshot", record: record() },
      { type: "ingest_done", chars: 100 },
      call,
      { type: "claims_found", claims: [{ id: 1, text: "c1" }], skipped: 0, language: "en" },
      { type: "queries_planned", claim_id: 1, queries: ["q"] },
    ];
    const once = run(history);
    const twice = run(history, once); // reconnect: new snapshot + full replay
    expect(twice.progress).toEqual(once.progress);
    expect(twice.progress.trace).toHaveLength(1);
    expect(run([call], once).progress.trace).toHaveLength(1); // a stray duplicate is skipped too
    expect(run([{ type: "ping" }], once)).toBe(once);
  });

  it("records stream errors", () => {
    const s = run([{ type: "error", message: "Too long" }]);
    expect(s.progress.finished).toBe(true);
    expect(s.progress.message).toBe("Too long");
  });

  it("marks finished claims from a mid-run snapshot", () => {
    const done = record({
      language: "en",
      claims: [{ id: 2, text: "c2", queries: [], evidence: [], result: { draft: verdict, jury: verdict, agreed: true, debated: false, final: verdict } }],
    });
    const s = run([{ type: "snapshot", record: done }]);
    expect(s.progress.claimsFound).toBe(true);
    expect(s.progress.claims).toMatchObject([{ id: 2, stage: "done", text: "c2" }]);
  });

  it("treats a done record as the final step", () => {
    const s = run([{ type: "record", record: record({ status: "done", language: "en", totals: { duration_s: 3 } }) }]);
    expect(currentStep(s)).toBe(5);
    expect(s.progress.totals).toEqual({ duration_s: 3 });
  });
});
