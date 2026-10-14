"""Probe NVIDIA Nemotron models on Nebius Token Factory.

Tests each candidate model for plain chat, the three structured-output modes, reasoning output,
latency and token usage. Writes docs/model_probe.md and prints recommended .env values.

Usage (from the repo root):  .venv/bin/python scripts/probe_models.py [--models ID ID ...]
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app.config import Settings, StructuredMode  # noqa: E402
from app.jsonutil import strip_think  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.schemas import Verdict  # noqa: E402
from app.trace import Trace  # noqa: E402

BACKUPS = [
    "nvidia/Nemotron-3_5-Lightning",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "nvidia/Nemotron-3-Ultra-550b-a55b",
]
MODES: list[StructuredMode] = ["tool_forced", "tool_auto", "text_json"]

VERDICT_SYSTEM = (
    "You are a fact-checker. Judge the claim using only the numbered sources. "
    "Cite the source ids you rely on."
)
VERDICT_USER = (
    "Claim: The Eiffel Tower is in Paris.\n\n"
    "Sources:\n[1] The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars "
    "in Paris, France. It is named after the engineer Gustave Eiffel."
)


@dataclass
class ModeResult:
    ok: bool = False
    label: str = ""
    latency_s: float = 0.0
    tokens: str = ""
    error: str = ""


@dataclass
class ModelResult:
    model: str
    chat_ok: bool = False
    chat_reply: str = ""
    chat_latency_s: float = 0.0
    chat_tokens: str = ""
    chat_error: str = ""
    think_in_content: bool = False
    reasoning_field: bool = False
    modes: dict[str, ModeResult] = field(default_factory=dict)

    def best_mode(self) -> StructuredMode | None:
        return next((m for m in MODES if self.modes.get(m, ModeResult()).ok), None)


def short(e: Exception) -> str:
    text = f"{type(e).__name__}: {e}".replace("\n", " ").replace("|", "/")
    return text[:120]


def tokens_of(usage: object) -> str:
    return f"{getattr(usage, 'prompt_tokens', '?')}/{getattr(usage, 'completion_tokens', '?')}"


async def probe_chat(llm: LLM, r: ModelResult) -> None:
    t0 = time.perf_counter()
    try:
        resp = await llm.client.chat.completions.create(
            model=r.model,
            messages=[{"role": "user", "content": "Reply with the word OK"}],
            temperature=0.1,
            max_tokens=1024,
        )
        r.chat_latency_s = time.perf_counter() - t0
        r.chat_tokens = tokens_of(resp.usage)
        msg = resp.choices[0].message
        content = msg.content or ""
        r.think_in_content = "<think>" in content.lower()
        r.reasoning_field = bool(getattr(msg, "reasoning_content", None))
        r.chat_reply = strip_think(content)[:40].replace("\n", " ").replace("|", "/")
        r.chat_ok = "ok" in r.chat_reply.lower()
    except Exception as e:  # noqa: BLE001 - every failure is a probe result
        r.chat_latency_s = time.perf_counter() - t0
        r.chat_error = short(e)


async def probe_mode(llm: LLM, model: str, mode: StructuredMode) -> ModeResult:
    trace = Trace()
    t0 = time.perf_counter()
    res = ModeResult()
    try:
        v = await llm.structured(
            trace=trace, step=f"probe_{mode}", model=model, system=VERDICT_SYSTEM,
            user=VERDICT_USER, schema=Verdict, mode=mode,
        )
        res.ok, res.label = True, v.label
    except Exception as e:  # noqa: BLE001
        res.error = short(e)
    res.latency_s = time.perf_counter() - t0
    totals = trace.totals()
    res.tokens = f"{totals['input_tokens']}/{totals['output_tokens']}"
    return res


async def probe_model(llm: LLM, model: str) -> ModelResult:
    r = ModelResult(model=model)
    print(f"\n== {model}")
    await probe_chat(llm, r)
    print(f"  chat: {'OK' if r.chat_ok else 'FAIL'} {r.chat_reply or r.chat_error}")
    for mode in MODES:
        r.modes[mode] = await probe_mode(llm, model, mode)
        m = r.modes[mode]
        print(f"  {mode}: {'OK ' + m.label if m.ok else 'FAIL ' + m.error}")
    return r


def recommend(results: list[ModelResult]) -> dict[str, str]:
    working = [r for r in results if r.best_mode()]

    def pick(prefer: list[str], exclude: str = "") -> ModelResult | None:
        for word in prefer:
            for r in working:
                if word in r.model.lower() and r.model != exclude:
                    return r
        return next((r for r in working if r.model != exclude), None)

    judge = pick(["ultra"])
    fast = pick(["lightning", "nano"], exclude=judge.model if judge else "")
    if judge and fast and "ultra" not in judge.model.lower():
        # No Ultra available: the judge is just a second, different working model.
        judge = pick(["nano", "lightning"], exclude=fast.model)
    rec: dict[str, str] = {}
    if fast:
        rec["MODEL_FAST"] = fast.model
        rec["STRUCTURED_MODE_FAST"] = str(fast.best_mode())
    if judge:
        rec["MODEL_JUDGE"] = judge.model
        rec["STRUCTURED_MODE_JUDGE"] = str(judge.best_mode())
    return rec


def write_report(path: Path, base_url: str, listed: list[str], results: list[ModelResult],
                 rec: dict[str, str]) -> None:
    def cell(m: ModeResult) -> str:
        if m.ok:
            return f"OK {m.label} ({m.latency_s:.1f}s, {m.tokens})"
        return f"FAIL: {m.error}"

    lines = [
        "# Model probe",
        "",
        f"Run: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} against `{base_url}`",
        "",
        "## NVIDIA / Nemotron models listed by `GET /v1/models`",
        "",
        *([f"- `{m}`" for m in listed] or ["- (none found)"]),
        "",
        "## Results",
        "",
        "Tokens are input/output. Structured tests ask for a `Verdict` on a tiny claim "
        "(expected label: TRUE).",
        "",
        "| Model | Plain chat | tool_forced | tool_auto | text_json | `<think>` in content "
        "| reasoning_content |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        chat = (f"{'OK' if r.chat_ok else 'unexpected'}: {r.chat_reply!r} "
                f"({r.chat_latency_s:.1f}s, {r.chat_tokens})" if not r.chat_error
                else f"FAIL: {r.chat_error}")
        lines.append(
            f"| `{r.model}` | {chat} | {cell(r.modes['tool_forced'])} "
            f"| {cell(r.modes['tool_auto'])} | {cell(r.modes['text_json'])} "
            f"| {'yes' if r.think_in_content else 'no'} | {'yes' if r.reasoning_field else 'no'} |"
        )
    lines += ["", "## Recommendation", ""]
    if rec:
        lines += ["```dotenv", *[f"{k}={v}" for k, v in rec.items()], "```"]
    else:
        lines.append("No model returned a valid `Verdict`.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", help="model IDs to probe instead of the defaults")
    args = parser.parse_args()

    s = Settings(_env_file=None)  # values already loaded from .env by load_dotenv
    if not s.nebius_api_key.strip():
        print("NEBIUS_API_KEY is not set. Add it to .env in the repo root, then run again.")
        return 1

    llm = LLM(s.nebius_base_url, s.nebius_api_key)
    listed: list[str] = []
    try:
        page = await llm.client.models.list()
        listed = sorted(m.id for m in page.data
                        if "nvidia" in m.id.lower() or "nemotron" in m.id.lower())
        print("NVIDIA / Nemotron models on Token Factory:")
        for m in listed:
            print(f"  {m}")
    except Exception as e:  # noqa: BLE001
        print(f"Could not list models: {short(e)}")

    candidates = args.models or [s.model_fast, s.model_judge, *BACKUPS]
    models = list(dict.fromkeys(m.strip() for m in candidates if m and m.strip()))

    results = [await probe_model(llm, m) for m in models]
    rec = recommend(results)
    report = ROOT / "docs" / "model_probe.md"
    write_report(report, s.nebius_base_url, listed, results, rec)

    print(f"\nWrote {report.relative_to(ROOT)}")
    if not rec:
        print("No model returned a valid Verdict. See the report for errors.")
        return 1
    print("Recommended .env values:")
    for k, v in rec.items():
        print(f"  {k}={v}")
    if "MODEL_JUDGE" not in rec:
        print("Only one working model: the jury needs two DIFFERENT models.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
