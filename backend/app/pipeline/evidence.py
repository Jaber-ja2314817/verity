import asyncio
from typing import TYPE_CHECKING

from ..quotes import verify_quote
from ..schemas import Evidence, EvidenceAssessment, Source
from ..search import collect_sources, normalize_url
from ..trace import Trace
from .ingest import load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps


async def find_sources(
    queries: list[str],
    deps: "Deps",
    *,
    start_id: int = 1,
    exclude: list[Source] | None = None,
) -> list[Source]:
    """Run queries concurrently and merge them into numbered sources."""
    s = deps.settings
    results = await asyncio.gather(*(deps.search.search_web(q) for q in queries))
    return collect_sources(
        list(results),
        max_per_domain=s.max_sources_per_domain,
        max_total=s.max_sources_per_claim,
        source_chars=s.source_chars,
        start_id=start_id,
        exclude_urls={normalize_url(x.url) for x in exclude or []},
    )


def render_sources(sources: list[Source]) -> str:
    return "\n\n".join(
        f'<source id="{x.id}" domain="{x.domain}" title="{x.title}">{x.content}</source>'
        for x in sources
    )


async def assess_evidence(
    claim_text: str, sources: list[Source], deps: "Deps", trace: Trace, step: str
) -> list[Evidence]:
    """One FAST call for all sources. Quotes are verified in code; skipped sources = irrelevant."""
    if not sources:
        return []
    assessment = await deps.llm.structured(
        trace=trace,
        step=step,
        model=deps.settings.model_fast,
        system=system_prompt(deps.today()),
        user=render(
            load_prompt("assess_evidence"),
            {"claim": claim_text, "sources": render_sources(sources)},
        ),
        schema=EvidenceAssessment,
    )
    by_id = {x.id: x for x in sources}
    seen: dict[int, Evidence] = {}
    for item in assessment.items:
        source = by_id.get(item.source_id)
        if source is None or source.id in seen:
            continue
        seen[source.id] = Evidence(
            source=source,
            stance=item.stance,
            quote=item.quote,
            quote_verified=verify_quote(item.quote, source.content),
            note=item.note,
        )
    for source in sources:
        if source.id not in seen:
            seen[source.id] = Evidence(
                source=source, stance="irrelevant", quote="", quote_verified=False, note=""
            )
    return [seen[x.id] for x in sources]


def usable(evidence: list[Evidence]) -> list[Evidence]:
    """Only verified quotes with a real stance reach the verdict and jury steps."""
    return [e for e in evidence if e.quote_verified and e.stance != "irrelevant"]


def discarded_count(evidence: list[Evidence]) -> int:
    return sum(1 for e in evidence if e.stance != "irrelevant" and not e.quote_verified)
