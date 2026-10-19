import type { Evidence, Reliability, Stance } from "../types";

export type UsableStance = Exclude<Stance, "irrelevant">;

const STANCE_ORDER: UsableStance[] = ["supports", "refutes", "mixed"];
const RELIABILITY_RANK: Record<Reliability, number> = { high: 0, medium: 1, unknown: 2, low: 3 };

export interface EvidenceGroup {
  stance: UsableStance;
  items: Evidence[]; // cited first, then more reliable, then by source id
  cited: number;
}

export interface EvidenceView {
  groups: EvidenceGroup[]; // only non-empty groups
  verified: number;
  cited: number;
  unverified: Evidence[]; // the model gave a quote/stance, but code couldn't find it on the page
  irrelevant: Evidence[]; // the source didn't address the claim
}

/** Mirrors backend usable(): only verified quotes with a real stance reach the jury. */
export function isUsable(e: Evidence): boolean {
  return e.quote_verified && e.stance !== "irrelevant";
}

/**
 * Split a claim's evidence into stance groups (verified quotes only) plus what was set aside.
 * Groups the verdict relied on most come first; ties keep supports / refutes / mixed order.
 */
export function organizeEvidence(evidence: Evidence[], citedIds: number[]): EvidenceView {
  const cited = new Set(citedIds);
  const rank = (e: Evidence) => [
    cited.has(e.source.id) ? 0 : 1,
    RELIABILITY_RANK[e.source.reliability ?? "unknown"],
    e.source.id,
  ];
  const byRank = (a: Evidence, b: Evidence) => {
    const ra = rank(a);
    const rb = rank(b);
    return ra[0] - rb[0] || ra[1] - rb[1] || ra[2] - rb[2];
  };
  const usable = evidence.filter(isUsable);
  const groups = STANCE_ORDER.map((stance) => {
    const items = usable.filter((e) => e.stance === stance).sort(byRank);
    return { stance, items, cited: items.filter((e) => cited.has(e.source.id)).length };
  })
    .filter((g) => g.items.length > 0)
    .sort((a, b) => b.cited - a.cited || STANCE_ORDER.indexOf(a.stance) - STANCE_ORDER.indexOf(b.stance));
  const byId = (a: Evidence, b: Evidence) => a.source.id - b.source.id;
  return {
    groups,
    verified: usable.length,
    cited: usable.filter((e) => cited.has(e.source.id)).length,
    unverified: evidence.filter((e) => e.stance !== "irrelevant" && !e.quote_verified).sort(byId),
    irrelevant: evidence.filter((e) => e.stance === "irrelevant").sort(byId),
  };
}

export interface ReliabilityBadge {
  text: string;
  title: string;
  tone: "good" | "neutral" | "warn";
}

/** A quiet badge for the source's domain tier; null when the tier is unknown or missing. */
export function reliabilityBadge(r: Reliability | undefined): ReliabilityBadge | null {
  switch (r) {
    case "high":
      return {
        text: "High reliability",
        title: "Domain rated highly reliable (e.g. official, scientific or reference source)",
        tone: "good",
      };
    case "medium":
      return { text: "Medium reliability", title: "Domain rated generally reliable", tone: "neutral" };
    case "low":
      return {
        text: "Low reliability",
        title: "Domain rated low reliability: weigh this source with care",
        tone: "warn",
      };
    default:
      return null;
  }
}

/** "2024-03-04" or a full ISO timestamp -> "Mar 4, 2024". Dates are shown in UTC so a bare
 * date never shifts to the previous day in western time zones. */
export function formatPublished(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const s = iso.trim();
  const t = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T00:00:00Z` : s);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}
