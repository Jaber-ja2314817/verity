from typing import Literal

from pydantic import BaseModel, Field

Label = Literal["TRUE", "FALSE", "MISLEADING", "UNVERIFIED"]
Stance = Literal["supports", "refutes", "mixed", "irrelevant"]
Intent = Literal["neutral", "support", "refute"]


# ---- LLM outputs ----
class ExtractedClaim(BaseModel):
    id: int
    text: str = Field(description="One self-contained, checkable factual claim, max 30 words")
    checkworthy: bool
    reason: str = Field(description="Why it is or isn't checkable, max 15 words")


class ClaimExtraction(BaseModel):
    language: str = Field(description="ISO 639-1 code of the input text, e.g. 'en'")
    claims: list[ExtractedClaim]


class PlannedQuery(BaseModel):
    query: str = Field(description="Web search query, max 12 words")
    intent: Intent


class QueryPlan(BaseModel):
    queries: list[PlannedQuery]


class SourceAssessment(BaseModel):
    source_id: int
    stance: Stance
    quote: str = Field(
        description="Exact sentence copied word for word from the source, or empty if irrelevant"
    )
    note: str = Field(description="Max 20 words on why")


class EvidenceAssessment(BaseModel):
    items: list[SourceAssessment]


class Verdict(BaseModel):
    label: Label
    confidence: int = Field(ge=0, le=100)
    explanation: str = Field(description="Plain language, max 90 words")
    cited_source_ids: list[int]
    missing_evidence_queries: list[str] = Field(
        default_factory=list,
        description="Up to 2 search queries that would settle the claim, if evidence is weak",
    )


# ---- Internal / API ----
class Source(BaseModel):
    id: int
    url: str
    title: str
    domain: str
    content: str  # text given to the model (trimmed to SOURCE_CHARS)
    favicon: str | None = None


class Evidence(BaseModel):
    source: Source
    stance: Stance
    quote: str
    quote_verified: bool
    note: str


class JuryResult(BaseModel):
    draft: Verdict  # from MODEL_FAST
    jury: Verdict  # from MODEL_JUDGE (independent)
    agreed: bool
    debated: bool  # extra search round happened
    final: Verdict


class ClaimResult(BaseModel):
    id: int
    text: str
    queries: list[PlannedQuery]
    evidence: list[Evidence]
    result: JuryResult


class TraceEntry(BaseModel):
    step: str  # e.g. "extract_claims", "verdict_draft[claim 2]"
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float
    cost_usd: float | None


class CheckRecord(BaseModel):
    id: str
    created_at: str  # ISO 8601 UTC
    status: Literal["queued", "running", "done", "error"]
    input_type: Literal["text", "url"]
    input_preview: str  # first 300 chars
    language: str | None = None
    claims: list[ClaimResult] = []
    skipped_claims: list[ExtractedClaim] = []
    trace: list[TraceEntry] = []
    totals: dict = {}  # tokens, cost_usd, duration_s, model_calls
    error: str | None = None


class CheckRequest(BaseModel):
    text: str | None = None
    url: str | None = None  # exactly one of text/url must be set


MIN_TEXT_CHARS = 20
MAX_URL_CHARS = 2000


def validate_check_request(req: CheckRequest, max_input_chars: int) -> CheckRequest:
    """Check a request and return a trimmed copy. Raises ValueError with a user-facing message."""
    text = (req.text or "").strip()
    url = (req.url or "").strip()
    if bool(text) == bool(url):
        raise ValueError("Send either text or a URL, not both and not neither.")
    if text:
        if len(text) < MIN_TEXT_CHARS:
            raise ValueError(f"Text is too short (minimum {MIN_TEXT_CHARS} characters).")
        if len(text) > max_input_chars:
            raise ValueError(f"Text is too long (maximum {max_input_chars} characters).")
        return CheckRequest(text=text)
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://.")
    if len(url) > MAX_URL_CHARS:
        raise ValueError(f"URL is too long (maximum {MAX_URL_CHARS} characters).")
    return CheckRequest(url=url)
