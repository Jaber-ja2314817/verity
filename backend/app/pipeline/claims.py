import re
from typing import TYPE_CHECKING

from ..schemas import ClaimExtraction, ExtractedClaim
from ..trace import Trace
from .ingest import defuse, load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps

# "en", "pt-BR" or a language name. Anything else is not a language: the value is placed in
# later prompts outside the untrusted-data tags, so it must not be able to carry instructions.
LANGUAGE_RE = re.compile(r"[A-Za-z][A-Za-z_-]{1,19}")
DEFAULT_LANGUAGE = "en"


async def extract_claims(text: str, deps: "Deps", trace: Trace) -> ClaimExtraction:
    s = deps.settings
    user = render(
        load_prompt("extract_claims"),
        {"max_claims_plus_two": s.max_claims + 2, "text": defuse(text)},
    )
    extraction = await deps.llm.structured(
        trace=trace,
        step="extract_claims",
        model=s.model_fast,
        system=system_prompt(deps.today()),
        user=user,
        schema=ClaimExtraction,
        thinking=True,  # without reasoning FAST adds claims the input never made; input is short
    )
    language = extraction.language.strip()
    if not LANGUAGE_RE.fullmatch(language):
        language = DEFAULT_LANGUAGE
    return extraction.model_copy(update={"language": language})


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def select_claims(
    extraction: ClaimExtraction, max_claims: int
) -> tuple[list[ExtractedClaim], list[ExtractedClaim]]:
    """Keep the first max_claims checkworthy claims, renumbered 1..N. The rest are skipped.
    A claim repeated word for word is checked once (the model does not always merge them)."""
    kept: list[ExtractedClaim] = []
    skipped: list[ExtractedClaim] = []
    seen: set[str] = set()
    for c in extraction.claims:
        key = _key(c.text)
        if c.checkworthy and key and key in seen:
            continue
        if c.checkworthy and key and len(kept) < max_claims:
            seen.add(key)
            kept.append(c.model_copy(update={"id": len(kept) + 1}))
        else:
            skipped.append(c)
    return kept, skipped
