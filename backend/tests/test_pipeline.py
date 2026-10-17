import asyncio

import pytest
from conftest import FakeLLM, FakeSearch, raw_result

from app.config import Settings
from app.events import EventBus
from app.pipeline.orchestrator import Deps, run_check
from app.schemas import (
    CheckRecord,
    CheckRequest,
    ClaimExtraction,
    EvidenceAssessment,
    ExtractedClaim,
    PlannedQuery,
    QueryPlan,
    SourceAssessment,
    Verdict,
)
from app.store import Store

FAST, JUDGE = "nvidia/fast", "nvidia/judge"
TEXT = "The Great Wall of China is visible from space. Water boils at 100 C at sea level."
QUOTE_A = "The Great Wall cannot be seen from orbit with the naked eye."
QUOTE_B = "Astronauts confirm the wall is too narrow to see from space."
PAGE_A = f"Intro text. {QUOTE_A} More text follows here."
PAGE_B = f"Other intro. {QUOTE_B} End."


def settings(**kw) -> Settings:
    base = dict(model_fast=FAST, model_judge=JUDGE, nebius_api_key="k", tavily_api_key="t")
    return Settings(_env_file=None, **(base | kw))


@pytest.fixture
def deps(tmp_path, fake_llm: FakeLLM, fake_search: FakeSearch) -> Deps:
    return Deps(
        settings=settings(),
        llm=fake_llm,
        search=fake_search,
        store=Store(tmp_path),
        events=EventBus(),
        semaphore=asyncio.Semaphore(3),
        today=lambda: "2026-10-14",
    )


async def run(deps: Deps, req: CheckRequest | None = None) -> CheckRecord:
    req = req or CheckRequest(text=TEXT)
    record = CheckRecord(
        id="chk1",
        created_at="2026-10-14T00:00:00+00:00",
        status="queued",
        input_type="url" if req.url else "text",
        input_preview=(req.text or req.url or "")[:300],
    )
    await deps.store.save_check(record)
    await run_check("chk1", req, deps)
    saved = await deps.store.get_check("chk1")
    assert saved is not None
    return saved


def claim(i: int, text: str, worthy: bool = True) -> ExtractedClaim:
    return ExtractedClaim(id=i, text=text, checkworthy=worthy, reason="r")


def queries(*qs: str) -> QueryPlan:
    return QueryPlan(queries=[PlannedQuery(query=q, intent="neutral") for q in qs])


def assess(*items: tuple[int, str, str]) -> EvidenceAssessment:
    return EvidenceAssessment(
        items=[SourceAssessment(source_id=i, stance=s, quote=q, note="n") for i, s, q in items]
    )


def verdict(label: str, conf: int = 80, cited=(1,), missing=()) -> Verdict:
    return Verdict(
        label=label,
        confidence=conf,
        explanation=f"{label} because",
        cited_source_ids=list(cited),
        missing_evidence_queries=list(missing),
    )


def queue_claim(llm: FakeLLM, n: int, qs: tuple[str, ...], ev: EvidenceAssessment) -> None:
    llm.queue(f"plan_queries[claim {n}]", queries(*qs))
    llm.queue(f"assess_evidence[claim {n}]", ev)


def steps(llm: FakeLLM) -> list[str]:
    return [c["step"] for c in llm.calls]


async def test_happy_path_two_claims_jury_agrees(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A, 0.9)]
    fake_llm.queue(
        "extract_claims",
        ClaimExtraction(
            language="en",
            claims=[claim(1, "Wall visible"), claim(2, "I love walls", False), claim(3, "Water")],
        ),
    )
    for n in (1, 2):
        queue_claim(fake_llm, n, ("q1", "q2", "q3"), assess((1, "refutes", QUOTE_A)))
        fake_llm.queue(f"verdict_draft[claim {n}]", verdict("FALSE", 80))
        fake_llm.queue(f"verdict_jury[claim {n}]", verdict("FALSE", 91))

    rec = await run(deps)

    assert rec.status == "done" and rec.error is None and rec.language == "en"
    assert [c.id for c in rec.claims] == [1, 2]  # renumbered
    assert [c.text for c in rec.skipped_claims] == ["I love walls"]
    for c in rec.claims:
        assert c.result.agreed and not c.result.debated
        assert c.result.final.label == "FALSE"
        assert c.result.final.confidence == 86  # round((80 + 91) / 2)
        assert c.evidence[0].quote_verified
    assert not any("final_ruling" in s or "debate" in s for s in steps(fake_llm))
    assert rec.totals["model_calls"] == len(fake_llm.calls) == 9
    assert "duration_s" in rec.totals and len(rec.trace) == 9


async def test_disagreement_runs_debate_and_final_ruling(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A, 0.9)]
    fake_search.results["extra q"] = [
        raw_result("https://a.com/x", PAGE_A),  # already seen -> excluded
        raw_result("https://b.org/y", PAGE_B, 0.8),
    ]
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(fake_llm, 1, ("q1", "q2", "q3"), assess((1, "refutes", QUOTE_A)))
    fake_llm.queue("verdict_draft[claim 1]", verdict("TRUE", 60, missing=["extra q"]))
    fake_llm.queue("verdict_jury[claim 1]", verdict("FALSE", 70, missing=["extra q", "more"]))
    fake_llm.queue("debate_assess[claim 1]", assess((2, "refutes", QUOTE_B)))
    fake_llm.queue("final_ruling[claim 1]", verdict("FALSE", 88, cited=(1, 2)))

    rec = await run(deps)

    r = rec.claims[0].result
    assert not r.agreed and r.debated
    assert (r.draft.label, r.jury.label, r.final.label) == ("TRUE", "FALSE", "FALSE")
    assert r.final.cited_source_ids == [1, 2]
    assert fake_search.queries[-2:] == ["extra q", "more"]  # MAX_EXTRA_QUERIES = 2
    assert [e.source.id for e in rec.claims[0].evidence] == [1, 2]  # numbering continues
    final_call = next(c for c in fake_llm.calls if c["step"] == "final_ruling[claim 1]")
    assert final_call["model"] == JUDGE
    assert QUOTE_B in final_call["user"] and "TRUE because" in final_call["user"]
    types = [e["type"] for e in deps.events.history("chk1")]
    assert "debate_started" in types and types[-1] == "done"


async def test_unverified_quotes_excluded_from_verdict_input(deps, fake_llm, fake_search):
    fake_search.default = [
        raw_result("https://a.com/x", PAGE_A, 0.9),
        raw_result("https://b.org/y", PAGE_B, 0.8),
    ]
    fake_quote = "The wall is clearly visible from the moon every night."
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(
        fake_llm, 1, ("q1", "q2", "q3"),
        assess((1, "supports", fake_quote), (2, "refutes", QUOTE_B)),
    )  # fmt: skip
    fake_llm.queue("verdict_draft[claim 1]", verdict("FALSE", cited=(1, 2)))
    fake_llm.queue("verdict_jury[claim 1]", verdict("FALSE", cited=(2,)))

    rec = await run(deps)

    ev = {e.source.id: e for e in rec.claims[0].evidence}
    assert not ev[1].quote_verified and ev[2].quote_verified  # kept for the trace
    for step in ("verdict_draft[claim 1]", "verdict_jury[claim 1]"):
        call = next(c for c in fake_llm.calls if c["step"] == step)
        assert fake_quote not in call["user"] and QUOTE_B in call["user"]
    assert rec.claims[0].result.final.cited_source_ids == [2]  # id 1 is not usable
    ready = next(e for e in deps.events.history("chk1") if e["type"] == "evidence_ready")
    assert (ready["verified"], ready["discarded"]) == (1, 1)


async def test_no_sources_gives_unverified_without_more_calls(deps, fake_llm, fake_search):
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    fake_llm.queue("plan_queries[claim 1]", queries("q1", "q2", "q3"))

    rec = await run(deps)

    final = rec.claims[0].result.final
    assert (final.label, final.confidence, final.explanation) == (
        "UNVERIFIED",
        0,
        "No sources found.",
    )
    assert rec.claims[0].result.agreed and not rec.claims[0].result.debated
    assert steps(fake_llm) == ["extract_claims", "plan_queries[claim 1]"]


async def test_no_usable_evidence_skips_jury(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A)]
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(fake_llm, 1, ("q1", "q2", "q3"), assess((1, "irrelevant", "")))

    rec = await run(deps)

    final = rec.claims[0].result.final
    assert (final.label, final.confidence) == ("UNVERIFIED", 10)
    assert not any("verdict" in s for s in steps(fake_llm))


async def test_fast_and_judge_model_ids(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A)]
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(fake_llm, 1, ("q1",), assess((1, "refutes", QUOTE_A)))
    fake_llm.queue("verdict_draft[claim 1]", verdict("TRUE", missing=["x"]))
    fake_llm.queue("verdict_jury[claim 1]", verdict("FALSE"))
    fake_llm.queue("final_ruling[claim 1]", verdict("FALSE"))

    await run(deps)

    models = {c["step"].split("[")[0]: c["model"] for c in fake_llm.calls}
    assert models == {
        "extract_claims": FAST,
        "plan_queries": FAST,
        "assess_evidence": FAST,
        "verdict_draft": FAST,
        "verdict_jury": JUDGE,
        "final_ruling": JUDGE,
    }
    # 1 query from the model + the claim text as padding... capped at QUERIES_PER_CLAIM = 3
    assert fake_search.queries[:2] == ["q1", "Wall"]


async def test_true_without_valid_citation_downgraded(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A)]
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(fake_llm, 1, ("q1", "q2", "q3"), assess((1, "supports", QUOTE_A)))
    fake_llm.queue("verdict_draft[claim 1]", verdict("TRUE", 95, cited=(99,)))
    fake_llm.queue("verdict_jury[claim 1]", verdict("TRUE", 90, cited=(42,)))

    rec = await run(deps)

    r = rec.claims[0].result
    for v in (r.draft, r.jury, r.final):
        assert v.label == "UNVERIFIED" and v.confidence <= 30
        assert v.cited_source_ids == [] and "(No verifiable citation)" in v.explanation
    assert r.agreed  # both downgraded to the same label


async def test_zero_checkworthy_claims_done_empty(deps, fake_llm):
    fake_llm.queue(
        "extract_claims",
        ClaimExtraction(language="en", claims=[claim(1, "Walls are pretty", False)]),
    )

    rec = await run(deps)

    assert rec.status == "done" and rec.claims == [] and len(rec.skipped_claims) == 1
    assert steps(fake_llm) == ["extract_claims"]
    types = [e["type"] for e in deps.events.history("chk1")]
    assert types[-1] == "done"


async def test_url_ingest_uses_extract(deps, fake_llm, fake_search):
    fake_search.page = "# Wall myths\n\nSome article text about the Great Wall of China."
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[]))

    rec = await run(deps, CheckRequest(url="https://news.example.com/wall"))

    assert rec.status == "done"
    assert fake_search.extracted == ["https://news.example.com/wall"]
    ingest = deps.events.history("chk1")[0]
    assert ingest["type"] == "ingest_done" and ingest["title"] == "Wall myths"
    assert "Some article text" in fake_llm.calls[0]["user"]


async def test_events_and_prompt_rendering(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A)]
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    queue_claim(fake_llm, 1, ("q1", "q2", "q3"), assess((1, "refutes", QUOTE_A)))
    fake_llm.queue("verdict_draft[claim 1]", verdict("FALSE"))
    fake_llm.queue("verdict_jury[claim 1]", verdict("FALSE"))

    await run(deps)

    types = [e["type"] for e in deps.events.history("chk1")]
    for t in ("ingest_done", "claims_found", "queries_planned", "sources_found",
              "evidence_ready", "verdicts_drafted", "claim_done", "model_call"):  # fmt: skip
        assert t in types
    assert types[-1] == "done"
    done = deps.events.history("chk1")[-1]
    assert done["totals"]["model_calls"] == 5
    first = fake_llm.calls[0]
    assert "Today's date is 2026-10-14" in first["system"]
    assert "<input>\n" + TEXT in first["user"] and "at most 5 claims" in first["user"]
    assert "{" not in first["system"]
    jury_call = next(c for c in fake_llm.calls if c["step"] == "verdict_jury[claim 1]")
    assert "FALSE because" not in jury_call["user"]  # the judge never sees the draft


async def test_one_failed_claim_kept_as_unverified(deps, fake_llm, fake_search):
    fake_search.default = [raw_result("https://a.com/x", PAGE_A)]
    fake_llm.queue(
        "extract_claims", ClaimExtraction(language="en", claims=[claim(1, "A"), claim(2, "B")])
    )
    queue_claim(fake_llm, 1, ("q1", "q2", "q3"), assess((1, "refutes", QUOTE_A)))
    fake_llm.queue("verdict_draft[claim 1]", verdict("FALSE"))
    fake_llm.queue("verdict_jury[claim 1]", verdict("FALSE"))
    fake_llm.queue("plan_queries[claim 2]", RuntimeError("boom"))

    rec = await run(deps)

    assert rec.status == "done"
    assert rec.claims[1].result.final.explanation == "Checking failed for this claim."


async def test_all_claims_failed_is_error(deps, fake_llm):
    fake_llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "A")]))
    fake_llm.queue("plan_queries[claim 1]", RuntimeError("secret detail"))

    rec = await run(deps)

    assert rec.status == "error"
    assert "secret detail" not in rec.error
    assert deps.events.history("chk1")[-1] == {"type": "error", "message": rec.error}


async def test_timeout_is_error(deps, fake_llm):
    # model_copy skips validation, so a sub-second timeout is allowed in the test
    deps.settings = deps.settings.model_copy(update={"check_timeout_seconds": 0.05})

    async def slow(**_):
        await asyncio.sleep(1)

    fake_llm.structured = slow

    rec = await run(deps)

    assert rec.status == "error" and rec.error == "The check took too long. Try a shorter text."


async def test_bad_text_is_ingest_error(deps, fake_llm):
    rec = await run(deps, CheckRequest(text="short"))
    assert rec.status == "error" and "too short" in rec.error
    assert fake_llm.calls == []


def test_render_sources_swaps_double_quotes_and_quote_still_verifies():
    from app.pipeline.evidence import render_sources
    from app.quotes import verify_quote
    from app.schemas import Source

    content = 'It is “not visible”, and "indeed visible to the naked eye," says Cernan.'
    src = Source(id=1, url="https://x.org/a", title='The "myth"', domain="x.org", content=content)
    rendered = render_sources([src])
    assert rendered.count('"') == 6  # only the tag attribute quotes remain
    assert "“" not in rendered and "'indeed visible" in rendered
    copied = "'indeed visible to the naked eye,' says Cernan."
    assert verify_quote(copied, content)
