"""Structured output validation with auto-retry on parse failure (v0.6.0).

LLMs sometimes return malformed JSON, missing required fields, or wrong
types — even when explicitly asked for structured output. This module
provides:

1. ``validate_json_against_schema()`` — pure validation utility.
2. ``parse_with_retry()`` — calls an LLM and retries up to N times on
   parse/validation failure, with feedback to the model.

Usage:

    from largestack._core.structured_output import parse_with_retry

    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "temp_c": {"type": "number"},
        },
        "required": ["city", "temp_c"],
    }

    data = await parse_with_retry(
        agent=agent,
        task="What's the weather in Bengaluru?",
        schema=schema,
        max_retries=3,
    )
    # → {"city": "Bengaluru", "temp_c": 28.5}

The function raises ``StructuredOutputError`` after max_retries on
persistent failure. Each failure includes the parser error in the next
prompt, giving the LLM a chance to self-correct.
"""
from __future__ import annotations
import json
import logging
from typing import Any

log = logging.getLogger("largestack.structured_output")


class StructuredOutputError(Exception):
    """Raised when structured-output parse/validate fails after all retries."""

    def __init__(self, message: str, last_response: str = "", attempts: int = 0):
        super().__init__(message)
        self.last_response = last_response
        self.attempts = attempts


def _validate(data: Any, schema: dict, path: str = "$") -> list[str]:
    """Tiny JSON Schema validator (subset of Draft 7).

    Returns a list of error strings; empty list = valid. We deliberately
    avoid pulling in ``jsonschema`` to keep the dep tree small — this
    handles the cases that matter for LLM output (type, required,
    properties, items, enum).
    """
    errors: list[str] = []
    t = schema.get("type")

    # Type check
    if t == "object":
        if not isinstance(data, dict):
            errors.append(f"{path}: expected object, got {type(data).__name__}")
            return errors
        # Required
        for k in schema.get("required", []):
            if k not in data:
                errors.append(f"{path}: missing required field {k!r}")
        # Properties
        props = schema.get("properties", {})
        for k, sub_schema in props.items():
            if k in data:
                errors.extend(_validate(data[k], sub_schema, f"{path}.{k}"))
        # additionalProperties: false → reject extras
        if schema.get("additionalProperties") is False:
            for k in data:
                if k not in props:
                    errors.append(f"{path}: unexpected field {k!r}")
    elif t == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: expected array, got {type(data).__name__}")
            return errors
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                errors.extend(_validate(item, items_schema, f"{path}[{i}]"))
    elif t == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: expected string, got {type(data).__name__}")
        elif "enum" in schema and data not in schema["enum"]:
            errors.append(f"{path}: value {data!r} not in enum {schema['enum']}")
    elif t == "integer":
        # bool is a subclass of int — JSON Schema treats them as distinct
        if isinstance(data, bool) or not isinstance(data, int):
            errors.append(f"{path}: expected integer, got {type(data).__name__}")
    elif t == "number":
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            errors.append(f"{path}: expected number, got {type(data).__name__}")
    elif t == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: expected boolean, got {type(data).__name__}")
    elif t == "null":
        if data is not None:
            errors.append(f"{path}: expected null")
    return errors


def validate_json_against_schema(data: Any, schema: dict) -> tuple[bool, list[str]]:
    """Validate ``data`` against ``schema``.

    Returns:
        (valid, errors). errors is empty when valid is True.
    """
    errors = _validate(data, schema)
    return (len(errors) == 0, errors)


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -3].rstrip()
    return s


async def parse_with_retry(
    agent: Any,
    task: str,
    schema: dict,
    max_retries: int = 3,
    **agent_run_kwargs: Any,
) -> dict:
    """Call agent.run() and parse output as JSON validated against schema.

    On parse failure or schema violation, append feedback to the next
    prompt and retry up to ``max_retries`` times.

    Args:
        agent: a LARGESTACK Agent instance.
        task: the user task / prompt.
        schema: JSON Schema (Draft 7 subset — see _validate).
        max_retries: number of retries (default 3 = up to 4 total attempts).
        **agent_run_kwargs: forwarded to agent.run() (e.g. cost_budget, timeout).

    Returns:
        The parsed and validated JSON object.

    Raises:
        StructuredOutputError if all attempts fail.
    """
    last_response = ""
    feedback = ""
    for attempt in range(max_retries + 1):
        prompt = task if not feedback else f"{task}\n\nPrevious attempt failed:\n{feedback}\n\nReturn valid JSON conforming exactly to this schema:\n{json.dumps(schema, indent=2)}"
        result = await agent.run(prompt, **agent_run_kwargs)
        # AgentResult.content is the assistant's final text
        text = getattr(result, "content", str(result))
        last_response = text

        # Try parse
        cleaned = _strip_code_fences(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            feedback = f"Output was not valid JSON: {e}. Return ONLY a JSON object — no explanation, no markdown fences."
            log.debug(f"structured_output attempt {attempt + 1}/{max_retries + 1}: parse error: {e}")
            continue

        # Validate
        ok, errors = validate_json_against_schema(data, schema)
        if ok:
            return data
        feedback = "JSON had schema violations:\n- " + "\n- ".join(errors)
        log.debug(f"structured_output attempt {attempt + 1}/{max_retries + 1}: schema violations: {errors}")

    raise StructuredOutputError(
        f"Failed to produce valid JSON after {max_retries + 1} attempts. "
        f"Last error: {feedback}",
        last_response=last_response,
        attempts=max_retries + 1,
    )
