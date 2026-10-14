import { VERDICT } from "../lib/verdict";
import type { Label } from "../types";

function Icon({ label }: { label: Label }) {
  const common = {
    viewBox: "0 0 16 16",
    className: "h-3.5 w-3.5",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (label) {
    case "TRUE":
      return (
        <svg {...common}>
          <path d="M3 8.5l3 3L13 4.5" />
        </svg>
      );
    case "FALSE":
      return (
        <svg {...common}>
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      );
    case "MISLEADING":
      return (
        <svg {...common}>
          <path d="M8 3.5v5.5M8 12.2v.3" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d="M6 6a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2v.5M8 12.2v.3" />
        </svg>
      );
  }
}

/** Verdict label with color, icon and text (never color alone). */
export default function VerdictBadge({ label, size = "md" }: { label: Label; size?: "sm" | "md" }) {
  const v = VERDICT[label];
  const pad = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wide ${pad} ${v.text} ${v.bg} ${v.border}`}
    >
      <Icon label={label} />
      {v.title}
    </span>
  );
}
