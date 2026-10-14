import { useEffect, useReducer } from "react";
import { api, ApiError } from "../api";
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
        draftLabel: c.result.draft.label,
        juryLabel: c.result.jury.label,
      },
      "done",
    );
  }
  return next;
}

export function checkReducer(state: CheckState, action: CheckAction): CheckState {
  const p = state.progress;
  switch (action.type) {
    case "snapshot":
    case "record":
      return { record: action.record, progress: fromRecord(p, action.record) };
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
    case "claim_done":
      return {
        ...state,
        progress: updateClaim(
          p,
          action.claim_id,
          { final: action.final, agreed: action.agreed, debated: action.debated },
          "done",
        ),
      };
    case "model_call": {
      const { type: _t, ...entry } = action;
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

const WATCHDOG_MS = 10_000;
const POLL_MS = 2_000;

export interface UseCheck {
  state: CheckState;
  loading: boolean;
  notFound: boolean;
  loadError: string | null;
}

interface Meta {
  loading: boolean;
  notFound: boolean;
  loadError: string | null;
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
  });
  useEffect(() => {
    let cancelled = false;
    let source: EventSource | null = null;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let poller: ReturnType<typeof setInterval> | undefined;

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
    };

    const refresh = async (): Promise<CheckRecord | null> => {
      try {
        const record = await api.getCheck(id);
        if (cancelled) return null;
        dispatch({ type: "record", record });
        return record;
      } catch {
        return null; // transient; polling keeps trying
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
      source = new EventSource(api.eventsUrl(id));
      armWatchdog();
      source.onmessage = (msg) => {
        armWatchdog();
        let event: CheckEvent;
        try {
          event = JSON.parse(msg.data) as CheckEvent;
        } catch {
          return;
        }
        dispatch(event);
        if (event.type === "snapshot" && isTerminal(event.record)) {
          stopAll();
        } else if (event.type === "done" || event.type === "error") {
          stopStream();
          void refresh(); // full record incl. trace + evidence
        }
      };
      source.onerror = () => {
        if (!cancelled) startPolling();
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
            loadError: e instanceof Error ? e.message : "Could not load this check.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
      stopAll();
    };
  }, [id]);

  return { state, ...meta };
}
