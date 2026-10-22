from typing import TYPE_CHECKING

from ..schemas import Evidence, Verdict
from ..trace import Trace
from .ingest import defuse, load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps

NO_CITATION = "(No verifiable citation)"
# TRUE should cite a "supports" item, FALSE a "refutes" item. MISLEADING may cite any.
NEEDED_STANCE = {"TRUE": "supports", "FALSE": "refutes"}
DOWNGRADED_CONFIDENCE = 30  # max confidence of a verdict post_check turned into UNVERIFIED
# Only a confidence cap, not UNVERIFIED: live runs showed the FAST stance tags are sometimes
# wrong (a source giving 330 m tagged "supports" for "500 m tall") while the verdict is right.
STANCE_MISMATCH_CONFIDENCE = 50
LOW_RELIABILITY_CONFIDENCE = 40  # max confidence of TRUE/FALSE resting only on "low" sources
TITLE_CHARS = 100
DOUBLE_QUOTES = str.maketrans({'"': "'", "“": "'", "”": "'"})


def _evidence_line(e: Evidence) -> str:
    s = e.source
    meta = [f"id {s.id}", e.stance, s.domain, f"reliability {s.reliability}"]
    if s.published_date:
        meta.append(f"published {s.published_date}")
    title = defuse(" ".join(s.title.split())[:TITLE_CHARS].translate(DOUBLE_QUOTES))
    quote = defuse(e.quote.translate(DOUBLE_QUOTES))
    return f'[{" | ".join(meta)}] {title}\n  "{quote}" ({defuse(e.note)})'


def render_evidence(evidence: list[Evidence]) -> str:
    """One compact item per piece of evidence: id, stance, domain, reliability tier, published
    date (when known) and title, then the verified quote and the assessor's note. Prompt tags
    in the (web-derived) text are defused."""
    return "\n".join(_evidence_line(e) for e in evidence)


def post_check(v: Verdict, evidence: list[Evidence]) -> Verdict:
    """Code-side rules on every verdict (draft, jury, merged and final):
    1. confidence is clamped to 0-100; cited ids are deduplicated and must be in `evidence`.
    2. TRUE/FALSE without a valid citation -> UNVERIFIED (confidence <= 30).
    3. TRUE citing no "supports" item, or FALSE citing no "refutes" item: confidence <= 50.
    4. TRUE/FALSE whose cited items are all "low" reliability: confidence <= 40."""
    by_id = {e.source.id: e for e in evidence}
    cited = [i for i in dict.fromkeys(v.cited_source_ids) if i in by_id]
    label, confidence, explanation = v.label, max(0, min(100, v.confidence)), v.explanation
    if label in NEEDED_STANCE and not cited:
        label, confidence = "UNVERIFIED", min(confidence, DOWNGRADED_CONFIDENCE)
        explanation = f"{explanation} {NO_CITATION}".strip()
    elif label in NEEDED_STANCE:
        if not any(by_id[i].stance == NEEDED_STANCE[label] for i in cited):
            confidence = min(confidence, STANCE_MISMATCH_CONFIDENCE)
        if all(by_id[i].source.reliability == "low" for i in cited):
            confidence = min(confidence, LOW_RELIABILITY_CONFIDENCE)
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
            {
                "language": language,
                "claim": defuse(claim_text),
                "evidence": render_evidence(evidence),
            },
        ),
        schema=Verdict,
    )
    return post_check(v, evidence)
