import { describe, expect, it } from "vitest";
import { confidenceLevel, juryModels, juryOutcome, phrasingHint, skipInfo } from "./claims";
import type { Verdict } from "../types";

const v = (label: Verdict["label"], explanation = "e"): Verdict => ({
  label, confidence: 70, explanation, cited_source_ids: [], missing_evidence_queries: [],
});

describe("juryOutcome", () => {
  it("tells a code-settled verdict from a real agreement", () => {
    const same = v("UNVERIFIED", "No sources found.");
    expect(juryOutcome({ draft: same, jury: same, agreed: true, debated: false, final: same })).toBe("settled");
    expect(juryOutcome({ draft: v("TRUE", "a"), jury: v("TRUE", "b"), agreed: true, debated: false, final: v("TRUE") })).toBe("agreed");
    expect(juryOutcome({ draft: v("TRUE"), jury: v("FALSE"), agreed: false, debated: true, final: v("FALSE") })).toBe("debated");
    expect(juryOutcome({ draft: v("TRUE"), jury: v("FALSE"), agreed: false, debated: false, final: v("FALSE") })).toBe("disagreed");
    expect(juryOutcome({ draft: v("UNVERIFIED", "a"), jury: v("UNVERIFIED", "b"), agreed: true, debated: true, rechecked: true, final: v("TRUE") })).toBe("rechecked");
  });
});

describe("confidenceLevel", () => {
  it("buckets confidence", () => {
    expect(confidenceLevel(95)).toBe("high");
    expect(confidenceLevel(80)).toBe("high");
    expect(confidenceLevel(60)).toBe("moderate");
    expect(confidenceLevel(10)).toBe("low");
  });
});

describe("skipInfo", () => {
  it("explains claims dropped by the per-check limit", () => {
    const s = skipInfo({ id: 5, text: "x", checkworthy: true, reason: "Specific historical fact" });
    expect(s.reason).toContain("up to 3 claims");
    expect(s.hint).toBe("Check it on its own.");
  });
  it("gives an actionable hint for open questions and opinions", () => {
    expect(skipInfo({ id: 1, text: "Who won?", checkworthy: false, reason: "Open question - rephrase it as a statement" }).hint).toMatch(/instead of/);
    expect(skipInfo({ id: 1, text: "Who won?", checkworthy: false, reason: "A question" }).hint).toMatch(/Rephrase/);
    expect(skipInfo({ id: 2, text: "Pizza is great", checkworthy: false, reason: "Opinion" }).hint).toMatch(/Opinions/);
    expect(skipInfo({ id: 3, text: "lol", checkworthy: false, reason: "Joke" }).hint).toBeNull();
    expect(skipInfo({ id: 4, text: "x", checkworthy: false, reason: " " }).reason).toBe("Not a checkable factual statement.");
  });
});

describe("phrasingHint", () => {
  it("flags single open questions only", () => {
    expect(phrasingHint("Who built the Eiffel Tower?")).toMatch(/Open questions/);
    expect(phrasingHint("Is the Earth flat?")).toMatch(/Yes\/no/);
    expect(phrasingHint("The Earth is flat.")).toBeNull();
    expect(phrasingHint("Who knew? The tower was built in 1889. It is tall.")).toBeNull();
    expect(phrasingHint("https://example.com/what?")).toBeNull();
    expect(phrasingHint("")).toBeNull();
  });
});

describe("juryModels", () => {
  it("reads per-claim roles from the trace", () => {
    const t = (step: string, model: string) => ({ step, model, input_tokens: 1, output_tokens: 1, latency_s: 1, cost_usd: null });
    const trace = [t("verdict_draft[claim 1]", "nvidia/fast"), t("verdict_jury[claim 1]", "nvidia/judge"), t("verdict_draft[claim 12]", "nvidia/other")];
    expect(juryModels(trace, 1)).toEqual({ draft: "nvidia/fast", jury: "nvidia/judge", final: undefined });
    expect(juryModels(trace, 2)).toEqual({ draft: undefined, jury: undefined, final: undefined });
  });
});
