import { useEffect, useReducer } from "react";
import { api, ApiError } from "../api";
import { followLive } from "./liveChecks";
import type {
  CheckEvent,
  CheckRecord,
  Label,
  Totals,
  TraceEntry,
  Verdict,
} from "../types";

export type ClaimStage = "planning" | "searching" | "assessing" | "jury" | "debating" | "done";

export interface ClaimProgress {
  id: number;
  text: string;
  stage: ClaimStage;
  queries?: string[];
  sourceCount?: number;
  domains?: string[];
  verified?: number;
  discarded?: number;
  draftLabel?: Label;
  juryLabel?: Label;
  agreed?: boolean;
  debated?: boolean;
  rechecked?: boolean; // both models said UNVERIFIED; searching again
  final?: Verdict;
}

export interface Progress {
  ingested: boolean;
  title?: string;
  chars?: number;
  claimsFound: boolean;
  claims: ClaimProgress[];
  skipped: number;
  trace: TraceEntry[]; // live model calls (record.trace is only filled at the end)
  totals?: Totals;
  finished: boolean;
  message?: string; // error message from the stream
}

export interface CheckState {
  record: CheckRecord | null;
  progress: Progress;
}

export type CheckAction = CheckEvent | { type: "record"; record: CheckRecord };

export const initialState: CheckState = {
  record: null,
  progress: {
    ingested: false,
    claimsFound: false,
    claims: [],
    skipped: 0,
    trace: [],
    finished: false,
  },
};

const STAGE_ORDER: ClaimStage[] = ["planning", "searching", "assessing", "jury", "debating", "done"];

function updateClaim(
  p: Progress,
  id: number,
  patch: Partial<ClaimProgress>,
  stage?: ClaimStage,
): Progress {
  let found = false;
  const claims = p.claims.map((c) => {
    if (c.id !== id) return c;
    found = true;
    // Never move a claim backwards (events can arrive after a fuller snapshot).
    const next =
      stage && STAGE_ORDER.indexOf(stage) > STAGE_ORDER.indexOf(c.stage) ? stage : c.stage;
    return { ...c, ...patch, stage: next };
  });
  if (!found) claims.push({ id, text: "", stage: stage ?? "planning", ...patch });
  claims.sort((a, b) => a.id - b.id);
  return { ...p, claims, claimsFound: true, ingested: true };
}

/** Merge a full record (snapshot, fetch or poll) into the progress state. */
function fromRecord(p: Progress, record: CheckRecord): Progress {
  let next: Progress = { ...p };
  if (record.language !== null || record.claims.length || record.skipped_claims.length) {
    next.ingested = true;
    next.claimsFound = true;
  }
  if (record.status === "done" || record.status === "error") {
    next.ingested = true;
    next.finished = true;
    if (record.error) next.message = record.error;
    if (record.totals && Object.keys(record.totals).length) next.totals = record.totals;
  }
  if (record.skipped_claims.length) next.skipped = record.skipped_claims.length;
  for (const c of record.claims) {
    next = updateClaim(
      next,
      c.id,
      {
        text: c.text,
        final: c.result.final,
        agreed: c.result.agreed,
        debated: c.result.debated,
        rechecked: c.result.rechecked ?? false,
        draftLabel: c.result.draft.label,
        juryLabel: c.result.jury.label,
      },
      "done",
    );
  }
  return next;
}

function sameCall(a: TraceEntry, b: TraceEntry): boolean {
  return (
    a.step === b.step &&
    a.model === b.model &&
    a.input_tokens === b.input_tokens &&
    a.output_tokens === b.output_tokens &&
    a.latency_s === b.latency_s &&
    a.cost_usd === b.cost_usd
  );
}

export function checkReducer(state: CheckState, action: CheckAction): CheckState {
  const p = state.progress;
  switch (action.type) {
    case "snapshot":
      // Every (re)connection starts with a snapshot followed by a replay of the full event
      // history, so rebuild progress from scratch instead of merging (no duplicated trace rows).
      return { record: action.record, progress: fromRecord(initialState.progress, action.record) };
    case "record":
      // A polled record: merge (polling has no replay).
      return { record: action.record, progress: fromRecord(p, action.record) };
    case "ping":
      return state;
    case "ingest_done":
      return { ...state, progress: { ...p, ingested: true, title: action.title, chars: action.chars } };
    case "claims_found": {
      let next: Progress = { ...p, ingested: true, claimsFound: true, skipped: action.skipped };
      for (const c of action.claims) next = updateClaim(next, c.id, { text: c.text }, "planning");
      return { ...state, progress: next };
    }
    case "queries_planned":
      return {
        ...state,
        progress: updateClaim(p, action.claim_id, { queries: action.queries }, "searching"),
      };
    case "sources_found":
      return {
        ...state,
        progress: updateClaim(
          p,
          action.claim_id,
          { sourceCount: action.count, domains: action.domains },
          "assessing",
        ),
      };
    case "evidence_ready":
      return {
        ...state,
        progress: updateClaim(
          p,
          action.claim_id,
          { verified: action.verified, discarded: action.discarded },
          "jury",
        ),
      };
    case "verdicts_drafted":
      return {
        ...state,
        progress: updateClaim(
          p,
          action.claim_id,
          { draftLabel: action.draft_label, juryLabel: action.jury_label, agreed: action.agreed },
          "jury",
        ),
      };
    case "debate_started":
      return {
        ...state,
        progress: updateClaim(p, action.claim_id, { debated: true }, "debating"),
      };
    case "recheck_started":
      return {
        ...state,
        progress: updateClaim(p, action.claim_id, { debated: true, rechecked: true }, "debating"),
      };
    case "claim_done":
      return {
        ...state,
        progress: updateClaim(
          p,
          action.claim_id,
          {
            final: action.final,
            agreed: action.agreed,
            debated: action.debated,
            ...(action.rechecked !== undefined && { rechecked: action.rechecked }),
          },
          "done",
        ),
      };
    case "model_call": {
      const { type: _t, ...entry } = action;
      if (p.trace.some((e) => sameCall(e, entry))) return state; // replayed event
      return { ...state, progress: { ...p, trace: [...p.trace, entry] } };
    }
    case "done":
      return { ...state, progress: { ...p, finished: true, totals: action.totals } };
    case "error":
      return { ...state, progress: { ...p, finished: true, message: action.message } };
    default:
      return state;
  }
}

/** Index into STEPS for the overall stepper. */
export const STEPS = [
  "Reading",
  "Finding claims",
  "Searching",
  "Checking evidence",
  "Jury",
  "Done",
] as const;

export function currentStep(state: CheckState): number {
  const { record, progress } = state;
  if (record?.status === "done" || (progress.finished && !progress.message)) return 5;
  if (!progress.ingested) return 0;
  if (!progress.claimsFound) return 1;
  const open = progress.claims.filter((c) => c.stage !== "done");
  if (open.length === 0) return progress.claims.length ? 4 : 1;
  const earliest = Math.min(...open.map((c) => STAGE_ORDER.indexOf(c.stage)));
  const stage = STAGE_ORDER[earliest];
  if (stage === "planning" || stage === "searching") return 2;
  if (stage === "assessing") return 3;
  return 4;
}

export function isTerminal(record: CheckRecord | null): boolean {
  return record?.status === "done" || record?.status === "error";
}

// The server sends a {"type":"ping"} event every 5 s, so 15 s of silence means the stream is
// stalled (e.g. a buffering proxy) even if it never errors: switch to polling.
const WATCHDOG_MS = 15_000;
const POLL_MS = 2_000;
const MAX_STREAM_ERRORS = 3;

export interface UseCheck {
  state: CheckState;
  loading: boolean;
  notFound: boolean;
  loadError: string | null;
  reconnecting: boolean; // the live connection dropped; retrying
}

interface Meta {
  loading: boolean;
  notFound: boolean;
  loadError: string | null;
  reconnecting: boolean;
}

type MetaAction = Partial<Meta>;

function metaReducer(m: Meta, a: MetaAction): Meta {
  return { ...m, ...a };
}

export function useCheck(id: string): UseCheck {
  const [state, dispatch] = useReducer(checkReducer, initialState);
  const [meta, setMeta] = useReducer(metaReducer, {
    loading: true,
    notFound: false,
    loadError: null,
    reconnecting: false,
  });
  useEffect(() => {
    let cancelled = false;
    // Started in this tab: its own stream has everything, no request needed.
    const unfollow = followLive(id, (action) => {
      if (!cancelled) dispatch(action);
    });
    if (unfollow) {
      setMeta({ loading: false });
      return () => {
        cancelled = true;
        unfollow();
      };
    }

    let source: EventSource | null = null;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let poller: ReturnType<typeof setInterval> | undefined;
    let streamErrors = 0;
    let reconnecting = false;

    const setReconnecting = (v: boolean) => {
      if (cancelled || v === reconnecting) return;
      reconnecting = v;
      setMeta({ reconnecting: v });
    };

    const stopStream = () => {
      if (watchdog) clearTimeout(watchdog);
      watchdog = undefined;
      source?.close();
      source = null;
    };

    const stopAll = () => {
      stopStream();
      if (poller) clearInterval(poller);
      poller = undefined;
      setReconnecting(false);
    };

    const refresh = async (): Promise<CheckRecord | null> => {
      try {
        const record = await api.getCheck(id);
        if (cancelled) return null;
        dispatch({ type: "record", record });
        setReconnecting(false);
        return record;
      } catch {
        setReconnecting(true); // transient; polling / the stream keeps trying
        return null;
      }
    };

    const startPolling = () => {
      stopStream();
      if (poller || cancelled) return;
      const tick = async () => {
        const record = await refresh();
        if (record && isTerminal(record)) stopAll();
      };
      void tick();
      poller = setInterval(tick, POLL_MS);
    };

    const armWatchdog = () => {
      if (watchdog) clearTimeout(watchdog);
      watchdog = setTimeout(startPolling, WATCHDOG_MS);
    };

    const startStream = () => {
      if (typeof EventSource === "undefined") {
        startPolling();
        return;
      }
      const es = new EventSource(api.eventsUrl(id));
      source = es;
      armWatchdog();
      es.onopen = () => {
        streamErrors = 0;
        setReconnecting(false);
      };
      es.onmessage = (msg) => {
        armWatchdog();
        streamErrors = 0;
        setReconnecting(false);
        let event: CheckEvent;
        try {
          event = JSON.parse(msg.data) as CheckEvent;
        } catch {
          return;
        }
        if (event.type === "ping") return; // keep-alive: already reset the watchdog
        dispatch(event);
        if (event.type === "snapshot" && isTerminal(event.record)) {
          stopAll();
        } else if (event.type === "done" || event.type === "error") {
          stopStream();
          // Full record incl. trace + evidence; if that fails, poll until it arrives.
          void refresh().then((r) => {
            if (!cancelled && (!r || !isTerminal(r))) startPolling();
          });
        }
      };
      es.onerror = () => {
        if (cancelled || source !== es) return;
        streamErrors += 1;
        // The browser retries on its own (and the server re-sends a snapshot on reconnect).
        // Give up on the stream only when it is closed for good or keeps failing.
        if (es.readyState === EventSource.CLOSED || streamErrors >= MAX_STREAM_ERRORS) startPolling();
        else setReconnecting(true);
      };
    };

    (async () => {
      try {
        const record = await api.getCheck(id);
        if (cancelled) return;
        dispatch({ type: "record", record });
        setMeta({ loading: false });
        if (!isTerminal(record)) startStream();
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setMeta({ loading: false, notFound: true });
        } else {
          setMeta({
            loading: false,
            loadError:
              e instanceof ApiError && e.status >= 500
                ? "Verity is having trouble right now. Please try again in a moment."
                : e instanceof Error
                  ? e.message
                  : "Could not load this check.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
      if (watchdog) clearTimeout(watchdog);
      source?.close();
      if (poller) clearInterval(poller);
    };
  }, [id]);

  return { state, ...meta };
}
