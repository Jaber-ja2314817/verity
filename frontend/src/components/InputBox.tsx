import { useId, useRef, type FormEvent, type KeyboardEvent } from "react";

export const MAX_TEXT = 5000;
export const MIN_TEXT = 20;
export const MAX_URL = 2000;

export type InputMode = "text" | "url";

/** Mirrors backend validate_check_request. Returns a message, or null when valid. */
export function validateInput(mode: InputMode, text: string, url: string): string | null {
  if (mode === "text") {
    const t = text.trim();
    if (t.length < MIN_TEXT) return `Paste at least ${MIN_TEXT} characters.`;
    if (t.length > MAX_TEXT) return `Text is too long (maximum ${MAX_TEXT.toLocaleString()} characters).`;
    return null;
  }
  const u = url.trim();
  if (!/^https?:\/\//i.test(u)) return "Enter a link starting with http:// or https://";
  if (u.length > MAX_URL) return `URL is too long (maximum ${MAX_URL} characters).`;
  return null;
}

interface Props {
  mode: InputMode;
  onModeChange: (m: InputMode) => void;
  text: string;
  onTextChange: (t: string) => void;
  url: string;
  onUrlChange: (u: string) => void;
  submitting: boolean;
  error: string | null;
  onSubmit: () => void;
}

const TABS: { id: InputMode; label: string }[] = [
  { id: "text", label: "Text" },
  { id: "url", label: "URL" },
];

export default function InputBox(p: Props) {
  const base = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const invalid = validateInput(p.mode, p.text, p.url);
  const len = p.text.trim().length;
  const nearLimit = len > MAX_TEXT * 0.9;
  const over = len > MAX_TEXT;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!invalid && !p.submitting) p.onSubmit();
  }

  function onTabKey(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = (i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length;
    p.onModeChange(TABS[next].id);
    tabRefs.current[next]?.focus();
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-line bg-surface p-3 shadow-[0_1px_0_rgba(0,0,0,0.02),0_12px_32px_-16px_rgba(0,0,0,0.12)] sm:p-4"
    >
      <div role="tablist" aria-label="Input type" className="mb-3 inline-flex rounded-lg bg-paper p-1">
        {TABS.map((t, i) => {
          const selected = p.mode === t.id;
          return (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${t.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => p.onModeChange(t.id)}
              onKeyDown={(e) => onTabKey(e, i)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${
                selected ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {p.mode === "text" ? (
        <div role="tabpanel" id={`${base}-panel-text`} aria-labelledby={`${base}-tab-text`}>
          <label htmlFor={`${base}-text`} className="sr-only">
            Text to fact-check
          </label>
          <textarea
            id={`${base}-text`}
            value={p.text}
            onChange={(e) => p.onTextChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
            }}
            rows={7}
            placeholder="Paste a post, a paragraph or a forwarded message…"
            className="block w-full resize-y rounded-lg border border-transparent bg-transparent px-2 py-1 font-serif text-[17px] leading-relaxed text-ink placeholder:text-muted/70 focus:border-line focus:outline-none"
          />
          <div className="mt-1 flex justify-end px-2 text-xs tabular-nums" aria-live="polite">
            <span className={over ? "font-semibold text-v-false" : nearLimit ? "text-v-misleading" : "text-muted"}>
              {len.toLocaleString()} / {MAX_TEXT.toLocaleString()}
            </span>
          </div>
        </div>
      ) : (
        <div role="tabpanel" id={`${base}-panel-url`} aria-labelledby={`${base}-tab-url`}>
          <label htmlFor={`${base}-url`} className="sr-only">
            Article URL
          </label>
          <input
            id={`${base}-url`}
            type="url"
            inputMode="url"
            value={p.url}
            onChange={(e) => p.onUrlChange(e.target.value)}
            placeholder="https://example.com/article"
            className="block w-full rounded-lg border border-line bg-paper px-3 py-3 text-base text-ink placeholder:text-muted/70 focus:border-accent focus:outline-none"
          />
          <p className="mt-2 px-1 text-xs text-muted">We read the article's text, then check its claims.</p>
        </div>
      )}

      <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p role="alert" className="min-h-[1.25rem] text-sm text-v-false">
          {p.error}
        </p>
        <button
          type="submit"
          disabled={!!invalid || p.submitting}
          title={invalid ?? undefined}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-7 py-3.5 text-base font-semibold text-paper transition hover:bg-accent-ink disabled:cursor-not-allowed disabled:opacity-40 sm:w-auto"
        >
          {p.submitting && (
            <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-paper/40 border-t-paper" />
          )}
          {p.submitting ? "Starting…" : "Check it"}
        </button>
      </div>
    </form>
  );
}
