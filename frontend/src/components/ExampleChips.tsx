import { useEffect, useState } from "react";
import { api } from "../api";
import type { Example } from "../types";

export default function ExampleChips({ onPick }: { onPick: (ex: Example) => void }) {
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .examples()
      .then((list) => alive && setExamples(Array.isArray(list) ? list.slice(0, 6) : []))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  if (failed || (examples && examples.length === 0)) return null;

  return (
    <div className="mt-5">
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">Try an example</p>
      <div className="flex flex-wrap gap-2">
        {examples === null
          ? [64, 88, 72, 96].map((w, i) => (
              <span
                key={i}
                aria-hidden
                className="h-8 animate-pulse rounded-full bg-line"
                style={{ width: `${w * 1.4}px` }}
              />
            ))
          : examples.map((ex) => (
              <button
                key={ex.title}
                type="button"
                onClick={() => onPick(ex)}
                className="max-w-full truncate rounded-full border border-line bg-surface px-3.5 py-1.5 text-left text-sm text-ink transition hover:border-accent hover:text-accent-ink"
                title={ex.value}
              >
                {ex.title}
              </button>
            ))}
      </div>
    </div>
  );
}
