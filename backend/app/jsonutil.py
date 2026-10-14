import json
import re

THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_think(text: str | None) -> str:
    """Remove <think>…</think> blocks that Nemotron reasoning models may emit."""
    return THINK_RE.sub("", text or "").strip()


def extract_json(text: str | None) -> str:
    """Return the first complete JSON object found in text (after removing <think> blocks)."""
    text = strip_think(text)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return json.dumps(obj)


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
