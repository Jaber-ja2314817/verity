import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import type { CheckRecord } from "../types";
import { followLive, LOST_MESSAGE, parseSse, readEvents, startCheck } from "./liveChecks";
import type { CheckAction } from "./useCheck";

const record = (over: Partial<CheckRecord> = {}): CheckRecord => ({
  id: "abc", created_at: "2026-10-14T12:00:00Z", status: "queued", input_type: "text",
  input_preview: "text", language: null, claims: [], skipped_claims: [], trace: [], totals: {},
  error: null, ...over,
});

const sse = (...events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

/** A byte stream that delivers the given chunks, then closes (or stays open when keepOpen). */
function streamOf(chunks: string[], keepOpen = false): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(bytes.encode(c));
      if (!keepOpen) controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>, stallMs?: number) {
  const actions: CheckAction[] = [];
  await readEvents(stream, (a) => actions.push(a), stallMs);
  return actions;
}

afterEach(() => vi.restoreAllMocks());

describe("parseSse", () => {
  it("returns whole messages and keeps the unfinished tail", () => {
    const { messages, rest } = parseSse('data: {"type":"ping"}\n\ndata: {"type":"do');
    expect(messages).toEqual([{ type: "ping" }]);
    expect(rest).toBe('data: {"type":"do');
  });

  it("skips comments and malformed data", () => {
    expect(parseSse(": hi\n\ndata: nope\n\ndata: {\"a\":1}\n\n").messages).toEqual([{ a: 1 }]);
  });
});

describe("readEvents", () => {
  it("passes events split across chunks and stops at done", async () => {
    const body = sse({ type: "snapshot", record: record() }, { type: "ping" }, { type: "done", totals: {} });
    const actions = await collect(streamOf([body.slice(0, 25), body.slice(25)]));
    expect(actions.map((a) => a.type)).toEqual(["snapshot", "done"]);
  });

  it("ends with an error when the stream closes early", async () => {
    const actions = await collect(streamOf([sse({ type: "snapshot", record: record() })]));
    expect(actions.at(-1)).toEqual({ type: "error", message: LOST_MESSAGE });
  });

  it("ends with an error when the stream stalls", async () => {
    const actions = await collect(streamOf([sse({ type: "snapshot", record: record() })], true), 20);
    expect(actions.map((a) => a.type)).toEqual(["snapshot", "error"]);
  });
});

describe("startCheck", () => {
  it("resolves with the id and replays events to followers", async () => {
    const final = record({ id: "x1", status: "done" });
    vi.spyOn(api, "startCheck").mockResolvedValue(
      streamOf([sse({ type: "snapshot", record: record({ id: "x1" }) }, { type: "record", record: final }, { type: "done", totals: {} })]),
    );
    expect(await startCheck({ text: "t" })).toBe("x1");
    await new Promise((r) => setTimeout(r, 0));
    const seen: string[] = [];
    const stop = followLive("x1", (a) => seen.push(a.type));
    expect(seen).toEqual(["snapshot", "record", "done"]);
    stop?.();
    expect(followLive("unknown", () => {})).toBeNull();
  });

  it("rejects when the stream ends before the check is accepted", async () => {
    vi.spyOn(api, "startCheck").mockResolvedValue(streamOf([]));
    await expect(startCheck({ text: "t" })).rejects.toBeInstanceOf(ApiError);
  });
});
