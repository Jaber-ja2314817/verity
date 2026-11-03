from typing import TYPE_CHECKING

from ..schemas import ExtractedClaim, PlannedQuery, QueryPlan
from ..trace import Trace
from .ingest import defuse, load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps


async def plan_queries(claim: ExtractedClaim, deps: "Deps", trace: Trace) -> list[PlannedQuery]:
    """n distinct queries from FAST; padded with the claim text if it returns too few."""
    queries, _ = await plan_searches(claim, deps, trace)
    return queries


async def plan_searches(
    claim: ExtractedClaim, deps: "Deps", trace: Trace
) -> tuple[list[PlannedQuery], bool]:
    """plan_queries plus FAST's call on whether the claim is about a recent event."""
    n = deps.settings.queries_per_claim
    today = deps.today()
    plan = await deps.llm.structured(
        trace=trace,
        step=f"plan_queries[claim {claim.id}]",
        model=deps.settings.model_fast,
        system=system_prompt(today),
        user=render(
            load_prompt("plan_queries"), {"n": n, "claim": defuse(claim.text), "year": today[:4]}
        ),
        schema=QueryPlan,
    )
    seen: set[str] = set()
    queries: list[PlannedQuery] = []
    for q in plan.queries:
        key = " ".join(q.query.lower().split())
        if key and key not in seen:
            seen.add(key)
            queries.append(q.model_copy(update={"query": q.query.strip()}))
    queries = queries[:n]
    if len(queries) < n and " ".join(claim.text.lower().split()) not in seen:
        queries.append(PlannedQuery(query=claim.text, intent="neutral"))
    return queries, plan.time_sensitive
