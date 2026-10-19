import { useEffect, useState } from "react";
import { checkToText } from "../lib/format";
import type { CheckRecord } from "../types";

async function copy(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the legacy path */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

export default function ShareButton({ record }: { record: CheckRecord }) {
  const [status, setStatus] = useState<string | null>(null);
  useEffect(() => {
    if (!status) return;
    const t = setTimeout(() => setStatus(null), 2000);
    return () => clearTimeout(t);
  }, [status]);

  const url = window.location.origin + window.location.pathname; // no #claim-N anchor
  const btn =
    "inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2 text-sm font-medium hover:border-ink";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        className={btn}
        onClick={async () => setStatus((await copy(url)) ? "Link copied" : "Copy failed")}
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path d="M6.5 9.5l3-3M7 4.5l1-1a2.8 2.8 0 014 4l-1 1M9 11.5l-1 1a2.8 2.8 0 01-4-4l1-1" strokeLinecap="round" />
        </svg>
        Share link
      </button>
      <button
        type="button"
        className={btn}
        onClick={async () =>
          setStatus((await copy(checkToText(record, url))) ? "Result copied as text" : "Copy failed")
        }
      >
        Copy as text
      </button>
      <span role="status" aria-live="polite" className="text-sm text-accent-ink">
        {status}
      </span>
    </div>
  );
}
