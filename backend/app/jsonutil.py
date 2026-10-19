import json
import re

THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def strip_think(text: str | None) -> str:
    """Remove <think>…</think> blocks that Nemotron reasoning models may emit.

    Also handles a lone </think> (the chat template opened the block in the prompt, so only
    the close tag is in the output) and a lone <think> (reasoning cut off before it closed).
    """
    text = THINK_RE.sub("", text or "")
    lower = text.lower()
    if "</think>" in lower:
        text = text[lower.rindex("</think>") + len("</think>") :]
        lower = text.lower()
    if "<think>" in lower:
        text = text[: lower.index("<think>")]
    return text.strip()


def _decode_at(text: str, start: int) -> object | None:
    """Decode the JSON value starting at text[start], or None. Retries without trailing commas."""
    decoder = json.JSONDecoder()
    try:
        return decoder.raw_decode(text, start)[0]
    except ValueError:
        pass
    try:
        return decoder.raw_decode(TRAILING_COMMA_RE.sub(r"\1", text[start:]))[0]
    except ValueError:
        return None


def extract_json(text: str | None) -> str:
    """Return the first complete JSON object found in text (after removing <think> blocks).

    Tolerates prose and code fences around the object, stray braces in the prose before it
    and trailing commas inside it.
    """
    text = strip_think(text)
    for match in re.finditer(r"\{", text):
        obj = _decode_at(text, match.start())
        if isinstance(obj, dict):
            return json.dumps(obj)
    raise ValueError("no JSON object in model output")


def inline_refs(schema: dict) -> dict:
    """Replace Pydantic $ref/$defs with inline copies (some servers handle $ref badly)."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(defs[name])
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
