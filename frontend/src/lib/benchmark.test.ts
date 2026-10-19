import { describe, expect, it } from "vitest";
import { parseBenchmark, pct } from "./benchmark";

describe("parseBenchmark", () => {
  it("returns null for the empty and missing states", () => {
    expect(parseBenchmark(null)).toBeNull();
    expect(parseBenchmark({})).toBeNull();
    expect(parseBenchmark({ single: { n: 0, errors: 2 }, jury: { n: 0 } })).toBeNull();
  });
  it("reads the build_summary shape", () => {
    const b = parseBenchmark({
      single: { n: 40, errors: 0, correct: 30, abstained: 4, accuracy: 0.75, abstain_rate: 0.1, accuracy_when_answered: 0.8333, avg_cost_usd: 0.0012, avg_time_s: 9.5 },
      jury: { n: 40, errors: 1, correct: 34, abstained: 3, accuracy: 0.85, abstain_rate: 0.075, avg_cost_usd: 0.004, avg_time_s: 14.2, agreement_rate: 0.8, debate_rate: 0.15 },
      n: 40, claims_total: 40, date: "2026-10-18", models: { fast: "nvidia/a", judge: "nvidia/b" },
      rule: "A prediction is correct when...", description: "40 human-labeled claims",
    });
    expect(b?.single?.accuracy).toBe(0.75);
    expect(b?.jury?.agreement_rate).toBe(0.8);
    expect(b?.models).toEqual({ fast: "nvidia/a", judge: "nvidia/b" });
    expect(b?.claimsTotal).toBe(40);
    expect(b?.date).toBe("2026-10-18");
  });
  it("ignores wrongly typed fields", () => {
    const b = parseBenchmark({ jury: { accuracy: "0.9", avg_time_s: 3 }, n: "40", models: "x" });
    expect(b?.jury).toEqual({ avg_time_s: 3 });
    expect(b?.single).toBeNull();
    expect(b?.n).toBeUndefined();
    expect(b?.models).toBeUndefined();
  });
  it("formats fractions as percentages", () => {
    expect(pct(0.8333)).toBe("83.3%");
    expect(pct(1)).toBe("100.0%");
  });
});
