import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..schemas import Evidence, JuryResult, Source, Verdict
from ..trace import Trace
from .evidence import assess_evidence, find_sources, usable
from .ingest import load_prompt, render, system_prompt
from .verdict import post_check, render_evidence, verdict

if TYPE_CHECKING:
    from .orchestrator import Deps


def _label_rules() -> str:
    """The Labels + Guidance part of verdict.md. final_ruling.md says "same label definitions and
    output rules as before", but the judge's final call is a fresh conversation, so we append
    them for it to refer to."""
    text = load_prompt("verdict")
    return text[text.index("Labels:") : text.index("<claim>")].strip()


async def run_jury(
    claim_id: int,
    claim_text: str,
    sources: list[Source],
    evidence: list[Evidence],
    language: str,
    deps: "Deps",
    trace: Trace,
    emit: Callable[..., object],
) -> tuple[JuryResult, list[Source], list[Evidence]]:
    """Draft (FAST) and jury (JUDGE) in parallel; debate + final ruling if they disagree.
    Returns the result plus the (possibly extended) sources and evidence."""
    s = deps.settings
    good = usable(evidence)
    draft, jury = await asyncio.gather(
        verdict(claim_text, good, language, deps, trace,
                model=s.model_fast, step=f"verdict_draft[claim {claim_id}]"),
        verdict(claim_text, good, language, deps, trace,
                model=s.model_judge, step=f"verdict_jury[claim {claim_id}]"),
    )  # fmt: skip
    agreed = draft.label == jury.label
    emit(
        "verdicts_drafted",
        claim_id=claim_id,
        draft_label=draft.label,
        jury_label=jury.label,
        agreed=agreed,
    )

    if agreed:
        final = jury.model_copy(
            update={
                "confidence": round((draft.confidence + jury.confidence) / 2),
                "cited_source_ids": list(
                    dict.fromkeys(jury.cited_source_ids + draft.cited_source_ids)
                ),
            }
        )
        final = post_check(final, {e.source.id for e in good})
        result = JuryResult(draft=draft, jury=jury, agreed=True, debated=False, final=final)
        return result, sources, evidence

    extra = list(
        dict.fromkeys(
            q.strip()
            for q in draft.missing_evidence_queries + jury.missing_evidence_queries
            if q.strip()
        )
    )[: s.max_extra_queries]
    if extra:
        emit("debate_started", claim_id=claim_id, queries=extra)
        start = max((x.id for x in sources), default=0) + 1
        new_sources = await find_sources(
            extra, deps, claim=claim_text, start_id=start, exclude=sources
        )
        new_evidence = await assess_evidence(
            claim_text, new_sources, deps, trace, f"debate_assess[claim {claim_id}]"
        )
        sources = sources + new_sources
        evidence = evidence + new_evidence
        good = usable(evidence)

    final = await final_ruling(claim_id, claim_text, good, draft, jury, language, deps, trace)
    result = JuryResult(draft=draft, jury=jury, agreed=False, debated=bool(extra), final=final)
    return result, sources, evidence


async def final_ruling(
    claim_id: int,
    claim_text: str,
    good: list[Evidence],
    draft: Verdict,
    jury: Verdict,
    language: str,
    deps: "Deps",
    trace: Trace,
) -> Verdict:
    user = render(
        load_prompt("final_ruling"),
        {
            "claim": claim_text,
            "all_evidence": render_evidence(good),
            "draft.label": draft.label,
            "draft.confidence": draft.confidence,
            "draft.explanation": draft.explanation,
            "jury.label": jury.label,
            "jury.confidence": jury.confidence,
            "jury.explanation": jury.explanation,
            "language": language,
        },
    )
    v = await deps.llm.structured(
        trace=trace,
        step=f"final_ruling[claim {claim_id}]",
        model=deps.settings.model_judge,
        system=system_prompt(deps.today()),
        user=f"{user}\n\n{_label_rules()}",
        schema=Verdict,
    )
    return post_check(v, {e.source.id for e in good})
