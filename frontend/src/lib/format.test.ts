import { describe, expect, it } from "vitest";
import { checkToText, formatCost, humanizeWait, formatSeconds, formatTokens, relativeTime, shortModel } from "./format";
import type { CheckRecord } from "../types";

describe("format", () => {
  it("formats cost", () => {
    expect(formatCost(null)).toBe("—");
    expect(formatCost(0)).toBe("$0");
    expect(formatCost(0.00004)).toBe("<$0.0001");
    expect(formatCost(0.0042)).toBe("$0.0042");
    expect(formatCost(0.1234)).toBe("$0.123");
    expect(formatCost(2.5)).toBe("$2.50");
  });
  it("formats tokens and seconds", () => {
    expect(formatTokens(1234)).toBe("1,234");
    expect(formatTokens(undefined)).toBe("—");
    expect(formatSeconds(0.42)).toBe("0.4 s");
    expect(formatSeconds(42.4)).toBe("42 s");
    expect(formatSeconds(65)).toBe("1 min 5 s");
    expect(formatSeconds(120)).toBe("2 min");
  });
  it("formats relative time", () => {
    const now = Date.parse("2026-10-14T12:00:00Z");
    expect(relativeTime("2026-10-14T11:59:50Z", now)).toBe("just now");
    expect(relativeTime("2026-10-14T11:55:00Z", now)).toBe("5 min ago");
    expect(relativeTime("2026-10-14T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-10-12T12:00:00Z", now)).toBe("2 days ago");
    expect(relativeTime("nonsense", now)).toBe("");
  });
  it("shortens model ids", () => {
    expect(shortModel("nvidia/Nemotron-3-Ultra-550b-a55b")).toBe("Nemotron-3-Ultra-550b-a55b");
  });
  it("humanizes long rate-limit waits", () => {
    expect(humanizeWait("Please wait 412 seconds and try again.")).toBe("Please wait about 7 minutes and try again.");
    expect(humanizeWait("Please wait 30 seconds and try again.")).toBe("Please wait 30 seconds and try again.");
    expect(humanizeWait("Try again tomorrow.")).toBe("Try again tomorrow.");
  });
  it("builds a plain-text summary with cited verified sources only", () => {
    const v = { label: "FALSE" as const, confidence: 88, explanation: "Not visible.", cited_source_ids: [1, 2], missing_evidence_queries: [] };
    const src = (id: number) => ({ id, url: `https://s${id}.org/a`, title: "t", domain: `s${id}.org`, content: "", favicon: null });
    const record: CheckRecord = {
      id: "x", created_at: "2026-10-14T12:00:00Z", status: "done", input_type: "text",
      input_preview: "p", language: "en",
      skipped_claims: [{ id: 2, text: "Who won?", checkworthy: false, reason: "Open question - rephrase it as a statement" }], trace: [], totals: {}, error: null,
      claims: [{
        id: 1, text: "The wall is visible from space.", queries: [],
        evidence: [
          { source: src(1), stance: "refutes", quote: "q", quote_verified: true, note: "" },
          { source: src(2), stance: "refutes", quote: "q", quote_verified: false, note: "" },
        ],
        result: { draft: v, jury: { ...v, explanation: "Jury view." }, agreed: true, debated: false, final: v },
      }],
    };
    const text = checkToText(record, "https://verity.app/c/x");
    expect(text).toContain('1. "The wall is visible from space."');
    expect(text).toContain("FALSE (confidence 88%)");
    expect(text).toContain("s1.org: https://s1.org/a");
    expect(text).not.toContain("s2.org");
    expect(text).toContain("Both models agreed independently.");
    expect(text).toContain('- "Who won?" (Open question - rephrase it as a statement)');
    expect(text).toContain("Full result: https://verity.app/c/x");
  });
});
