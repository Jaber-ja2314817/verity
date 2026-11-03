import { useCallback, useEffect, useState, type FormEvent } from "react";
import { adminApi, ApiError } from "../api";
import { copy } from "../lib/clipboard";
import { adminErrorMessage } from "../lib/developers";
import { useTitle } from "../lib/useTitle";
import type { AdminKey, CreatedKey } from "../types";

const STORE = "verity-admin-secret";

// sessionStorage, not localStorage: the secret disappears when the tab closes.
function readSecret(): string {
  try {
    return sessionStorage.getItem(STORE) ?? "";
  } catch {
    return "";
  }
}
function writeSecret(value: string) {
  try {
    if (value) sessionStorage.setItem(STORE, value);
    else sessionStorage.removeItem(STORE);
  } catch {
    /* storage blocked: the page still works until it is reloaded */
  }
}

function problem(e: unknown): { status: number; message: string } {
  if (e instanceof ApiError) return { status: e.status, message: adminErrorMessage(e.status, e.message) };
  return { status: 0, message: "Something went wrong. Try again." };
}

const field =
  "mt-1 block w-full border border-line bg-frame px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none";
const button =
  "inline-flex items-center justify-center bg-accent px-5 py-2.5 text-sm text-on-accent transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-60";
const ghost = "border border-line px-3 py-1.5 text-xs text-muted transition hover:border-ink hover:text-ink";

function day(iso: string): string {
  return iso.slice(0, 10);
}

export default function Admin() {
  useTitle("Admin");
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex";
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);

  const [secret, setSecret] = useState(readSecret);
  const [input, setInput] = useState("");
  const [keys, setKeys] = useState<AdminKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [rate, setRate] = useState("");
  const [quota, setQuota] = useState("");

  const signOut = useCallback(() => {
    writeSecret("");
    setSecret("");
    setKeys(null);
    setCreated(null);
  }, []);

  const load = useCallback(
    async (s: string) => {
      try {
        setKeys(await adminApi.list(s));
        setError(null);
        return true;
      } catch (e) {
        const p = problem(e);
        setError(p.message);
        if (p.status === 401) signOut(); // stored secret is no longer valid
        return false;
      }
    },
    [signOut],
  );

  useEffect(() => {
    if (secret && keys === null) void load(secret);
  }, [secret, keys, load]);

  async function signIn(e: FormEvent) {
    e.preventDefault();
    const s = input.trim();
    if (!s || busy) return;
    setBusy(true);
    if (await load(s)) {
      writeSecret(s);
      setSecret(s);
      setInput("");
    }
    setBusy(false);
  }

  async function createKey(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: name.trim(),
        ...(rate ? { rate_per_minute: Number(rate) } : {}),
        ...(quota ? { daily_quota: Number(quota) } : {}),
      };
      setCreated(await adminApi.create(secret, body));
      setCopied(false);
      setName("");
      setRate("");
      setQuota("");
      await load(secret);
    } catch (err) {
      setError(problem(err).message);
    }
    setBusy(false);
  }

  async function revoke(id: string) {
    if (confirmId !== id) {
      setConfirmId(id);
      return;
    }
    setBusy(true);
    setConfirmId(null);
    try {
      await adminApi.revoke(secret, id);
      await load(secret);
    } catch (err) {
      setError(problem(err).message);
    }
    setBusy(false);
  }

  if (!secret) {
    return (
      <section className="max-w-md">
        <p className="eyebrow text-accent">Admin</p>
        <h1 className="mt-4 font-serif text-3xl font-light tracking-tight">API keys</h1>
        <form onSubmit={signIn} className="mt-6">
          <label className="eyebrow text-muted" htmlFor="admin-secret">
            Admin secret
          </label>
          <input
            id="admin-secret"
            type="password"
            autoComplete="off"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className={field}
          />
          {error && (
            <p role="alert" className="mt-3 text-sm text-v-false">
              {error}
            </p>
          )}
          <button type="submit" disabled={busy || !input.trim()} className={`${button} mt-4`}>
            {busy ? "Checking…" : "Sign in"}
          </button>
          <p className="mt-4 text-xs text-muted">
            This is the ADMIN_SECRET from the server's .env. It is kept in this tab only and sent just to the
            key endpoints.
          </p>
        </form>
      </section>
    );
  }

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="eyebrow text-accent">Admin</p>
          <h1 className="mt-4 font-serif text-3xl font-light tracking-tight">API keys</h1>
        </div>
        <button type="button" onClick={signOut} className={ghost}>
          Sign out
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-v-false">
          {error}
        </p>
      )}

      {created && (
        <div role="status" className="mt-6 border border-accent/60 bg-surface p-4">
          <p className="text-sm">
            <strong>Key created for “{created.name}”.</strong> Copy it now. It is shown only once and cannot be
            recovered.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <code className="break-all bg-frame px-3 py-2 font-mono text-xs">{created.key}</code>
            <button
              type="button"
              className={ghost}
              onClick={async () => setCopied(await copy(created.key))}
            >
              {copied ? "Copied" : "Copy key"}
            </button>
            <button type="button" className={ghost} onClick={() => setCreated(null)}>
              I saved it
            </button>
          </div>
        </div>
      )}

      <form onSubmit={createKey} className="mt-8 border border-rule/80 bg-surface p-4 sm:p-6">
        <h2 className="font-serif text-xl font-light">Create a key</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-[2fr_1fr_1fr]">
          <label className="text-xs text-muted">
            Name (who it is for)
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className={field} />
          </label>
          <label className="text-xs text-muted">
            Per minute
            <input
              type="number"
              min={1}
              max={600}
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              placeholder="default"
              className={field}
            />
          </label>
          <label className="text-xs text-muted">
            Per day
            <input
              type="number"
              min={1}
              max={100000}
              value={quota}
              onChange={(e) => setQuota(e.target.value)}
              placeholder="default"
              className={field}
            />
          </label>
        </div>
        <button type="submit" disabled={busy || !name.trim()} className={`${button} mt-4`}>
          Create key
        </button>
      </form>

      <div className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="eyebrow text-left text-muted">
              <th className="py-2 pr-3 font-normal">Name</th>
              <th className="py-2 pr-3 font-normal">Key</th>
              <th className="py-2 pr-3 font-normal">Per min</th>
              <th className="py-2 pr-3 font-normal">Today / day</th>
              <th className="py-2 pr-3 font-normal">Created</th>
              <th className="py-2 font-normal" />
            </tr>
          </thead>
          <tbody>
            {keys === null && (
              <tr>
                <td colSpan={6} className="py-4 text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {keys?.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-muted">
                  No keys yet.
                </td>
              </tr>
            )}
            {keys?.map((k) => (
              <tr key={k.id} className={`border-t border-line ${k.revoked_at ? "text-muted" : ""}`}>
                <td className="py-2 pr-3">{k.name}</td>
                <td className="py-2 pr-3 font-mono text-xs">{k.prefix}…</td>
                <td className="py-2 pr-3 tabular-nums">{k.rate_per_minute}</td>
                <td className="py-2 pr-3 tabular-nums">
                  {k.used_today ?? 0} / {k.daily_quota}
                </td>
                <td className="py-2 pr-3 tabular-nums">{day(k.created_at)}</td>
                <td className="py-2 text-right no-underline">
                  {k.revoked_at ? (
                    <span className="text-xs">revoked {day(k.revoked_at)}</span>
                  ) : (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => revoke(k.id)}
                      className={`${ghost} ${confirmId === k.id ? "border-v-false text-v-false" : ""}`}
                    >
                      {confirmId === k.id ? "Click again to revoke" : "Revoke"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
