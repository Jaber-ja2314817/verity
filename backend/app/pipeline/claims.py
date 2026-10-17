from typing import TYPE_CHECKING

from ..schemas import ClaimExtraction, ExtractedClaim
from ..trace import Trace
from .ingest import load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps


async def extract_claims(text: str, deps: "Deps", trace: Trace) -> ClaimExtraction:
    s = deps.settings
    user = render(
        load_prompt("extract_claims"), {"max_claims_plus_two": s.max_claims + 2, "text": text}
    )
    return await deps.llm.structured(
        trace=trace,
        step="extract_claims",
        model=s.model_fast,
        system=system_prompt(deps.today()),
        user=user,
        schema=ClaimExtraction,
        thinking=True,  # without reasoning FAST adds claims the input never made; input is short
    )


def select_claims(
    extraction: ClaimExtraction, max_claims: int
) -> tuple[list[ExtractedClaim], list[ExtractedClaim]]:
    """Keep the first max_claims checkworthy claims, renumbered 1..N. The rest are skipped."""
    worthy = [c for c in extraction.claims if c.checkworthy and c.text.strip()]
    kept = [c.model_copy(update={"id": i}) for i, c in enumerate(worthy[:max_claims], start=1)]
    skipped = [c for c in extraction.claims if c not in worthy[:max_claims]]
    return kept, skipped
