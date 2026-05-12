"""v0.6.0: Structured output validation tests.

Tests both the validator subset (no jsonschema dep) and the auto-retry
``parse_with_retry`` flow.
"""
from __future__ import annotations

import pytest

from largestack._core.structured_output import (
    StructuredOutputError,
    parse_with_retry,
    validate_json_against_schema,
    _strip_code_fences,
)


# -------------------- Validator --------------------

def test_validate_simple_object_ok():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
    }
    ok, errors = validate_json_against_schema({"name": "alice", "age": 30}, schema)
    assert ok is True
    assert errors == []


def test_validate_missing_required():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    ok, errors = validate_json_against_schema({}, schema)
    assert ok is False
    assert any("missing required field 'name'" in e for e in errors)


def test_validate_wrong_type_string():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    ok, errors = validate_json_against_schema({"x": 42}, schema)
    assert ok is False
    assert any("expected string" in e for e in errors)


def test_validate_integer_not_bool():
    """JSON Schema treats bool as distinct from int."""
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    ok, errors = validate_json_against_schema({"x": True}, schema)
    assert ok is False


def test_validate_number_accepts_int_and_float():
    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    ok, _ = validate_json_against_schema({"x": 1}, schema)
    assert ok is True
    ok, _ = validate_json_against_schema({"x": 1.5}, schema)
    assert ok is True


def test_validate_array_with_items():
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    ok, _ = validate_json_against_schema({"tags": ["a", "b"]}, schema)
    assert ok is True
    ok, errors = validate_json_against_schema({"tags": ["a", 2]}, schema)
    assert ok is False
    assert any("[1]" in e and "expected string" in e for e in errors)


def test_validate_enum():
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["open", "closed"]}},
    }
    ok, _ = validate_json_against_schema({"status": "open"}, schema)
    assert ok is True
    ok, errors = validate_json_against_schema({"status": "pending"}, schema)
    assert ok is False
    assert any("enum" in e for e in errors)


def test_validate_additional_properties_false():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }
    ok, errors = validate_json_against_schema(
        {"name": "x", "extra": 1}, schema
    )
    assert ok is False
    assert any("unexpected field 'extra'" in e for e in errors)


def test_validate_nested_object():
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            }
        },
    }
    ok, _ = validate_json_against_schema({"user": {"id": 1}}, schema)
    assert ok is True
    ok, errors = validate_json_against_schema({"user": {"id": "x"}}, schema)
    assert ok is False
    assert any("$.user.id" in e for e in errors)


# -------------------- Code fence stripping --------------------

def test_strip_code_fences_with_json_lang():
    text = '```json\n{"a": 1}\n```'
    assert _strip_code_fences(text) == '{"a": 1}'


def test_strip_code_fences_no_fence():
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_strip_code_fences_plain_fence():
    text = '```\n{"a": 1}\n```'
    assert _strip_code_fences(text) == '{"a": 1}'


# -------------------- parse_with_retry --------------------

class _MockAgent:
    """Minimal agent stub that returns a sequence of preset responses."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[str] = []

    async def run(self, task: str, **kw):
        self.calls.append(task)
        text = self.responses.pop(0) if self.responses else ""

        class _R:
            content = text
        return _R()


@pytest.mark.asyncio
async def test_parse_with_retry_succeeds_first_try():
    agent = _MockAgent(['{"name": "alice", "age": 30}'])
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    data = await parse_with_retry(agent, "task", schema, max_retries=3)
    assert data == {"name": "alice", "age": 30}
    assert len(agent.calls) == 1


@pytest.mark.asyncio
async def test_parse_with_retry_recovers_from_bad_json():
    """First attempt returns broken JSON, second attempt is clean."""
    agent = _MockAgent([
        "not valid json at all",
        '{"name": "alice", "age": 30}',
    ])
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    data = await parse_with_retry(agent, "task", schema, max_retries=3)
    assert data == {"name": "alice", "age": 30}
    assert len(agent.calls) == 2
    # Second prompt must contain the parse-error feedback
    assert "not valid JSON" in agent.calls[1]


@pytest.mark.asyncio
async def test_parse_with_retry_recovers_from_schema_violation():
    """First attempt parses but violates schema, second attempt is correct."""
    agent = _MockAgent([
        '{"name": "alice"}',  # missing age
        '{"name": "alice", "age": 30}',
    ])
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    data = await parse_with_retry(agent, "task", schema, max_retries=3)
    assert data == {"name": "alice", "age": 30}
    assert len(agent.calls) == 2
    # Second prompt must contain schema-violation feedback
    assert "schema violations" in agent.calls[1]


@pytest.mark.asyncio
async def test_parse_with_retry_strips_markdown_fences():
    """LLMs often wrap JSON in ```json ... ``` — must still parse."""
    agent = _MockAgent(['```json\n{"name": "alice", "age": 30}\n```'])
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    data = await parse_with_retry(agent, "task", schema, max_retries=3)
    assert data == {"name": "alice", "age": 30}


@pytest.mark.asyncio
async def test_parse_with_retry_raises_after_all_attempts():
    """If LLM never produces valid output, raise StructuredOutputError
    after exhausting retries."""
    agent = _MockAgent(["broken1", "broken2", "broken3", "broken4"])
    schema = {"type": "object", "required": ["x"]}

    with pytest.raises(StructuredOutputError) as ei:
        await parse_with_retry(agent, "task", schema, max_retries=3)

    err = ei.value
    assert err.attempts == 4  # 1 initial + 3 retries
    assert err.last_response == "broken4"


@pytest.mark.asyncio
async def test_parse_with_retry_forwards_kwargs():
    """Extra kwargs must be passed through to agent.run()."""
    captured_kwargs: dict = {}

    class _CaptureAgent:
        async def run(self, task, **kw):
            captured_kwargs.update(kw)

            class _R:
                content = "{}"
            return _R()

    schema = {"type": "object"}
    await parse_with_retry(
        _CaptureAgent(),
        "task",
        schema,
        max_retries=0,
        cost_budget=5.0,
        timeout=30.0,
    )
    assert captured_kwargs.get("cost_budget") == 5.0
    assert captured_kwargs.get("timeout") == 30.0
