import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..config import Settings
from ..events import EventBus
from ..news import NewsUnavailable
from ..schemas import (
    CheckRecord,
    CheckRequest,
    ClaimResult,
    ExtractedClaim,
    JuryResult,
    SearchMode,
    SearchRoute,
    Source,
    Verdict,
)
from ..search import IngestError, SearchUnavailable
from ..store import Store
from ..trace import Trace
from .claims import extract_claims, select_claims
from .evidence import (
    assess_evidence,
    discarded_count,
    find_news_sources,
    find_sources,
    usable,
)
from .ingest import ingest
from .jury import run_jury
from .queries import plan_searches

log = logging.getLogger(__name__)

TIMEOUT_MESSAGE = "The check took too long. Try a shorter text."
GENERIC_MESSAGE = "Something went wrong while checking. Please try again."
SEARCH_DOWN_MESSAGE = "Web search is not responding right now. Please try again in a minute."
CLAIM_FAILED = "Checking failed for this claim."
NO_SOURCES = "No sources found."
NO_USABLE_EVIDENCE = "Sources found but none directly addressed the claim."


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


@dataclass
class Deps:
    settings: Settings
    llm: Any  # app.llm.LLM or FakeLLM: async structured(*, trace, step, model, ...)
    search: Any  # app.search.Search or FakeSearch: async search_web(q), async extract_url(url)
    store: Store
    events: EventBus
    semaphore: asyncio.Semaphore
    today: Callable[[], str] = field(default=_utc_today)
    news: Any = None  # app.news.NewsSearch or a fake: async search_news(q); None = news off


def _settled(label: str, confidence: int, explanation: str) -> JuryResult:
    """A result decided in code (no jury): draft = jury = final."""
    v = Verdict(label=label, confidence=confidence, explanation=explanation, cited_source_ids=[])
    return JuryResult(draft=v, jury=v, agreed=True, debated=False, final=v)


async def run_check(check_id: str, req: CheckRequest, deps: Deps) -> None:
    """Run the whole pipeline for a check whose 'queued' record already exists in the store."""
    record = await deps.store.get_check(check_id)
    if record is None:
        log.error("check_id=%s run_check: no queued record", check_id)
        return

    async with deps.semaphore:
        started = time.perf_counter()
        record.status = "running"
        await deps.store.save_check(record)
        trace = Trace(
            prices=deps.settings.prices,
            on_record=lambda e: deps.events.emit(check_id, "model_call", **e.model_dump()),
        )
        error: str | None = None
        try:
            await asyncio.wait_for(
                _run(record, req, deps, trace), deps.settings.check_timeout_seconds
            )
        except IngestError as e:
            error = str(e)
            log.info("check_id=%s ingest failed: %s", check_id, e)
        except SearchUnavailable:
            error = SEARCH_DOWN_MESSAGE
            log.warning("check_id=%s web search unavailable", check_id, exc_info=True)
        except TimeoutError:
            error = TIMEOUT_MESSAGE
            log.warning("check_id=%s timed out", check_id)
        except Exception:
            error = GENERIC_MESSAGE
            log.exception("check_id=%s failed", check_id)

        record.claims.sort(key=lambda c: c.id)
        record.trace = list(trace.entries)
        record.totals = trace.totals() | {"duration_s": round(time.perf_counter() - started, 1)}
        record.status = "error" if error else "done"
        record.error = error
        await deps.store.save_check(record)
        if error:
            deps.events.emit(check_id, "error", message=error)
        else:
            deps.events.emit(check_id, "done", totals=record.totals)
        log.info("check_id=%s finished status=%s", check_id, record.status)


async def _run(record: CheckRecord, req: CheckRequest, deps: Deps, trace: Trace) -> None:
    check_id = record.id

    def emit(type_: str, **data) -> None:
        deps.events.emit(check_id, type_, **data)

    text, title = await ingest(req, deps)
    emit("ingest_done", chars=len(text), **({"title": title} if title else {}))

    extraction = await extract_claims(text, deps, trace)
    kept, skipped = select_claims(extraction, deps.settings.max_claims)
    record.language = extraction.language
    record.skipped_claims = skipped
    emit(
        "claims_found",
        claims=[{"id": c.id, "text": c.text} for c in kept],
        skipped=len(skipped),
        language=extraction.language,
    )
    await deps.store.save_check(record)
    if not kept:
        return

    async def one(claim: ExtractedClaim) -> None:
        result = await _check_claim(claim, extraction.language, req.mode, deps, trace, emit)
        record.claims.append(result)
        await deps.store.save_check(record)

    outcomes = await asyncio.gather(*(one(c) for c in kept), return_exceptions=True)
    failures = [(c, o) for c, o in zip(kept, outcomes, strict=True) if isinstance(o, BaseException)]
    for claim, exc in failures:
        log.error("check_id=%s claim %s failed", check_id, claim.id, exc_info=exc)
    if failures and len(failures) == len(kept):
        raise failures[0][1]
    for claim, _ in failures:
        result = ClaimResult(
            id=claim.id,
            text=claim.text,
            queries=[],
            evidence=[],
            result=_settled("UNVERIFIED", 0, CLAIM_FAILED),
        )
        record.claims.append(result)
        emit("claim_done", claim_id=claim.id, final=result.result.final.model_dump(),
             agreed=True, debated=False, rechecked=False)  # fmt: skip
    if failures:
        await deps.store.save_check(record)


def wants_news(mode: SearchMode, time_sensitive: bool, deps: Deps) -> bool:
    """News search is used when it is configured and the mode asks for it: always in News mode,
    for recent-event claims in Auto mode, never in Web mode."""
    if deps.news is None or mode == "web":
        return False
    return mode == "news" or time_sensitive


async def gather_sources(
    claim: ExtractedClaim, queries: list[str], news: bool, deps: Deps
) -> tuple[list[Source], SearchRoute]:
    """News route: news API first; if it finds fewer than news_min_sources, one web query tops
    them up (1 Tavily call instead of 3). If the news API fails, the claim uses web search."""
    s = deps.settings
    if news:
        try:
            found = await find_news_sources(queries, deps, claim=claim.text)
        except NewsUnavailable as e:
            log.warning("claim %s: news search unavailable (%s); using web search", claim.id, e)
        else:
            if len(found) >= s.news_min_sources:
                return found, "news"
            try:
                extra = await find_sources(
                    queries[:1],
                    deps,
                    claim=claim.text,
                    start_id=len(found) + 1,
                    exclude=found,
                    max_total=max(0, s.max_sources_per_claim - len(found)),
                )
            except SearchUnavailable:
                if not found:
                    raise
                log.warning("claim %s: web top-up failed; using news sources only", claim.id)
                return found, "news"
            return found + extra, ("mixed" if found and extra else "news" if found else "web")
    return await find_sources(queries, deps, claim=claim.text), "web"


async def _check_claim(
    claim: ExtractedClaim,
    language: str,
    mode: SearchMode,
    deps: Deps,
    trace: Trace,
    emit: Callable[..., None],
) -> ClaimResult:
    """Steps 3-8 for one claim, in order."""
    queries, time_sensitive = await plan_searches(claim, deps, trace)
    emit("queries_planned", claim_id=claim.id, queries=[q.query for q in queries])

    sources, route = await gather_sources(
        claim, [q.query for q in queries], wants_news(mode, time_sensitive, deps), deps
    )
    emit(
        "sources_found",
        claim_id=claim.id,
        count=len(sources),
        domains=list(dict.fromkeys(x.domain for x in sources)),
        route=route,
    )

    evidence = []
    if not sources:
        result = _settled("UNVERIFIED", 0, NO_SOURCES)
    else:
        evidence = await assess_evidence(
            claim.text, sources, deps, trace, f"assess_evidence[claim {claim.id}]"
        )
        emit(
            "evidence_ready",
            claim_id=claim.id,
            verified=len(usable(evidence)),
            discarded=discarded_count(evidence),
        )
        if not usable(evidence):
            result = _settled("UNVERIFIED", 10, NO_USABLE_EVIDENCE)
        else:
            result, sources, evidence = await run_jury(
                claim.id, claim.text, sources, evidence, language, deps, trace, emit
            )

    emit(
        "claim_done",
        claim_id=claim.id,
        final=result.final.model_dump(),
        agreed=result.agreed,
        debated=result.debated,
        rechecked=result.rechecked,
    )
    return ClaimResult(
        id=claim.id,
        text=claim.text,
        queries=queries,
        evidence=evidence,
        result=result,
        search=route,
    )
