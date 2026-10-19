// Mirrors backend/app/schemas.py. Keep in sync.
export type Label = "TRUE" | "FALSE" | "MISLEADING" | "UNVERIFIED";
export type Stance = "supports" | "refutes" | "mixed" | "irrelevant";
export type Intent = "neutral" | "support" | "refute";
export type Reliability = "high" | "medium" | "low" | "unknown";
export type CheckStatus = "queued" | "running" | "done" | "error";

export interface ExtractedClaim {
  id: number;
  text: string;
  checkworthy: boolean;
  reason: string;
}

export interface PlannedQuery {
  query: string;
  intent: Intent;
}

export interface Verdict {
  label: Label;
  confidence: number;
  explanation: string;
  cited_source_ids: number[];
  missing_evidence_queries: string[];
}

export interface Source {
  id: number;
  url: string;
  title: string;
  domain: string;
  content: string;
  favicon: string | null;
  published_date?: string | null; // ISO date; missing on checks stored before it existed
  reliability?: Reliability; // domain tier; missing on older checks
}

export interface Evidence {
  source: Source;
  stance: Stance;
  quote: string;
  quote_verified: boolean;
  note: string;
}

export interface JuryResult {
  draft: Verdict;
  jury: Verdict;
  agreed: boolean;
  debated: boolean; // an extra search round happened
  rechecked?: boolean; // both said UNVERIFIED -> extra search (+ judge ruling if new evidence); missing on older checks
  final: Verdict;
}

export interface ClaimResult {
  id: number;
  text: string;
  queries: PlannedQuery[];
  evidence: Evidence[];
  result: JuryResult;
}

export interface TraceEntry {
  step: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_s: number;
  cost_usd: number | null;
}

export interface Totals {
  model_calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  duration_s?: number;
}

export interface CheckRecord {
  id: string;
  created_at: string;
  status: CheckStatus;
  input_type: "text" | "url";
  input_preview: string;
  language: string | null;
  claims: ClaimResult[];
  skipped_claims: ExtractedClaim[];
  trace: TraceEntry[];
  totals: Totals;
  error: string | null;
}

export interface CheckRequest {
  text?: string;
  url?: string;
}

export interface Example {
  title: string;
  type: "text" | "url";
  value: string;
}

export interface Health {
  ok: boolean;
  models: { fast: string; judge: string };
  version: string;
}

// Benchmark file (eval/results/latest.json) is written in Phase 4; the shape is loose until then.
export type Benchmark = Record<string, unknown>;

// Server-Sent Events from GET /api/checks/{id}/events (field `type` is the event name).
// Each connection starts with a snapshot, then replays the check's event history, then goes live.
export type CheckEvent =
  | { type: "snapshot"; record: CheckRecord }
  | { type: "ingest_done"; chars: number; title?: string }
  | { type: "claims_found"; claims: { id: number; text: string }[]; skipped: number; language: string }
  | { type: "queries_planned"; claim_id: number; queries: string[] }
  | { type: "sources_found"; claim_id: number; count: number; domains: string[] }
  | { type: "evidence_ready"; claim_id: number; verified: number; discarded: number }
  | { type: "verdicts_drafted"; claim_id: number; draft_label: Label; jury_label: Label; agreed: boolean }
  | { type: "debate_started"; claim_id: number; queries: string[] }
  | { type: "recheck_started"; claim_id: number; queries: string[] }
  | { type: "claim_done"; claim_id: number; final: Verdict; agreed: boolean; debated: boolean; rechecked?: boolean }
  | ({ type: "model_call" } & TraceEntry)
  | { type: "done"; totals: Totals }
  | { type: "ping" } // keep-alive, every few seconds
  | { type: "error"; message: string };
