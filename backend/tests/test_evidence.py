from types import SimpleNamespace

from app.config import Settings
from app.pipeline.evidence import assess_evidence, discarded_count, usable
from app.schemas import Evidence, EvidenceAssessment, Source, SourceAssessment

FAST = "nvidia/fast"
PAGE = "Intro. RMS Titanic sank in the North Atlantic Ocean on 15 April 1912. More text here."


def src(i: int, content: str = PAGE, reliability: str = "unknown") -> Source:
    return Source(
        id=i, url=f"https://s{i}.org/a", title="T", domain=f"s{i}.org", content=content,
        reliability=reliability,
    )  # fmt: skip


def deps(llm) -> SimpleNamespace:
    settings = Settings(_env_file=None, model_fast=FAST, model_judge="nvidia/judge")
    return SimpleNamespace(settings=settings, llm=llm, today=lambda: "2026-10-19")


def item(i: int, stance: str, quote: str) -> SourceAssessment:
    return SourceAssessment(source_id=i, stance=stance, quote=quote, note="n")


async def test_prompt_names_every_source_id(fake_llm, trace):
    fake_llm.queue(
        "a", EvidenceAssessment(items=[item(1, "irrelevant", ""), item(2, "irrelevant", "")])
    )
    await assess_evidence("Titanic sank in 1920.", [src(1), src(2)], deps(fake_llm), trace, "a")
    user = fake_llm.calls[0]["user"]
    assert "all 2 sources (1, 2)" in user and "Titanic sank in 1920." in user


async def test_skipped_sources_are_asked_again(fake_llm, trace):
    quote = "RMS Titanic sank in the North Atlantic Ocean on 15 April 1912."
    fake_llm.queue("a", EvidenceAssessment(items=[item(1, "refutes", quote)]))
    fake_llm.queue("a retry", EvidenceAssessment(items=[item(3, "refutes", quote)]))
    ev = await assess_evidence("c", [src(1), src(2), src(3)], deps(fake_llm), trace, "a")
    retry = fake_llm.calls[1]
    assert (
        retry["step"] == "a retry" and 'id="2"' in retry["user"] and 'id="1"' not in retry["user"]
    )
    assert [(e.source.id, e.stance, e.quote_verified) for e in ev] == [
        (1, "refutes", True), (2, "irrelevant", False), (3, "refutes", True),
    ]  # fmt: skip


async def test_near_miss_quote_is_replaced_by_source_text(fake_llm, trace):
    fake_llm.queue("a", EvidenceAssessment(items=[
        item(1, "refutes", "RMS Titanic sank in North Atlantic Ocean on 15 April 1912"),
        item(2, "refutes", "RMS Titanic sank in the North Atlantic Ocean on 15 April 1921"),
    ]))  # fmt: skip
    ev = await assess_evidence("c", [src(1), src(2)], deps(fake_llm), trace, "a")
    assert ev[0].quote_verified
    assert ev[0].quote == "RMS Titanic sank in the North Atlantic Ocean on 15 April 1912."
    assert not ev[1].quote_verified  # a changed number is never snapped to the source
    assert discarded_count(ev) == 1


def evidence(i: int, stance: str, quote: str, reliability: str = "unknown", ok=True) -> Evidence:
    return Evidence(
        source=src(i, reliability=reliability), stance=stance, quote=quote, quote_verified=ok,
        note="",
    )  # fmt: skip


def test_usable_dedupes_mirrors_and_puts_reliable_sources_first():
    q = "Sound waves cannot normally travel through vacuums, like space."
    ev = [
        evidence(1, "supports", q, "low"),
        evidence(2, "mixed", "Other sentence with enough words in it.", "unknown"),
        evidence(3, "supports", q.upper(), "high"),  # mirror copy, more reliable
        evidence(4, "refutes", "Unverified quote is not used here at all.", ok=False),
        evidence(5, "irrelevant", "Irrelevant source quote is not used either."),
        evidence(6, "refutes", "A medium source says something else here.", "medium"),
    ]
    assert [e.source.id for e in usable(ev)] == [3, 6, 2]
