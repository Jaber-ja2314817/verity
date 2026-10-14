import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import ExampleChips from "../components/ExampleChips";
import InputBox, { type InputMode } from "../components/InputBox";
import type { Example } from "../types";
import { STEP_ICONS } from "./HowItWorks";

const STRIP = [
  { icon: STEP_ICONS.claims, title: "Claims", body: "Split into checkable statements" },
  { icon: STEP_ICONS.search, title: "Search", body: "Evidence from the live web" },
  { icon: STEP_ICONS.jury, title: "Two-model jury", body: "Two Nemotron models judge independently" },
  { icon: STEP_ICONS.verdict, title: "Verdict", body: "With verified quotes and sources" },
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
  const [mode, setMode] = useState<InputMode>("text");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const body = mode === "text" ? { text: text.trim() } : { url: url.trim() };
      const { id } = await api.createCheck(body);
      navigate(`/c/${id}`);
    } catch (e) {
      setError(friendly(e));
      setSubmitting(false);
    }
  }

  function pick(ex: Example) {
    setError(null);
    setMode(ex.type);
    if (ex.type === "text") setText(ex.value);
    else setUrl(ex.value);
  }

  return (
    <div className="pt-6 sm:pt-14">
      <section className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-ink">
          Two-model fact-checking
        </p>
        <h1 className="mt-3 font-serif text-5xl leading-[1.02] tracking-tight sm:text-7xl">Verity</h1>
        <p className="mt-3 font-serif text-2xl italic text-muted sm:text-3xl">Fact-checks you can audit.</p>
        <p className="mt-6 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">
          Paste any text or link. Verity finds each factual claim, searches the web for evidence, and
          has two independent NVIDIA Nemotron models rule on it, with quotes checked word for word.
        </p>
      </section>

      <section className="mt-10 max-w-3xl">
        <InputBox
          mode={mode}
          onModeChange={(m) => {
            setMode(m);
            setError(null);
          }}
          text={text}
          onTextChange={setText}
          url={url}
          onUrlChange={setUrl}
          submitting={submitting}
          error={error}
          onSubmit={submit}
        />
        <ExampleChips onPick={pick} />
      </section>

      <section aria-labelledby="strip-title" className="mt-20">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="strip-title" className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">
            How it works
          </h2>
          <Link to="/how-it-works" className="text-sm text-muted underline-offset-4 hover:text-ink hover:underline">
            Details →
          </Link>
        </div>
        <ol className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STRIP.map((s, i) => (
            <li key={s.title} className="relative flex gap-4 rounded-xl border border-line bg-surface p-4 lg:flex-col lg:gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-paper text-ink">{s.icon}</span>
              <div>
                <p className="text-sm font-semibold">
                  <span className="mr-1.5 text-muted tabular-nums">{i + 1}.</span>
                  {s.title}
                </p>
                <p className="mt-1 text-sm leading-snug text-muted">{s.body}</p>
              </div>
              {i < STRIP.length - 1 && (
                <span aria-hidden className="absolute -right-2.5 top-1/2 hidden -translate-y-1/2 text-muted lg:block">
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
