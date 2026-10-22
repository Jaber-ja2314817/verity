import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..schemas import Evidence, JuryResult, Source, Verdict
from ..trace import Trace
from .evidence import assess_evidence, find_sources, usable
from .ingest import defuse, load_prompt, render, system_prompt
from .verdict import post_check, render_evidence, verdict

if TYPE_CHECKING:
    from .orchestrator import Deps

log = logging.getLogger(__name__)

DISAGREED = "Two independent reviewers disagreed about this claim."
RECHECK = (
    "Two independent reviewers both found the first evidence too weak to decide (UNVERIFIED), "
    "so more evidence was gathered. Their opinions below are about the first evidence only."
)


def _label_rules() -> str:
    """The Labels + Guidance part of verdict.md. final_ruling.md says "same label definitions and
    output rules as before", but the judge's final call is a fresh conversation, so we append
    them for it to refer to."""
    text = load_prompt("verdict")
    return text[text.index("Labels:") : text.index("<claim>")].strip()


def _extra_queries(draft: Verdict, jury: Verdict, limit: int) -> list[str]:
    qs = (q.strip() for q in draft.missing_evidence_queries + jury.missing_evidence_queries)
    return list(dict.fromkeys(q for q in qs if q))[:limit]


async def _extra_round(
    claim_id: int,
    claim_text: str,
    queries: list[str],
    sources: list[Source],
    evidence: list[Evidence],
    deps: "Deps",
    trace: Trace,
) -> tuple[list[Source], list[Evidence], int]:
    """Search the reviewers' missing-evidence queries and assess only the new sources.
    Returns extended sources and evidence plus the number of new usable items (a quote already
    in the evidence, e.g. from a mirror site, is not new). A failed search or assessment is
    logged and the check continues with the evidence it already has (no data is invented)."""
    start = max((x.id for x in sources), default=0) + 1
    try:
        new_sources = await find_sources(
            queries, deps, claim=claim_text, start_id=start, exclude=sources
        )
        new_evidence = await assess_evidence(
            claim_text, new_sources, deps, trace, f"debate_assess[claim {claim_id}]"
        )
    except Exception:  # noqa: BLE001 - the extra round is optional; the claim must not fail
        log.warning("claim %s: extra round failed; ruling on existing evidence", claim_id,
                    exc_info=True)  # fmt: skip
        return sources, evidence, 0
    new_usable = len(usable(evidence + new_evidence)) - len(usable(evidence))
    return sources + new_sources, evidence + new_evidence, new_usable


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
    """Draft (FAST) and jury (JUDGE) in parallel.
    - Same label: merged verdict (mean confidence). If that label is UNVERIFIED and the reviewers
      proposed queries, one extra search; new usable evidence -> final ruling by JUDGE (recheck).
    - Different labels: extra search with their queries, then final ruling by JUDGE.
    Returns the result plus the (possibly extended) sources and evidence."""
    s = deps.settings
    good = usable(evidence)
    calls = [
        asyncio.ensure_future(verdict(claim_text, good, language, deps, trace,
                              model=s.model_fast, step=f"verdict_draft[claim {claim_id}]")),
        asyncio.ensure_future(verdict(claim_text, good, language, deps, trace,
                              model=s.model_judge, step=f"verdict_jury[claim {claim_id}]")),
    ]  # fmt: skip
    try:
        draft, jury = await asyncio.gather(*calls)
    finally:
        for call in calls:  # if one failed, stop the other instead of leaving it running
            call.cancel()
    agreed = draft.label == jury.label
    emit(
        "verdicts_drafted",
        claim_id=claim_id,
        draft_label=draft.label,
        jury_label=jury.label,
        agreed=agreed,
    )
    extra = _extra_queries(draft, jury, s.max_extra_queries)

    if agreed:
        merged = jury.model_copy(
            update={
                "confidence": round((draft.confidence + jury.confidence) / 2),
                "cited_source_ids": list(
                    dict.fromkeys(jury.cited_source_ids + draft.cited_source_ids)
                ),
            }
        )
        final = post_check(merged, good)
        if final.label != "UNVERIFIED" or not extra:
            result = JuryResult(draft=draft, jury=jury, agreed=True, debated=False, final=final)
            return result, sources, evidence
        emit("recheck_started", claim_id=claim_id, queries=extra)
        sources, evidence, new_usable = await _extra_round(
            claim_id, claim_text, extra, sources, evidence, deps, trace
        )
        if new_usable:
            final = await final_ruling(
                claim_id, claim_text, usable(evidence), draft, jury, language, deps, trace,
                situation=RECHECK,
            )  # fmt: skip
        result = JuryResult(
            draft=draft, jury=jury, agreed=True, debated=True, rechecked=True, final=final
        )
        return result, sources, evidence

    if extra:
        emit("debate_started", claim_id=claim_id, queries=extra)
        sources, evidence, _ = await _extra_round(
            claim_id, claim_text, extra, sources, evidence, deps, trace
        )
    final = await final_ruling(
        claim_id, claim_text, usable(evidence), draft, jury, language, deps, trace
    )
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
    *,
    situation: str = DISAGREED,
) -> Verdict:
    user = render(
        load_prompt("final_ruling"),
        {
            "situation": situation,
            "claim": defuse(claim_text),
            "all_evidence": render_evidence(good),
            "draft.label": draft.label,
            "draft.confidence": draft.confidence,
            "draft.explanation": defuse(draft.explanation),
            "jury.label": jury.label,
            "jury.confidence": jury.confidence,
            "jury.explanation": defuse(jury.explanation),
            "language": language,
        },
    )
    v = await deps.llm.structured(
        trace=trace,
        step=f"final_ruling[claim {claim_id}]",
        model=deps.settings.model_judge,
        system=system_prompt(deps.today()),
        user=f"{user}\n{render(_label_rules(), {'language': language})}",
        schema=Verdict,
    )
    return post_check(v, good)
