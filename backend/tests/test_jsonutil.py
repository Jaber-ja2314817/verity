import pytest
from pydantic import BaseModel

from app.jsonutil import extract_json, inline_refs, strip_think
from app.schemas import ClaimExtraction, JuryResult


def test_strip_think_removes_block():
    assert strip_think("<think>hmm\nlet me see</think> answer") == "answer"


def test_strip_think_handles_none_and_case():
    assert strip_think(None) == ""
    assert strip_think("<THINK>x</THINK>ok") == "ok"


def test_extract_json_after_think_block():
    text = '<think>{"wrong": 1}</think>{"label": "TRUE"}'
    assert extract_json(text) == '{"label": "TRUE"}'


def test_extract_json_with_text_around():
    text = 'Here you go: {"a": {"b": [1, 2]}} hope that helps {"c": 3}'
    assert extract_json(text) == '{"a": {"b": [1, 2]}}'


def test_extract_json_without_json_raises():
    with pytest.raises(ValueError):
        extract_json("no json here")


def _has_ref(node) -> bool:
    if isinstance(node, dict):
        return "$ref" in node or "$defs" in node or any(_has_ref(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_ref(x) for x in node)
    return False


@pytest.mark.parametrize("model", [ClaimExtraction, JuryResult])
def test_inline_refs_removes_all_refs(model: type[BaseModel]):
    schema = model.model_json_schema()
    assert _has_ref(schema)
    assert not _has_ref(inline_refs(schema))


def test_inline_refs_keeps_nested_structure():
    schema = inline_refs(ClaimExtraction.model_json_schema())
    item = schema["properties"]["claims"]["items"]
    assert set(item["properties"]) == {"id", "text", "checkworthy", "reason"}
