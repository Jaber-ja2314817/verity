import { describe, expect, it } from "vitest";
import { formatPublished, organizeEvidence, reliabilityBadge } from "./evidence";
import type { Evidence, Reliability, Stance } from "../types";

const ev = (id: number, stance: Stance, verified = true, reliability?: Reliability): Evidence => ({
  source: { id, url: `https://s${id}.org`, title: `t${id}`, domain: `s${id}.org`, content: "", favicon: null, reliability },
  stance,
  quote: verified || stance !== "irrelevant" ? "a quote of six or more words" : "",
  quote_verified: verified,
  note: "",
});

describe("organizeEvidence", () => {
  it("groups verified quotes by stance and sets the rest aside", () => {
    const v = organizeEvidence(
      [ev(1, "supports"), ev(2, "refutes"), ev(3, "refutes", false), ev(4, "irrelevant", false), ev(5, "mixed")],
      [2],
    );
    expect(v.groups.map((g) => g.stance)).toEqual(["refutes", "supports", "mixed"]); // cited group first
    expect(v.verified).toBe(3);
    expect(v.cited).toBe(1);
    expect(v.unverified.map((e) => e.source.id)).toEqual([3]);
    expect(v.irrelevant.map((e) => e.source.id)).toEqual([4]);
  });
  it("orders within a group: cited, then reliability, then id", () => {
    const v = organizeEvidence(
      [ev(1, "supports", true, "low"), ev(2, "supports"), ev(3, "supports", true, "high"), ev(4, "supports", true, "medium")],
      [4],
    );
    expect(v.groups[0].items.map((e) => e.source.id)).toEqual([4, 3, 2, 1]);
  });
  it("keeps supports/refutes/mixed order when nothing is cited", () => {
    const v = organizeEvidence([ev(1, "mixed"), ev(2, "refutes"), ev(3, "supports")], []);
    expect(v.groups.map((g) => g.stance)).toEqual(["supports", "refutes", "mixed"]);
  });
  it("ignores cited ids whose quote is not verified", () => {
    const v = organizeEvidence([ev(1, "supports", false)], [1]);
    expect(v.groups).toEqual([]);
    expect(v.cited).toBe(0);
  });
});

describe("reliabilityBadge", () => {
  it("is quiet for unknown or missing tiers", () => {
    expect(reliabilityBadge(undefined)).toBeNull();
    expect(reliabilityBadge("unknown")).toBeNull();
    expect(reliabilityBadge("high")?.text).toBe("High reliability");
    expect(reliabilityBadge("low")?.tone).toBe("warn");
  });
});

describe("formatPublished", () => {
  it("formats bare dates in UTC (no off-by-one day)", () => {
    expect(formatPublished("2024-03-04")).toBe("Mar 4, 2024");
    expect(formatPublished("2024-03-04T23:30:00Z")).toBe("Mar 4, 2024");
  });
  it("returns null for missing or invalid dates", () => {
    expect(formatPublished(null)).toBeNull();
    expect(formatPublished(undefined)).toBeNull();
    expect(formatPublished("")).toBeNull();
    expect(formatPublished("someday")).toBeNull();
  });
});
