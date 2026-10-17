import { useId, useState, type FormEvent } from "react";

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

interface Props {
  value: string;
  onChange: (v: string) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
}

export default function InputBox(p: Props) {
  const id = useId();
  const [tried, setTried] = useState(false);
  const invalid = validateInput(p.value);
  const len = p.value.trim().length;
  const over = detectMode(p.value) === "text" && len > MAX_TEXT;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    if (!invalid && !p.submitting) p.onSubmit();
  }

  let note: { text: string; tone: "muted" | "error" } = {
    text: "One specific claim is a good place to start.",
    tone: "muted",
  };
  if (p.error) note = { text: p.error, tone: "error" };
  else if (over || (tried && invalid)) note = { text: invalid ?? "", tone: "error" };
  else if (len > 0 && detectMode(p.value) === "url") note = { text: "We'll read the article, then check its claims.", tone: "muted" };

  return (
    <form onSubmit={submit} className="border border-rule/80 bg-surface">
      <div className="px-6 pt-6">
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
          placeholder="A statement you read, heard, or want to question…"
          className="mt-3 block min-h-24 w-full resize-y bg-transparent pb-4 text-xl leading-relaxed text-ink placeholder:text-muted focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-4 border-t border-line px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p
          role={note.tone === "error" ? "alert" : undefined}
          aria-live="polite"
          className={`text-xs ${note.tone === "error" ? "text-v-false" : "text-muted"}`}
        >
          {note.text}
        </p>
        <button
          type="submit"
          disabled={p.submitting}
          className="inline-flex shrink-0 items-center justify-center gap-2 bg-accent px-5 py-3 text-[15px] text-on-accent transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:bg-accent"
        >
          {p.submitting && (
            <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-on-accent/30 border-t-on-accent" />
          )}
          {p.submitting ? "Opening the file…" : "Investigate claim"}
          {!p.submitting && <span aria-hidden>↗</span>}
        </button>
      </div>
    </form>
  );
}
