import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from conftest import FakeLLM, FakeSearch, raw_result

from app.config import Settings
from app.events import EventBus
from app.pipeline.orchestrator import Deps
from app.schemas import EvidenceAssessment, PlannedQuery, QueryPlan, SourceAssessment, Verdict
from app.store import Store

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_eval.py"
_spec = importlib.util.spec_from_file_location("run_eval", SCRIPT)
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

FAST, JUDGE = "nvidia/fast", "nvidia/judge"
QUOTE = "Water boils at one hundred degrees Celsius at sea level."
PAGE = f"Intro. {QUOTE} More text."


def rec(id_, mode, expected, predicted, **kw):
    base = {"id": id_, "mode": mode, "expected": expected, "predicted": predicted,
            "cost_usd": 0.01, "duration_s": 2.0, "error": None}  # fmt: skip
    return base | kw


# ---- pure metrics


@pytest.mark.parametrize(
    "expected,predicted,ok",
    [("TRUE", "TRUE", True), ("FALSE", "FALSE", True), ("FALSE", "MISLEADING", True),
     ("TRUE", "MISLEADING", False), ("TRUE", "UNVERIFIED", False), ("TRUE", None, False)],
)  # fmt: skip
def test_is_correct(expected, predicted, ok):
    assert ev.is_correct(expected, predicted) is ok


def test_compute_metrics_single():
    records = [
        rec("a", "single", "TRUE", "TRUE"),
        rec("b", "single", "FALSE", "MISLEADING", cost_usd=0.03, duration_s=4.0),
        rec("c", "single", "TRUE", "UNVERIFIED"),
        rec("d", "single", "FALSE", "TRUE"),
        rec("e", "single", "TRUE", None, error="boom"),
        rec("a", "jury", "TRUE", "TRUE"),
    ]
    m = ev.compute_metrics(records, "single")
    assert m["n"] == 4 and m["errors"] == 1 and m["correct"] == 2 and m["abstained"] == 1
    assert m["accuracy"] == 0.5
    assert m["abstain_rate"] == 0.25
    assert m["accuracy_when_answered"] == pytest.approx(0.6667)
    assert m["avg_cost_usd"] == pytest.approx(0.015)
    assert m["avg_time_s"] == pytest.approx(2.5)
    assert "agreement_rate" not in m


def test_compute_metrics_jury_rates_and_unknown_cost():
    records = [
        rec("a", "jury", "TRUE", "TRUE", agreed=True, debated=False, cost_usd=None),
        rec("b", "jury", "FALSE", "FALSE", agreed=False, debated=True, cost_usd=None),
    ]
    m = ev.compute_metrics(records, "jury")
    assert m["agreement_rate"] == 0.5 and m["debate_rate"] == 0.5
    assert "avg_cost_usd" not in m  # never invent numbers


def test_summary_shape_matches_benchmark_page_and_markdown():
    records = [rec("a", "single", "TRUE", "TRUE"), rec("a", "jury", "TRUE", "TRUE",
                                                        agreed=True, debated=False)]  # fmt: skip
    s = ev.build_summary(records, models={"fast": FAST, "judge": JUDGE},
                         date="2026-10-23", claims_total=1)  # fmt: skip
    for mode in ("single", "jury"):
        assert {"accuracy", "abstain_rate", "avg_cost_usd", "avg_time_s"} <= set(s[mode])
    assert s["n"] == 1 and s["date"] == "2026-10-23" and "MISLEADING" in s["rule"]
    assert isinstance(s["description"], str)
    md = ev.render_markdown(s)
    assert "| Accuracy | 100.0% | 100.0% |" in md and "Do not edit by hand" in md


def test_empty_summary_has_no_modes():
    s = ev.build_summary([], models={}, date="d", claims_total=0)
    assert "single" not in s and "jury" not in s and s["n"] == 0


def test_load_claims_validates(tmp_path):
    good = tmp_path / "c.jsonl"
    good.write_text('{"id":"c01","claim":"x","label":"TRUE","evidence_url":"u"}\n\n')
    assert ev.load_claims(good)[0]["id"] == "c01"
    bad = tmp_path / "b.jsonl"
    bad.write_text('{"id":"c01","claim":"x","label":"MISLEADING"}\n')
    with pytest.raises(ValueError):
        ev.load_claims(bad)
    dup = tmp_path / "d.jsonl"
    dup.write_text(
        '{"id":"c1","claim":"x","label":"TRUE"}\n{"id":"c1","claim":"y","label":"FALSE"}\n'
    )
    with pytest.raises(ValueError):
        ev.load_claims(dup)


def test_write_outputs(tmp_path):
    s = ev.build_summary([rec("a", "single", "TRUE", "TRUE")], models={"fast": FAST},
                         date="d", claims_total=1)  # fmt: skip
    ev.write_outputs(s, [rec("a", "single", "TRUE", "TRUE")], tmp_path, "stamp")
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert "records" not in latest and latest["single"]["accuracy"] == 1.0
    assert "records" in json.loads((tmp_path / "stamp.json").read_text())
    assert (tmp_path / "latest.md").exists()


# ---- runners with fakes


@pytest.fixture
def deps(tmp_path, fake_llm: FakeLLM) -> Deps:
    search = FakeSearch(default=[raw_result("https://a.org/x", PAGE, 0.9)])
    return Deps(
        settings=Settings(_env_file=None, model_fast=FAST, model_judge=JUDGE,
                          nebius_api_key="k", tavily_api_key="t"),  # fmt: skip
        llm=fake_llm, search=search, store=Store(tmp_path), events=EventBus(),
        semaphore=asyncio.Semaphore(1), today=lambda: "2026-10-23",
    )  # fmt: skip


def queue_shared(llm: FakeLLM, stance="supports"):
    llm.queue(
        "plan_queries[claim 1]",
        QueryPlan(queries=[PlannedQuery(query="water boiling point", intent="neutral")]),
    )
    llm.queue("assess_evidence[claim 1]", EvidenceAssessment(items=[
        SourceAssessment(source_id=1, stance=stance, quote=QUOTE, note="n")]))  # fmt: skip


def v(label, ids=(1,)):
    return Verdict(label=label, confidence=80, explanation="e", cited_source_ids=list(ids))


ITEM = {"id": "c01", "claim": "Water boils at 100 C at sea level.", "label": "TRUE"}


async def test_single_and_jury_share_evidence(deps, fake_llm):
    queue_shared(fake_llm)
    fake_llm.queue("verdict_draft[claim 1]", v("TRUE"), v("TRUE"))
    fake_llm.queue("verdict_jury[claim 1]", v("TRUE"))
    out = await ev.evaluate_claim(ITEM, ["single", "jury"], deps)
    by = {r["mode"]: r for r in out}
    assert by["single"]["predicted"] == "TRUE" and by["single"]["correct"]
    assert by["single"]["agreed"] is None
    assert by["jury"]["agreed"] is True and by["jury"]["debated"] is False
    steps = [c["step"] for c in fake_llm.calls]
    assert steps.count("plan_queries[claim 1]") == 1  # shared steps ran once
    assert steps.count("assess_evidence[claim 1]") == 1
    single_models = {c["model"] for c in fake_llm.calls if c["step"] == "verdict_draft[claim 1]"}
    assert single_models == {FAST}
    assert by["single"]["model_calls"] == 3 and by["jury"]["model_calls"] == 4


async def test_jury_disagreement_uses_final_ruling(deps, fake_llm):
    queue_shared(fake_llm)
    fake_llm.queue("verdict_draft[claim 1]", v("TRUE"))
    fake_llm.queue("verdict_jury[claim 1]", v("FALSE"))
    fake_llm.queue("final_ruling[claim 1]", v("TRUE"))
    [r] = await ev.evaluate_claim(ITEM, ["jury"], deps)
    assert r["predicted"] == "TRUE" and r["agreed"] is False and r["debated"] is False


async def test_no_usable_evidence_settles_without_verdict(deps, fake_llm):
    queue_shared(fake_llm, stance="irrelevant")
    out = await ev.evaluate_claim(ITEM, ["single", "jury"], deps)
    assert [r["predicted"] for r in out] == ["UNVERIFIED", "UNVERIFIED"]
    assert not any("verdict" in c["step"] for c in fake_llm.calls)


async def test_errors_are_recorded_not_raised(deps, fake_llm):
    fake_llm.queue("plan_queries[claim 1]", RuntimeError("api down"))
    out = await ev.evaluate_claim(ITEM, ["single", "jury"], deps)
    assert all(r["error"] and "api down" in r["error"] for r in out)
    assert all(r["correct"] is False for r in out)


async def test_run_all_skips_done_pairs(deps, fake_llm):
    queue_shared(fake_llm)
    fake_llm.queue("verdict_draft[claim 1]", v("TRUE"))
    fake_llm.queue("verdict_jury[claim 1]", v("TRUE"))
    other = {"id": "c02", "claim": "Done already.", "label": "FALSE"}
    seen = []
    records = await ev.run_all([ITEM, other], ["single", "jury"], deps,
                               done={("c01", "single"), ("c02", "single"), ("c02", "jury")},
                               concurrency=2, on_record=seen.append)  # fmt: skip
    assert [(r["id"], r["mode"]) for r in records] == [("c01", "jury")]
    assert seen == records


# ---- command line and output guards


def test_write_outputs_can_leave_latest_alone(tmp_path):
    s = ev.build_summary([rec("a", "single", "TRUE", "TRUE")], models={}, date="d",
                         claims_total=1)  # fmt: skip
    ev.write_outputs(s, [], tmp_path, "stamp", latest=False)
    assert (tmp_path / "stamp.json").exists() and not (tmp_path / "latest.json").exists()


def test_latest_only_for_full_runs_of_the_verified_claims(tmp_path):
    assert ev.latest_skip_reason(ev.DEFAULT_CLAIMS, None, 40) is None
    assert "--limit" in ev.latest_skip_reason(ev.DEFAULT_CLAIMS, 5, 5)
    assert "no claim" in ev.latest_skip_reason(ev.DEFAULT_CLAIMS, None, 0)
    assert "not eval/claims.jsonl" in ev.latest_skip_reason(ev.DRAFT_CLAIMS, None, 40)


@pytest.mark.parametrize(
    "argv, message",
    [(["--concurrency", "0"], "--concurrency must be at least 1"),
     (["--limit", "0"], "--limit must be at least 1"),
     (["--resume", "/nonexistent/run_x.jsonl"], "--resume file not found"),
     (["--claims", "/nonexistent/c.jsonl"], "Claims file not found"),
     (["--claims", str(SCRIPT), "--modes", "single,both"], "--modes must be")],
)  # fmt: skip
def test_main_rejects_bad_arguments_before_any_work(argv, message, capsys):
    assert ev.main(argv) == 1
    assert message in capsys.readouterr().out
