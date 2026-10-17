import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import InputBox, { detectMode, validateInput } from "../components/InputBox";

const SAMPLE = "Water always boils at 100°C.";

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
    if (e.status === 429 && e.retryAfter) {
      const mins = Math.ceil(e.retryAfter / 60);
      return `${e.message} (try again in about ${mins} minute${mins === 1 ? "" : "s"})`;
    }
    return e.message;
  }
  return "Something went wrong. Please try again.";
}

export default function Home() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
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
        />
        <p className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-2 text-xs">
          <span className="uppercase tracking-[0.08em] text-muted">Explore a sample</span>
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              setValue(SAMPLE);
              investigate(SAMPLE);
            }}
            className="border-b border-muted pb-0.5 text-sm text-ink/85 transition hover:border-accent hover:text-accent disabled:opacity-60"
          >
            “{SAMPLE}” <span aria-hidden>↗</span>
          </button>
        </p>
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
