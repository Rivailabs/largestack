"""Tests for structured output (Pydantic parsing)."""
import sys, pytest; sys.path.insert(0, ".")
from pydantic import BaseModel
from largestack._core.structured import parse_structured, build_structured_prompt

class Report(BaseModel):
    title: str
    score: float
    tags: list[str] = []

def test_parse_clean_json():
    r = parse_structured('{"title": "AI Report", "score": 8.5}', Report)
    assert r.title == "AI Report" and r.score == 8.5

def test_parse_with_markdown():
    r = parse_structured('```json\n{"title": "Test", "score": 9.0}\n```', Report)
    assert r.title == "Test" and r.score == 9.0

def test_parse_with_preamble():
    r = parse_structured('Here is the result:\n{"title": "Data", "score": 7.0}', Report)
    assert r.title == "Data"

def test_parse_with_tags():
    r = parse_structured('{"title": "X", "score": 5.0, "tags": ["ai", "ml"]}', Report)
    assert r.tags == ["ai", "ml"]

def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_structured("not json at all", Report)

def test_build_prompt():
    prompt = build_structured_prompt(Report, "Analyze AI trends")
    assert "title" in prompt and "score" in prompt and "Analyze AI trends" in prompt
    assert "JSON" in prompt
