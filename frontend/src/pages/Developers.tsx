import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import CodeBlock from "../components/CodeBlock";
import { checkExample, usageExample } from "../lib/developers";
import { useTitle } from "../lib/useTitle";

const RESULT = `{
  "id": "k3T9xQ1aB2c",
  "status": "done",
  "claims": [
    {
      "id": 1,
      "text": "The Eiffel Tower was completed in 1889.",
      "verdict": "TRUE",
      "confidence": 96,
      "explanation": "...",
      "models_agreed": true,
      "search": "web",
      "sources": [
        {
          "url": "https://...",
          "domain": "...",
          "published_date": "2025-05-01",
          "reliability": "high",
          "stance": "supports",
          "quote": "Sentence copied word for word from the page.",
          "cited": true
        }
      ]
    }
  ]
}`;

const ERRORS: [string, string][] = [
  ["400", "Invalid body: text too short or too long, text and url together, or an unknown mode."],
  ["401", "Missing, wrong or revoked API key."],
  ["404", "Unknown check id, or a check that belongs to another key."],
  ["429", "Per-minute limit or daily quota reached. Retry-After says how many seconds to wait."],
  ["503", "The service's daily cap is reached. It resets at 00:00 UTC."],
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="font-serif text-2xl font-light tracking-tight">{title}</h2>
      <div className="mt-4 space-y-4 text-[15px] leading-relaxed">{children}</div>
    </section>
  );
}

export default function Developers() {
  useTitle("Verity API");
  const origin = window.location.origin;
  return (
    <article className="max-w-[44rem]">
      <p className="eyebrow text-accent">For developers</p>
      <h1 className="mt-4 font-serif text-[2.35rem] font-light leading-[1.12] tracking-[-0.02em]">
        Put Verity inside your app.
      </h1>
      <p className="mt-5 text-base leading-relaxed text-muted">
        Send a claim, a headline or an article link. Get back a verdict, a confidence score and the
        sources, with every quote verified against the page. Keys are issued by the Verity team.
      </p>

      <Section title="Quick start">
        <p>
          Replace <code className="font-mono text-sm">vrt_YOUR_KEY</code> with your key.{" "}
          <code className="font-mono text-sm">wait=true</code> holds the request until the verdict is
          ready, usually 10 to 30 seconds.
        </p>
        <CodeBlock label="check example" code={checkExample(origin, "The Eiffel Tower was completed in 1889.")} />
        <p className="text-muted">Without wait=true you get an id straight away and poll for the result:</p>
        <CodeBlock label="poll example" code={`curl ${origin}/v1/checks/CHECK_ID \\\n  -H "Authorization: Bearer vrt_YOUR_KEY"`} />
      </Section>

      <Section title="Send">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <code className="font-mono text-sm">text</code> or <code className="font-mono text-sm">url</code>, not
            both. Text can be a claim, a headline or a pasted article (up to 5,000 characters).
          </li>
          <li>
            <code className="font-mono text-sm">mode</code>: <strong>auto</strong> (news search for recent
            events, web for settled facts), <strong>news</strong> (news first) or <strong>web</strong>.
          </li>
        </ul>
      </Section>

      <Section title="Get back">
        <CodeBlock label="example result" code={RESULT} />
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <code className="font-mono text-sm">verdict</code> is TRUE, FALSE, MISLEADING or UNVERIFIED.{" "}
            <strong>UNVERIFIED means there wasn't enough reliable evidence. It does not mean false.</strong>
          </li>
          <li>
            <code className="font-mono text-sm">confidence</code> is 0 to 100. Each{" "}
            <code className="font-mono text-sm">quote</code> is verified to appear in its source.
          </li>
          <li>
            <code className="font-mono text-sm">models_agreed</code> is false when the two independent models
            disagreed and a debate round decided.
          </li>
        </ul>
      </Section>

      <Section title="Limits and errors">
        <p>
          Every key has a per-minute rate limit and a daily quota. See yours with:
        </p>
        <CodeBlock label="usage example" code={usageExample(origin)} />
        <table className="w-full border-collapse text-sm">
          <tbody>
            {ERRORS.map(([code, text]) => (
              <tr key={code} className="border-t border-line align-top">
                <td className="w-14 py-2 pr-3 font-mono text-muted">{code}</td>
                <td className="py-2">{text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Try it in the browser">
        <p>
          The interactive docs let you send real requests: open{" "}
          <a href="/v1/docs" className="border-b border-muted hover:border-accent hover:text-accent">
            /v1/docs
          </a>
          , click <strong>Authorize</strong>, paste your key, then use <strong>Try it out</strong>.
        </p>
        <p className="text-muted">
          Back to the <Link to="/" className="border-b border-muted hover:border-accent hover:text-accent">fact-checker</Link>.
        </p>
      </Section>
    </article>
  );
}
