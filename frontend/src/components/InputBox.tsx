import { useId, useState, type FormEvent } from "react";
import { MAX_CLAIMS, phrasingHint } from "../lib/claims";

export const MAX_TEXT = 5000;
export const MIN_TEXT = 20;
export const MAX_URL = 2000;

export type InputMode = "text" | "url";

/** A lone http(s) link is checked as an article; anything else is checked as text. */
export function detectMode(value: string): InputMode {
  return /^https?:\/\/\S+$/i.test(value.trim()) ? "url" : "text";
}

/** Mirrors backend validate_check_request. Returns a message, or null when valid. */
export function validateInput(value: string): string | null {
  const v = value.trim();
  if (detectMode(v) === "url") {
    if (v.length > MAX_URL) return `URL is too long (maximum ${MAX_URL} characters).`;
    return null;
  }
  if (v.length < MIN_TEXT) return `Write at least ${MIN_TEXT} characters.`;
  if (v.length > MAX_TEXT) return `Text is too long (maximum ${MAX_TEXT.toLocaleString()} characters).`;
  return null;
}

const TIPS: { good: string; bad?: string; why: string }[] = [
  {
    good: "Coffee stunts children's growth.",
    bad: "Is coffee bad for kids?",
    why: "State the claim. Yes/no questions work too; open questions (who, what, how many) don't.",
  },
  {
    good: "The Eiffel Tower was completed in 1889.",
    bad: "The tower is really old.",
    why: "Be specific: names, places, dates and numbers make a claim checkable.",
  },
  {
    good: "Unemployment in Spain fell below 12% in 2024.",
    bad: "Spain's economy will boom next year.",
    why: "Facts about the past and present can be checked; opinions and predictions can't.",
  },
];

function Tips() {
  return (
    <details className="group border-t border-line px-6 py-3">
      <summary className="cursor-pointer list-none text-xs text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
        <span aria-hidden className="mr-1.5 inline-block transition-transform group-open:rotate-90">›</span>
        How to phrase a checkable claim
      </summary>
      <ul className="mt-3 space-y-3 text-sm">
        {TIPS.map((t) => (
          <li key={t.good}>
            <p className="text-xs text-muted">{t.why}</p>
            <p className="mt-1 font-serif">
              <span className="text-accent-ink">Checkable:</span> “{t.good}”
              {t.bad && (
                <>
                  <br />
                  <span className="text-muted">Harder: “{t.bad}”</span>
                </>
              )}
            </p>
          </li>
        ))}
        <li className="text-xs text-muted">
          You can paste a paragraph (up to {MAX_TEXT.toLocaleString()} characters; the{" "}
          {MAX_CLAIMS} most important claims are checked) or a link to an article.
        </li>
      </ul>
    </details>
  );
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
  autoFocus?: boolean;
}

export default function InputBox(p: Props) {
  const id = useId();
  const noteId = `${id}-note`;
  const [tried, setTried] = useState(false);
  const invalid = validateInput(p.value);
  const mode = detectMode(p.value);
  const len = p.value.trim().length;
  const over = mode === "text" && len > MAX_TEXT;
  const hint = phrasingHint(p.value);

  function submit(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    if (!invalid && !p.submitting) p.onSubmit();
  }

  let note: { text: string; tone: "muted" | "error" | "hint" } = {
    text: "One specific claim is a good place to start.",
    tone: "muted",
  };
  if (p.error) note = { text: p.error, tone: "error" };
  else if (over || (tried && invalid)) note = { text: invalid ?? "", tone: "error" };
  else if (len > 0 && mode === "url") note = { text: "We'll read the article, then check its claims.", tone: "muted" };
  else if (hint) note = { text: hint, tone: "hint" };

  const showCount = mode === "text" && len > MAX_TEXT * 0.8;

  return (
    <form onSubmit={submit} className="border border-rule/80 bg-surface">
      <div className="px-4 pt-5 sm:px-6 sm:pt-6">
        <label htmlFor={id} className="eyebrow block text-muted">
          What would you like to investigate?
        </label>
        <textarea
          id={id}
          value={p.value}
          onChange={(e) => p.onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
          }}
          rows={3}
          autoFocus={p.autoFocus}
          aria-describedby={noteId}
          aria-invalid={note.tone === "error" || undefined}
          placeholder="A statement you read, heard, or want to question… or paste a link"
          className="mt-3 block min-h-24 w-full resize-y bg-transparent pb-4 text-lg leading-relaxed text-ink placeholder:text-muted focus:outline-none sm:text-xl"
        />
        {showCount && (
          <p className={`pb-2 text-right text-xs tabular-nums ${over ? "text-v-false" : "text-muted"}`}>
            {len.toLocaleString()} / {MAX_TEXT.toLocaleString()}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-4 border-t border-line px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p
          id={noteId}
          role={note.tone === "error" ? "alert" : undefined}
          aria-live="polite"
          className={`text-xs ${note.tone === "error" ? "text-v-false" : note.tone === "hint" ? "text-v-misleading" : "text-muted"}`}
        >
          {note.text}
        </p>
        <button
          type="submit"
          disabled={p.submitting}
          className="inline-flex shrink-0 items-center justify-center gap-2 bg-accent px-5 py-3 text-[15px] text-on-accent transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:bg-accent"
        >
          {p.submitting && (
            <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-on-accent/30 border-t-on-accent motion-reduce:animate-none" />
          )}
          {p.submitting ? "Opening the file…" : "Investigate claim"}
          {!p.submitting && <span aria-hidden>↗</span>}
        </button>
      </div>
      <Tips />
    </form>
  );
}
