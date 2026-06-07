"""Behavioral tests for structured-output parsing (largestack/_core/structured.py).

parse_structured() must hydrate a Pydantic model from the many shapes an LLM
actually returns: clean JSON, fenced JSON, JSON embedded in prose, and it must
raise (not silently return garbage) when there is no usable JSON.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from largestack._core.structured import build_structured_prompt, parse_structured


class M(BaseModel):
    name: str
    n: int


def test_parses_plain_json():
    assert parse_structured('{"name": "a", "n": 1}', M).n == 1


def test_parses_markdown_fenced_json():
    assert parse_structured('```json\n{"name": "a", "n": 2}\n```', M).n == 2


def test_extracts_json_embedded_in_prose():
    out = parse_structured('Sure! Here it is: {"name": "a", "n": 3}. Hope that helps.', M)
    assert out.n == 3 and out.name == "a"


def test_handles_nested_braces():
    class Nested(BaseModel):
        name: str
        meta: dict

    out = parse_structured('{"name": "x", "meta": {"a": {"b": 1}}}', Nested)
    assert out.meta["a"]["b"] == 1


def test_raises_when_no_json_present():
    with pytest.raises(ValueError):
        parse_structured("there is absolutely no json in this reply", M)


def test_build_structured_prompt_includes_schema_and_task():
    prompt = build_structured_prompt(M, "classify this ticket")
    assert "classify this ticket" in prompt
    assert "JSON" in prompt and "name" in prompt and "n" in prompt
