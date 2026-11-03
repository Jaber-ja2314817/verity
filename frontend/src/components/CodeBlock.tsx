import { useEffect, useState } from "react";
import { copy } from "../lib/clipboard";

/** A command or snippet with a copy button. */
export default function CodeBlock({ code, label }: { code: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const t = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(t);
  }, [state]);
  return (
    <div className="relative border border-line bg-frame">
      <button
        type="button"
        aria-label={`Copy ${label}`}
        onClick={async () => setState((await copy(code)) ? "copied" : "failed")}
        className="eyebrow absolute right-2 top-2 border border-line bg-surface px-2 py-1 text-muted hover:text-ink"
      >
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}
      </button>
      <pre className="overflow-x-auto p-4 pr-20 font-mono text-xs leading-relaxed text-ink">{code}</pre>
    </div>
  );
}
