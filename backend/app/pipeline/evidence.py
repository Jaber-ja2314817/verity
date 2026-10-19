import asyncio
import logging
import re
from typing import TYPE_CHECKING

from ..quotes import find_quote, normalize
from ..schemas import Evidence, EvidenceAssessment, Source, SourceAssessment
from ..search import collect_sources, normalize_url
from ..trace import Trace
from .ingest import load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps

log = logging.getLogger(__name__)


async def find_sources(
    queries: list[str],
    deps: "Deps",
    *,
    claim: str,
    start_id: int = 1,
    exclude: list[Source] | None = None,
) -> list[Source]:
    """Run queries concurrently and merge them into numbered sources for this claim, each cut
    to its passages most relevant to the claim. A failed query is skipped (logged) unless all
    of them fail."""
    s = deps.settings
    outcomes = await asyncio.gather(
        *(deps.search.search_web(q) for q in queries), return_exceptions=True
    )
    failures = [o for o in outcomes if isinstance(o, BaseException)]
    if failures and len(failures) == len(outcomes):
        raise failures[0]
    for e in failures:
        log.warning("search query failed: %r", e)
    return collect_sources(
        [o for o in outcomes if not isinstance(o, BaseException)],
        max_per_domain=s.max_sources_per_domain,
        max_total=s.max_sources_per_claim,
        source_chars=s.source_chars,
        claim=claim,
        start_id=start_id,
        exclude_urls={normalize_url(x.url) for x in exclude or []},
    )


DOUBLE_QUOTES = str.maketrans({'"': "'", "\u201c": "'", "\u201d": "'"})


def render_sources(sources: list[Source]) -> str:
    """Double quotes become single quotes: a model copying a quote containing " into a JSON
    string can break the JSON and degenerate. verify_quote ignores punctuation, so it still
    matches the original source text. Source tags inside page text are defused so a page
    cannot fake the end of its own source block. "[...]" marks a gap between passages."""
    return "\n\n".join(
        f'<source id="{x.id}" domain="{x.domain}" reliability="{x.reliability}"'
        + (f' published="{x.published_date}"' if x.published_date else "")
        + f' title="{_defuse(x.title)}">{_defuse(x.content)}</source>'
        for x in sources
    )


def _defuse(text: str) -> str:
    return re.sub(r"<(/?)source", r"<\1 source", text.translate(DOUBLE_QUOTES), flags=re.I)


async def assess_evidence(
    claim_text: str, sources: list[Source], deps: "Deps", trace: Trace, step: str
) -> list[Evidence]:
    """One FAST call for all sources, plus one retry for sources the model left out (small
    models drop items from long lists). Quotes are matched to the exact source text in code;
    sources still missing count as irrelevant."""
    if not sources:
        return []
    items = await _assess(claim_text, sources, deps, trace, step)
    missing = [x for x in sources if x.id not in {i.source_id for i in items}]
    if missing:
        log.warning("%s: model skipped sources %s, asking again", step, [x.id for x in missing])
        items += await _assess(claim_text, missing, deps, trace, f"{step} retry")
    by_id = {x.id: x for x in sources}
    seen: dict[int, Evidence] = {}
    for item in items:
        source = by_id.get(item.source_id)
        if source is None or source.id in seen:
            continue
        quote = find_quote(item.quote, source.content)
        seen[source.id] = Evidence(
            source=source,
            stance=item.stance,
            quote=quote or item.quote,  # unverified quotes are kept for the trace only
            quote_verified=quote is not None,
            note=item.note,
        )
    for source in sources:
        if source.id not in seen:
            seen[source.id] = Evidence(
                source=source, stance="irrelevant", quote="", quote_verified=False, note=""
            )
    return [seen[x.id] for x in sources]


async def _assess(
    claim_text: str, sources: list[Source], deps: "Deps", trace: Trace, step: str
) -> list[SourceAssessment]:
    ids = ", ".join(str(x.id) for x in sources)
    assessment = await deps.llm.structured(
        trace=trace,
        step=step,
        model=deps.settings.model_fast,
        system=system_prompt(deps.today()),
        user=render(
            load_prompt("assess_evidence"),
            {
                "claim": claim_text,
                "sources": render_sources(sources),
                "count": len(sources),
                "ids": ids,
            },
        ),
        schema=EvidenceAssessment,
        # No reasoning: in tests it took 30-46 s and 6-10k tokens per call for no better
        # stances (docs/FEEDBACK.md, 2026-10-19).
        thinking=False,
    )
    return assessment.items


RELIABILITY_RANK = {"high": 0, "medium": 1, "unknown": 2, "low": 3}


def usable(evidence: list[Evidence]) -> list[Evidence]:
    """Only verified quotes with a real stance reach the verdict and jury steps, most reliable
    sources first. A quote that mirror sites repeat word for word counts once."""
    good = [e for e in evidence if e.quote_verified and e.stance != "irrelevant"]
    good.sort(key=lambda e: RELIABILITY_RANK.get(e.source.reliability, 2))  # stable
    seen: set[str] = set()
    out = []
    for e in good:
        key = normalize(e.quote)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def discarded_count(evidence: list[Evidence]) -> int:
    return sum(1 for e in evidence if e.stance != "irrelevant" and not e.quote_verified)
