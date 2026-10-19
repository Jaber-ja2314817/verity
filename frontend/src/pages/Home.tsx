import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import InputBox, { detectMode, validateInput } from "../components/InputBox";
import { humanizeWait } from "../lib/format";
import { useTitle } from "../lib/useTitle";
import type { Example } from "../types";

const FALLBACK_EXAMPLES: Example[] = [
  { title: "Boiling point", type: "text", value: "Water always boils at 100°C." },
];
const MAX_EXAMPLES = 3;

const PILLARS = [
  {
    n: "01",
    tag: "Context",
    title: "A claim, taken apart.",
    body: "Separate what can be checked from what needs definition or context.",
  },
  {
    n: "02",
    tag: "Evidence",
    title: "Sources you can inspect.",
    body: "Read the evidence behind a finding, including what challenges it.",
  },
  {
    n: "03",
    tag: "Scrutiny",
    title: "Room for uncertainty.",
    body: "Compare verification passes and see the limits of a conclusion.",
  },
];

function friendly(e: unknown): string {
  if (e instanceof ApiError) {
    // Rate-limit messages already say how long to wait; just make long waits readable.
    if (e.status === 429) return humanizeWait(e.message);
    if (e.status >= 500) return "Verity is having trouble right now. Please try again in a moment.";
    return e.message;
  }
  return "Something went wrong. Please try again.";
}

export default function Home() {
  useTitle(null);
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = (location.state as { prefill?: unknown } | null)?.prefill;
  const [value, setValue] = useState(typeof prefill === "string" ? prefill : "");
  const [examples, setExamples] = useState<Example[]>(FALLBACK_EXAMPLES);

  useEffect(() => {
    let alive = true;
    api
      .examples()
      .then((list) => {
        const usable = list.filter((x) => x.type === "text" && x.value.trim().length >= 20);
        if (alive && usable.length) setExamples(usable.slice(0, MAX_EXAMPLES));
      })
      .catch(() => undefined); // keep the built-in sample
    return () => {
      alive = false;
    };
  }, []);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function investigate(raw: string) {
    const v = raw.trim();
    if (validateInput(v) || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const body = detectMode(v) === "url" ? { url: v } : { text: v };
      const { id } = await api.createCheck(body);
      navigate(`/c/${id}`);
    } catch (e) {
      setError(friendly(e));
      setSubmitting(false);
    }
  }

  return (
    <div className="pt-6 sm:pt-14">
      <section className="max-w-xl">
        <p className="eyebrow text-accent">For the claims that deserve a closer look</p>
        <h1 className="mt-6 font-serif text-[2.35rem] font-light leading-[1.12] tracking-[-0.02em] sm:text-[3.3rem]">
          Before you believe it,
          <br />
          <em className="text-accent">look into it.</em>
        </h1>
        <p className="mt-6 max-w-md text-base leading-relaxed text-muted">
          Bring a claim. Trace the sources. See what holds up—and where the evidence stops.
        </p>
      </section>

      <section className="mt-10 max-w-[48.5rem]">
        <InputBox
          value={value}
          onChange={(v) => {
            setValue(v);
            setError(null);
          }}
          submitting={submitting}
          error={error}
          onSubmit={() => investigate(value)}
          autoFocus={typeof prefill === "string"}
        />
        <div className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-2 text-xs">
          <span className="uppercase tracking-[0.08em] text-muted">Explore a sample</span>
          <ul className="flex flex-wrap gap-x-4 gap-y-2">
            {examples.map((x) => (
              <li key={x.value}>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => {
                    setValue(x.value);
                    investigate(x.value);
                  }}
                  className="border-b border-muted pb-0.5 text-left text-sm text-ink/85 transition hover:border-accent hover:text-accent disabled:opacity-60"
                >
                  “{x.value}” <span aria-hidden>↗</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-label="What an investigation includes" className="mt-16 border-t border-rule/80 pt-6">
        <ol className="grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-10">
          {PILLARS.map((p) => (
            <li key={p.n}>
              <p className="font-serif text-[15px] text-accent">
                {p.n} / {p.tag}
              </p>
              <p className="mt-2 text-sm font-semibold">{p.title}</p>
              <p className="mt-2 max-w-[17rem] text-[13px] leading-relaxed text-muted">{p.body}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
