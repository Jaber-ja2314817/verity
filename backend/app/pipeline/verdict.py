from typing import TYPE_CHECKING

from ..schemas import Evidence, Verdict
from ..trace import Trace
from .ingest import load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps

NO_CITATION = "(No verifiable citation)"


def render_evidence(evidence: list[Evidence]) -> str:
    return "\n".join(
        f'[id {e.source.id} | {e.source.domain} | {e.stance}] "{e.quote}" ({e.note})'
        for e in evidence
    )


def post_check(v: Verdict, valid_ids: set[int]) -> Verdict:
    """Code-side rules on every verdict: valid citations only, no TRUE/FALSE without one."""
    cited = [i for i in dict.fromkeys(v.cited_source_ids) if i in valid_ids]
    label, confidence, explanation = v.label, max(0, min(100, v.confidence)), v.explanation
    if label in ("TRUE", "FALSE") and not cited:
        label, confidence = "UNVERIFIED", min(confidence, 30)
        explanation = f"{explanation} {NO_CITATION}".strip()
    return v.model_copy(
        update={
            "label": label,
            "confidence": confidence,
            "explanation": explanation,
            "cited_source_ids": cited,
        }
    )


async def verdict(
    claim_text: str,
    evidence: list[Evidence],
    language: str,
    deps: "Deps",
    trace: Trace,
    *,
    model: str,
    step: str,
) -> Verdict:
    """Same prompt for the FAST draft and the independent JUDGE jury; post-checked."""
    v = await deps.llm.structured(
        trace=trace,
        step=step,
        model=model,
        system=system_prompt(deps.today()),
        user=render(
            load_prompt("verdict"),
            {"language": language, "claim": claim_text, "evidence": render_evidence(evidence)},
        ),
        schema=Verdict,
    )
    return post_check(v, {e.source.id for e in evidence})
