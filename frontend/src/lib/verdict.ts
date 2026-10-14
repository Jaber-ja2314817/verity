import type { Label } from "../types";

export interface VerdictStyle {
  text: string; // Tailwind text color class
  bg: string; // Tailwind background class
  border: string;
  title: string; // human label
  blurb: string;
}

export const VERDICT: Record<Label, VerdictStyle> = {
  TRUE: {
    text: "text-v-true",
    bg: "bg-v-true-bg",
    border: "border-v-true/30",
    title: "True",
    blurb: "Reliable evidence supports the claim.",
  },
  FALSE: {
    text: "text-v-false",
    bg: "bg-v-false-bg",
    border: "border-v-false/30",
    title: "False",
    blurb: "Reliable evidence contradicts the claim.",
  },
  MISLEADING: {
    text: "text-v-misleading",
    bg: "bg-v-misleading-bg",
    border: "border-v-misleading/30",
    title: "Misleading",
    blurb: "Partly true, but missing key context or exaggerated.",
  },
  UNVERIFIED: {
    text: "text-v-unverified",
    bg: "bg-v-unverified-bg",
    border: "border-v-unverified/30",
    title: "Unverified",
    blurb: "Not enough reliable evidence either way.",
  },
};
