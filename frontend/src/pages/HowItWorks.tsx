import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useTitle } from "../lib/useTitle";
import type { Health } from "../types";

const VERDICT_ICON = (
  <svg
    viewBox="0 0 24 24"
    className="h-6 w-6"
    aria-hidden
    fill="none"
    stroke="currentColor"
    strokeWidth={1.7}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M12 3.5l7 3v5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9v-5l7-3z" />
    <path d="M8.8 12.2l2.2 2.2 4.2-4.4" />
  </svg>
);

interface Stage {
  n: string;
  title: string;
  model: "fast" | "judge" | "code" | "search";
  body: string;
  highlight?: boolean;
}

const STAGES: Stage[] = [
  {
    n: "01",
    title: "Read",
    model: "code",
    body: "Your text is cleaned up. For a link, the article text is fetched first. Up to 5,000 characters are used.",
  },
  {
    n: "02",
    title: "Find claims",
    model: "fast",
    body: "Up to three self-contained factual claims, most important first. Yes/no questions become the statement they ask about. Opinions, predictions and open questions are set aside, each with a reason you can see.",
  },
  {
    n: "03",
    title: "Plan searches",
    model: "fast",
    body: "Three queries per claim: one neutral, one looking for support, one looking for debunks, so the search isn't one-sided.",
  },
  {
    n: "04",
    title: "Search the web",
    model: "search",
    body: "Results are merged, de-duplicated and ranked, with at most two per site and eight per claim, so one source can't dominate. Each source is tagged with a reliability tier for its domain and its publication date when known, and both models see these tags when they weigh the evidence.",
  },
  {
    n: "05",
    title: "Check evidence",
    model: "fast",
    body: "Every source is marked as supporting, refuting, mixed or irrelevant, and the model copies the one sentence that matters, word for word. Code then confirms the sentence really is on the page. If it isn't, it's discarded.",
    highlight: true,
  },
  {
    n: "06",
    title: "Two-model jury",
    model: "judge",
    body: "The fast model drafts a verdict while the judge model rules on the same verified quotes, in parallel, without seeing the draft. Code drops any citation that isn't verified evidence; True or False with no valid citation becomes Unverified.",
    highlight: true,
  },
  {
    n: "07",
    title: "Debate if needed",
    model: "judge",
    body: "If both reach the same label, that's the verdict, with their average confidence. If not, Verity searches for the evidence they said was missing, verifies it the same way, and the judge makes the final ruling from both opinions and all the evidence. If both say Unverified, Verity also searches once more before giving up.",
  },
];

const READING: { term: string; body: string }[] = [
  {
    term: "True · False",
    body: "Reliable, verified evidence clearly supports or contradicts the claim as an ordinary reader means it. Never given without at least one cited, verified quote.",
  },
  {
    term: "Misleading",
    body: "Partly true, but exaggerated, outdated or missing context that changes the conclusion. Not used for harmless technicalities.",
  },
  {
    term: "Unverified",
    body: "The evidence found was weak, conflicting or missing. It is not a polite way of saying False. Where possible, Verity shows the searches that could settle it.",
  },
  {
    term: "Confidence",
    body: "How sure the models are of the label given the evidence they saw. It is not the probability that the claim is true.",
  },
  {
    term: "Cited in verdict",
    body: "The sources the final verdict relied on. Other verified quotes are shown too, grouped by stance, including any that cut against the verdict.",
  },
  {
    term: "Reliability tier",
    body: "A rating of the website's domain, not of the individual article. A useful signal, not a guarantee.",
  },
];

function modelName(stage: Stage, health: Health | null, failed: boolean): string {
  if (stage.model === "code") return "Plain code";
  if (stage.model === "search") return "Tavily search + code";
  if (health) return stage.model === "fast" ? health.models.fast : health.models.judge;
  if (failed) return stage.model === "fast" ? "Fast Nemotron model" : "Judge Nemotron model";
  return "Loading…";
}

export default function HowItWorks() {
  useTitle("How it works");
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <article className="pt-6 sm:pt-12">
      <p className="eyebrow text-accent">How it works</p>
      <h1 className="mt-3 max-w-3xl font-serif text-4xl leading-[1.1] tracking-tight sm:text-5xl">
        Every verdict shows its work.
      </h1>
      <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
        Verity doesn't give one confident answer. It breaks your text into claims, gathers evidence
        from the live web, and has two different NVIDIA Nemotron models judge each claim.
      </p>

      <ol className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        {STAGES.map((s) => (
          <li key={s.n} className={`flex flex-col gap-3 p-5 sm:p-6 ${s.highlight ? "bg-surface" : "bg-paper"}`}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-serif text-2xl text-muted tabular-nums">{s.n}</span>
              <span
                className={`max-w-[70%] truncate rounded-full border px-2 py-0.5 font-mono text-[11px] ${
                  s.model === "judge"
                    ? "border-accent/40 text-accent-ink"
                    : "border-line text-muted"
                }`}
                title={modelName(s, health, failed)}
              >
                {modelName(s, health, failed)}
              </span>
            </div>
            <h2 className="text-lg font-semibold tracking-tight">{s.title}</h2>
            <p className="text-sm leading-relaxed text-muted">{s.body}</p>
          </li>
        ))}
        <li className="flex flex-col justify-center gap-2 bg-ink p-5 text-paper sm:p-6 lg:col-span-2">
          <span className="text-accent">{VERDICT_ICON}</span>
          <h2 className="text-lg font-semibold">Verdict</h2>
          <p className="text-sm leading-relaxed opacity-80">
            True, False, Misleading or Unverified, with confidence, sources and the full model trace.
          </p>
        </li>
      </ol>

      <div className="mt-16 grid gap-10 md:grid-cols-2">
        <section>
          <h2 className="font-serif text-2xl tracking-tight">Quotes are checked by code</h2>
          <p className="mt-3 leading-relaxed text-muted">
            Language models sometimes invent quotes. So the model must copy a sentence of at least
            six words from the source exactly, and Verity then searches the page text for it,
            ignoring only case, spacing and punctuation. If it isn't there, the quote is thrown out
            and never reaches the jury. Discarded and irrelevant sources stay visible, collapsed
            under each claim, so you can see what was set aside.
          </p>
        </section>
        <section>
          <h2 className="font-serif text-2xl tracking-tight">Two models, judged independently</h2>
          <p className="mt-3 leading-relaxed text-muted">
            The fast model drafts a verdict. At the same time,{" "}
            <span className="break-words font-medium text-ink">{health ? health.models.judge : "the judge model"}</span>{" "}
            reads the same evidence without seeing that draft. If they agree, you get their shared
            verdict. If they don't, Verity runs extra searches for what's missing and the judge
            makes a final ruling. Every claim shows both opinions and whether they agreed. If there
            is no verified evidence at all, the claim is marked Unverified in code, without a vote.
          </p>
        </section>
      </div>

      <section className="mt-16">
        <h2 className="font-serif text-2xl tracking-tight">Reading a result</h2>
        <dl className="mt-5 grid gap-x-10 gap-y-5 md:grid-cols-2">
          {READING.map((r) => (
            <div key={r.term}>
              <dt className="text-sm font-semibold">{r.term}</dt>
              <dd className="mt-1 text-sm leading-relaxed text-muted">{r.body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-16 rounded-2xl border border-line bg-surface p-5 sm:p-6">
        <h2 className="font-serif text-2xl tracking-tight">Limits</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">
          <li>Verity only knows what a web search returns right now. Very recent or niche topics may have thin coverage.</li>
          <li>A verified quote is really on the page, but the page itself can still be wrong. That's why every quote links to its source.</li>
          <li>Models can misread context. For anything that matters, open the cited sources and judge for yourself.</li>
          <li>Each check covers up to three claims. Split longer texts, or check single statements on their own.</li>
        </ul>
      </section>

      <p className="mt-14 text-sm text-muted">
        Every AI call is shown in the model trace on each result: model, tokens, time and cost.{" "}
        <Link to="/" className="font-medium text-ink underline decoration-accent underline-offset-4">
          Try a check →
        </Link>
      </p>
    </article>
  );
}
