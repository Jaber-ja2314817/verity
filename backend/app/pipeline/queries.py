from typing import TYPE_CHECKING

from ..schemas import ExtractedClaim, PlannedQuery, QueryPlan
from ..trace import Trace
from .ingest import load_prompt, render, system_prompt

if TYPE_CHECKING:
    from .orchestrator import Deps


async def plan_queries(claim: ExtractedClaim, deps: "Deps", trace: Trace) -> list[PlannedQuery]:
    n = deps.settings.queries_per_claim
    plan = await deps.llm.structured(
        trace=trace,
        step=f"plan_queries[claim {claim.id}]",
        model=deps.settings.model_fast,
        system=system_prompt(deps.today()),
        user=render(load_prompt("plan_queries"), {"n": n, "claim": claim.text}),
        schema=QueryPlan,
    )
    queries = [q for q in plan.queries if q.query.strip()][:n]
    if len(queries) < n:
        queries.append(PlannedQuery(query=claim.text, intent="neutral"))
    return queries
