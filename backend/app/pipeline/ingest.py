import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from ..schemas import CheckRequest, validate_check_request
from ..search import IngestError

if TYPE_CHECKING:
    from .orchestrator import Deps

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_NAMES = (
    "system_preamble",
    "extract_claims",
    "plan_queries",
    "assess_evidence",
    "verdict",
    "final_ruling",
)
_PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)?)\}")


# ---- shared prompt helpers (used by every step) ----
@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def load_all_prompts() -> None:
    """Read every prompt once, so a missing file fails at startup rather than mid-check."""
    for name in PROMPT_NAMES:
        load_prompt(name)


def render(template: str, values: dict[str, object]) -> str:
    """Fill {name} placeholders in ONE pass, so placeholders inside inserted (untrusted) text
    are never expanded, and JSON braces in text are left alone."""
    return _PLACEHOLDER.sub(
        lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template
    )


def system_prompt(today: str) -> str:
    return render(load_prompt("system_preamble"), {"today": today})


# The tags the prompts wrap untrusted text in.
_PROMPT_TAG = re.compile(r"<(/?)(source|claim|evidence|input|reviewer_[ab])", re.I)


def defuse(text: str) -> str:
    """Break prompt tags inside untrusted text ("</evidence>" -> "</ evidence>"), so web or
    model text cannot fake the end of its block and pose as instructions."""
    return _PROMPT_TAG.sub(r"<\1 \2", text)


# ---- step 1: ingest ----
def _page_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


async def ingest(req: CheckRequest, deps: "Deps") -> tuple[str, str | None]:
    """Return (text for the claims step, page title if any). Raises IngestError."""
    try:
        req = validate_check_request(req, deps.settings.max_input_chars)
    except ValueError as e:
        raise IngestError(str(e)) from e
    if req.text:
        return re.sub(r"\s+", " ", req.text).strip(), None
    page = await deps.search.extract_url(req.url)
    text = re.sub(r"\s+", " ", page).strip()
    if not text:
        raise IngestError("Could not read that page. Try pasting the text instead.")
    return text[: deps.settings.max_input_chars], _page_title(page)
