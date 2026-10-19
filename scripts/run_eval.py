"""Benchmark: single model vs two-model jury on the labeled claims in eval/claims.jsonl.

For each claim, the shared steps (plan queries -> search -> assess evidence) run ONCE, so both
modes judge exactly the same sources and verified quotes. Then:
  single = draft verdict from MODEL_FAST only (same post-checks, no jury, no debate)
  jury   = the full jury step: FAST draft + independent JUDGE verdict, debate round on disagreement
The shared steps' cost and time are counted in both modes.

Usage (from the repo root):
  .venv/bin/python scripts/run_eval.py [--limit N] [--modes single,jury] [--concurrency 2]
      [--claims eval/claims.jsonl] [--resume eval/results/run_X.jsonl]

Never edit results by hand. Report whatever the numbers are.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app.config import Settings, startup_problems  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.pipeline.evidence import assess_evidence, find_sources, usable  # noqa: E402
from app.pipeline.jury import run_jury  # noqa: E402
from app.pipeline.orchestrator import Deps  # noqa: E402
from app.pipeline.queries import plan_queries  # noqa: E402
from app.pipeline.verdict import verdict  # noqa: E402
from app.schemas import Evidence, ExtractedClaim, Source  # noqa: E402
from app.search import Search  # noqa: E402
from app.store import Store  # noqa: E402
from app.trace import Trace  # noqa: E402

DEFAULT_CLAIMS = ROOT / "eval" / "claims.jsonl"
DRAFT_CLAIMS = ROOT / "eval" / "claims_draft.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
MODES = ("single", "jury")
LANGUAGE = "en"
CORRECTNESS_RULE = (
    "A prediction is correct when it matches the label (TRUE->TRUE, FALSE->FALSE). "
    "MISLEADING counts as correct for FALSE claims. UNVERIFIED is an abstention and counts as "
    "not correct in accuracy; 'accuracy when answered' leaves abstentions out."
)


# ---------------------------------------------------------------- metrics (pure functions)


def is_correct(expected: str, predicted: str | None) -> bool:
    return predicted == expected or (expected == "FALSE" and predicted == "MISLEADING")


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def compute_metrics(records: list[dict], mode: str) -> dict[str, Any]:
    """Metrics for one mode. Records with an error are excluded and counted separately."""
    mine = [r for r in records if r["mode"] == mode]
    ok = [r for r in mine if not r.get("error")]
    n = len(ok)
    correct = sum(1 for r in ok if is_correct(r["expected"], r["predicted"]))
    abstained = sum(1 for r in ok if r["predicted"] == "UNVERIFIED")
    m: dict[str, Any] = {
        "n": n,
        "errors": len(mine) - n,
        "correct": correct,
        "abstained": abstained,
        "accuracy": _ratio(correct, n),
        "abstain_rate": _ratio(abstained, n),
        "accuracy_when_answered": _ratio(correct, n - abstained),
        "avg_cost_usd": _avg([r["cost_usd"] for r in ok if r.get("cost_usd") is not None]),
        "avg_time_s": _avg([r["duration_s"] for r in ok]),
    }
    if mode == "jury":
        m["agreement_rate"] = _ratio(sum(1 for r in ok if r.get("agreed")), n)
        m["debate_rate"] = _ratio(sum(1 for r in ok if r.get("debated")), n)
    return {k: v for k, v in m.items() if v is not None}


def build_summary(
    records: list[dict], *, models: dict[str, str], date: str, claims_total: int
) -> dict[str, Any]:
    modes = [m for m in MODES if any(r["mode"] == m for r in records)]
    per_mode = {m: compute_metrics(records, m) for m in modes}
    n = max((v["n"] for v in per_mode.values()), default=0)
    return {
        **per_mode,
        "n": n,
        "claims_total": claims_total,
        "date": date,
        "models": models,
        "rule": CORRECTNESS_RULE,
        "description": (
            f"{n} human-labeled claims (half TRUE, half FALSE) across science, health, history, "
            "geography and technology. Both modes judge the same sources and verified quotes: "
            "the single mode uses only the fast model's verdict, the jury adds an independent "
            "Nemotron Ultra verdict and a debate round when they disagree. "
            "MISLEADING counts as correct for FALSE claims; UNVERIFIED is an abstention."
        ),
    }


def _fmt(v: Any, kind: str) -> str:
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "usd":
        return f"${v:.4f}"
    if kind == "s":
        return f"{v:.1f} s"
    return str(v)


def render_markdown(summary: dict[str, Any]) -> str:
    rows = [
        ("Claims evaluated", "n", ""),
        ("Accuracy", "accuracy", "pct"),
        ("Abstain rate (UNVERIFIED)", "abstain_rate", "pct"),
        ("Accuracy when answered", "accuracy_when_answered", "pct"),
        ("Avg. cost per claim", "avg_cost_usd", "usd"),
        ("Avg. time per claim", "avg_time_s", "s"),
        ("Jury agreement rate", "agreement_rate", "pct"),
        ("Debate rate", "debate_rate", "pct"),
        ("Errors (excluded)", "errors", ""),
    ]
    modes = [m for m in MODES if m in summary]
    models = summary["models"]
    head = "| Metric | " + " | ".join("Single model" if m == "single" else "Two-model jury"
                                     for m in modes) + " |"  # fmt: skip
    lines = [
        "# Verity benchmark",
        "",
        f"- Date: {summary['date']}",
        f"- Claims: {summary['n']} (of {summary['claims_total']} in the file)",
        f"- Models: fast `{models.get('fast')}`, judge `{models.get('judge')}`",
        f"- Rule: {summary['rule']}",
        "",
        head,
        "|---|" + "---|" * len(modes),
    ]
    for title, key, kind in rows:
        if any(key in summary[m] for m in modes):
            cells = " | ".join(_fmt(summary[m].get(key), kind) for m in modes)
            lines.append(f"| {title} | {cells} |")
    lines += ["", "Generated by `scripts/run_eval.py`. Do not edit by hand.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- running claims


@dataclass
class Prepared:
    """Shared per-claim steps: same sources and evidence for both modes."""

    sources: list[Source]
    evidence: list[Evidence]
    trace: Trace
    duration_s: float
    settled: tuple[str, int] | None = None  # (label, confidence) decided in code, no verdict call


async def prepare(claim: ExtractedClaim, deps: Deps) -> Prepared:
    trace = Trace(prices=deps.settings.prices)
    t0 = time.perf_counter()
    queries = await plan_queries(claim, deps, trace)
    sources = await find_sources([q.query for q in queries], deps, claim=claim.text)
    evidence: list[Evidence] = []
    settled = None
    if not sources:
        settled = ("UNVERIFIED", 0)
    else:
        evidence = await assess_evidence(
            claim.text, sources, deps, trace, f"assess_evidence[claim {claim.id}]"
        )
        if not usable(evidence):
            settled = ("UNVERIFIED", 10)
    return Prepared(sources, evidence, trace, time.perf_counter() - t0, settled)


async def run_mode(claim: ExtractedClaim, prep: Prepared, mode: str, deps: Deps) -> dict:
    """Verdict step for one mode. Returns predicted label, confidence, agreed/debated, cost."""
    trace = Trace(prices=deps.settings.prices)
    t0 = time.perf_counter()
    agreed = debated = None
    if prep.settled:
        label, confidence = prep.settled
        if mode == "jury":
            agreed, debated = True, False
    elif mode == "single":
        v = await verdict(
            claim.text, usable(prep.evidence), LANGUAGE, deps, trace,
            model=deps.settings.model_fast, step=f"verdict_draft[claim {claim.id}]",
        )  # fmt: skip
        label, confidence = v.label, v.confidence
    else:
        result, _, _ = await run_jury(
            claim.id, claim.text, prep.sources, prep.evidence, LANGUAGE, deps, trace,
            emit=lambda *a, **k: None,
        )  # fmt: skip
        label, confidence = result.final.label, result.final.confidence
        agreed, debated = result.agreed, result.debated
    costs = [e.cost_usd for e in prep.trace.entries + trace.entries]
    return {
        "predicted": label,
        "confidence": confidence,
        "agreed": agreed,
        "debated": debated,
        "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 6),
        "duration_s": round(prep.duration_s + time.perf_counter() - t0, 2),
        "model_calls": len(prep.trace.entries) + len(trace.entries),
    }


async def evaluate_claim(item: dict, modes: list[str], deps: Deps) -> list[dict]:
    """Run the shared steps once, then each requested mode. Errors are recorded, not raised."""
    claim = ExtractedClaim(id=1, text=item["claim"], checkworthy=True, reason="benchmark")
    base = {"id": item["id"], "claim": item["claim"], "expected": item["label"]}
    try:
        prep = await prepare(claim, deps)
    except Exception as e:  # noqa: BLE001 - recorded per item, run continues
        return [{**base, "mode": m, "predicted": None, "correct": False,
                 "error": f"{type(e).__name__}: {str(e)[:300]}"} for m in modes]  # fmt: skip
    out = []
    for mode in modes:
        try:
            r = await run_mode(claim, prep, mode, deps)
            correct = is_correct(item["label"], r["predicted"])
            out.append({**base, "mode": mode, **r, "correct": correct, "error": None})
        except Exception as e:  # noqa: BLE001
            out.append({**base, "mode": mode, "predicted": None, "correct": False,
                        "error": f"{type(e).__name__}: {str(e)[:300]}"})  # fmt: skip
    return out


async def run_all(
    claims: list[dict],
    modes: list[str],
    deps: Deps,
    *,
    done: set[tuple[str, str]],
    concurrency: int,
    on_record=None,
) -> list[dict]:
    """Evaluate claims concurrently, skipping (id, mode) pairs already in `done`."""
    sem = asyncio.Semaphore(concurrency)
    records: list[dict] = []

    async def one(item: dict) -> None:
        pending = [m for m in modes if (item["id"], m) not in done]
        if not pending:
            return
        async with sem:
            for r in await evaluate_claim(item, pending, deps):
                records.append(r)
                if on_record:
                    on_record(r)

    await asyncio.gather(*(one(c) for c in claims))
    return records


# ---------------------------------------------------------------- files


def load_claims(path: Path) -> list[dict]:
    claims = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if (
            item.get("label") not in ("TRUE", "FALSE")
            or not item.get("claim")
            or not item.get("id")
        ):
            raise ValueError(f"{path.name} line {i}: need id, claim and label TRUE|FALSE")
        claims.append(item)
    ids = [c["id"] for c in claims]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: duplicate ids")
    return claims


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_outputs(summary: dict, records: list[dict], results_dir: Path, stamp: str) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    full = {**summary, "records": records}
    (results_dir / f"{stamp}.json").write_text(json.dumps(full, indent=2), encoding="utf-8")
    (results_dir / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (results_dir / "latest.md").write_text(render_markdown(summary), encoding="utf-8")


def make_deps(settings: Settings) -> Deps:
    store = Store(settings.data_dir)
    return Deps(
        settings=settings,
        llm=LLM(
            settings.nebius_base_url,
            settings.nebius_api_key,
            modes=settings.structured_modes,
            thinking=settings.thinking,
        ),  # fmt: skip
        search=Search(
            settings.tavily_api_key,
            store,
            depth=settings.tavily_search_depth,
            max_results=settings.tavily_max_results,
            cache_hours=settings.search_cache_hours,
            max_input_chars=settings.max_input_chars,
        ),  # fmt: skip
        store=store,
        events=EventBus(),
        semaphore=asyncio.Semaphore(1),
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--modes", default="single,jury")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--resume", type=Path, default=None, help="run_*.jsonl file to continue")
    args = p.parse_args()

    if not args.claims.exists():
        if args.claims == DEFAULT_CLAIMS:
            print(f"{DEFAULT_CLAIMS.relative_to(ROOT)} not found.\n"
                  f"Verify every label in {DRAFT_CLAIMS.relative_to(ROOT)} (see "
                  "eval/VERIFY_CLAIMS.md), then save it as eval/claims.jsonl.")  # fmt: skip
        else:
            print(f"Claims file not found: {args.claims}")
        return 1
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    if not modes or any(m not in MODES for m in modes):
        print(f"--modes must be a comma list of: {', '.join(MODES)}")
        return 1

    settings = Settings()
    problems = startup_problems(settings)
    if problems:
        print("Cannot run the benchmark:\n  " + "\n  ".join(problems))
        return 1

    claims = load_claims(args.claims)[: args.limit]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_file = args.resume or RESULTS_DIR / f"run_{stamp}.jsonl"
    previous = [r for r in load_records(run_file) if not r.get("error")]  # errors are retried
    done = {(r["id"], r["mode"]) for r in previous}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{len(claims)} claims, modes {modes}, {len(done)} results already done -> {run_file}")

    def save(r: dict) -> None:
        with run_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        mark = "ERROR" if r["error"] else ("ok " if r["correct"] else "MISS")
        print(f"  {r['id']} {r['mode']:6} {mark} expected {r['expected']:5} got {r['predicted']}")

    new = asyncio.run(
        run_all(
            claims,
            modes,
            make_deps(settings),
            done=done,
            concurrency=args.concurrency,
            on_record=save,
        )  # fmt: skip
    )
    ids = {c["id"] for c in claims}
    records = [r for r in previous + [r for r in new if not r["error"]] if r["id"] in ids]
    records += [r for r in new if r["error"]]
    summary = build_summary(
        records,
        models={"fast": settings.model_fast, "judge": settings.model_judge},
        date=datetime.now(UTC).date().isoformat(),
        claims_total=len(claims),
    )
    write_outputs(summary, records, RESULTS_DIR, stamp)
    print("\n" + render_markdown(summary))
    errors = sum(1 for r in records if r["error"])
    if errors:
        print(f"{errors} results had errors. Re-run with --resume {run_file} to retry them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
