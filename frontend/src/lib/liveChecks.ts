import { api, ApiError } from "../api";
import type { CheckRequest } from "../types";
import type { CheckAction } from "./useCheck";

// Checks started in this tab run inside their POST request (see /api/checks/stream), and their
// events are kept here for the session. On a serverless host a later request may reach an
// instance that never saw the check, so this stream is the source of truth while it runs.

export const LOST_MESSAGE =
  "The connection to Verity dropped before this check finished. Please run it again.";
// The server sends a ping every 5 s, so this much silence means the stream is stuck.
const STALL_MS = 30_000;

type Listener = (action: CheckAction) => void;

interface LiveCheck {
  actions: CheckAction[];
  listeners: Set<Listener>;
}

const live = new Map<string, LiveCheck>();

/** Split server-sent-event text into the parsed `data:` messages and the unfinished tail. */
export function parseSse(buffer: string): { messages: unknown[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? "";
  const messages: unknown[] = [];
  for (const part of parts) {
    const data = part
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue;
    try {
      messages.push(JSON.parse(data));
    } catch {
      /* malformed message */
    }
  }
  return { messages, rest };
}

const isEnd = (a: CheckAction) => a.type === "done" || a.type === "error";

/** Pass each event of a check stream to onAction (pings dropped) until it ends. If the stream
 * breaks, stalls or closes before a done/error event, finish with an error action. */
export async function readEvents(
  stream: ReadableStream<Uint8Array>,
  onAction: Listener,
  stallMs: number = STALL_MS,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let ended = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(() => void reader.cancel().catch(() => {}), stallMs);
  };
  try {
    arm();
    while (!ended) {
      const { value, done } = await reader.read();
      if (done) break;
      arm();
      const { messages, rest } = parseSse(buffer + decoder.decode(value, { stream: true }));
      buffer = rest;
      for (const action of messages as CheckAction[]) {
        if (action.type === "ping") continue;
        onAction(action);
        if (isEnd(action)) {
          ended = true;
          break;
        }
      }
    }
  } catch {
    /* network error, or cancelled after a stall */
  } finally {
    clearTimeout(timer);
  }
  if (ended) void reader.cancel().catch(() => {});
  else onAction({ type: "error", message: LOST_MESSAGE });
}

/** Start a check and resolve with its id once the server accepts it; its events keep arriving
 * in the background for followLive(). Refusals (bad input, rate limits) reject with ApiError. */
export async function startCheck(body: CheckRequest): Promise<string> {
  const stream = await api.startCheck(body);
  return new Promise<string>((resolve, reject) => {
    let entry: LiveCheck | null = null;
    let failed = false;
    void readEvents(stream, (action) => {
      if (failed) return;
      if (!entry) {
        if (action.type !== "snapshot") {
          failed = true;
          reject(new ApiError(action.type === "error" ? action.message : LOST_MESSAGE, 0));
          return;
        }
        entry = { actions: [], listeners: new Set() };
        live.set(action.record.id, entry);
        resolve(action.record.id);
      }
      entry.actions.push(action);
      for (const listener of entry.listeners) listener(action);
    });
  });
}

/** Replay a check started in this tab and follow its new events. Returns an unsubscribe
 * function, or null when this tab did not start the check. */
export function followLive(id: string, listener: Listener): (() => void) | null {
  const entry = live.get(id);
  if (!entry) return null;
  for (const action of entry.actions) listener(action);
  entry.listeners.add(listener);
  return () => entry.listeners.delete(listener);
}
