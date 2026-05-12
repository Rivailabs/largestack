"""Generic typed agent (v0.14.0).

Closes Tier A #19. ``TypedAgent[InputT, OutputT]`` — generic agent
class with declared input/output Pydantic models. Mypy --strict clean.

Why a separate class instead of retrofitting ``Agent``:
- Backward compatibility — existing ``Agent(name=..., model=...)`` users
  shouldn't have to add type parameters
- ``TypedAgent`` is opt-in for teams that run mypy --strict in CI

Usage::

    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class KYCInput(BaseModel):
        pan: str
        aadhaar_last4: str

    class KYCOutput(BaseModel):
        verified: bool
        risk_score: float
        notes: str

    agent: TypedAgent[KYCInput, KYCOutput] = TypedAgent(
        name="kyc-verify",
        model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        input_model=KYCInput,
        output_model=KYCOutput,
    )

    result = await agent.run(KYCInput(pan="ABCDE1234F", aadhaar_last4="9012"))
    # result is statically typed as KYCOutput
    print(result.risk_score)

The output is JSON-extracted from the LLM response and validated
against ``output_model``. If validation fails after N retries, raises
``OutputValidationError``.
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

log = logging.getLogger("largestack.core.typed_agent")


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class OutputValidationError(Exception):
    """Raised when LLM output can't be validated as ``output_model``."""

    def __init__(
        self,
        message: str,
        raw_output: str = "",
        validation_errors: list[str] | None = None,
    ):
        super().__init__(message)
        self.raw_output = raw_output
        self.validation_errors = validation_errors or []


def _extract_json_from_response(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of an LLM response.

    Handles common patterns:
    - Bare JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON wrapped in <json>...</json> tags
    - JSON with leading/trailing prose
    """
    if not text or not text.strip():
        return None

    # Try parsing as-is
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Code-fence pattern: ```json ... ``` or ``` ... ```
    fence_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text, re.DOTALL,
    )
    if fence_match:
        try:
            result = json.loads(fence_match.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # XML-style tag pattern
    tag_match = re.search(
        r"<json>\s*(\{.*?\})\s*</json>",
        text, re.DOTALL | re.IGNORECASE,
    )
    if tag_match:
        try:
            result = json.loads(tag_match.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Last resort: longest brace-balanced object in the text
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(text[start : i + 1])
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass

    return None


@dataclass
class TypedAgent(Generic[InputT, OutputT]):
    """Generic typed agent with declared input/output Pydantic models.

    The fields are populated at construction; ``run()`` produces an
    instance of ``output_model``.
    """
    name: str
    model: str
    input_model: type
    output_model: type
    instructions: str = ""
    max_retries: int = 2
    llm_runner: Callable[..., Awaitable[str]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ValueError("name is required")
        if not self.model:
            raise ValueError("model is required")
        if self.input_model is None or self.output_model is None:
            raise ValueError("input_model and output_model are required")

    def _build_prompt(self, input_data: InputT) -> list[dict[str, str]]:
        """Construct the LLM messages from typed input."""
        # Serialize input via Pydantic if available, else use __dict__
        input_dict: dict[str, Any]
        if hasattr(input_data, "model_dump"):
            input_dict = input_data.model_dump()  # pydantic v2
        elif hasattr(input_data, "dict"):
            input_dict = input_data.dict()        # pydantic v1
        elif hasattr(input_data, "__dict__"):
            input_dict = dict(input_data.__dict__)
        elif isinstance(input_data, dict):
            input_dict = dict(input_data)
        else:
            input_dict = {"value": input_data}

        # Build a JSON schema description for the output model
        schema_hint = ""
        if hasattr(self.output_model, "model_json_schema"):
            try:
                schema = self.output_model.model_json_schema()
                schema_hint = (
                    f"\nReturn a JSON object matching this schema:\n"
                    f"{json.dumps(schema, indent=2)}\n"
                )
            except Exception:
                schema_hint = (
                    f"\nReturn a JSON object matching the "
                    f"{self.output_model.__name__} schema.\n"
                )

        system = (
            self.instructions
            + "\n\nRespond ONLY with a valid JSON object that matches "
            "the output schema. No prose, no code fences, just the JSON."
            + schema_hint
        )
        user = (
            f"Input:\n{json.dumps(input_dict, indent=2, default=str)}"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _validate_output(self, raw: str) -> OutputT:
        """Parse + validate raw LLM output as ``output_model``."""
        data = _extract_json_from_response(raw)
        if data is None:
            raise OutputValidationError(
                "no JSON object found in LLM response",
                raw_output=raw,
            )
        try:
            if hasattr(self.output_model, "model_validate"):
                return self.output_model.model_validate(data)  # v2
            if hasattr(self.output_model, "parse_obj"):
                return self.output_model.parse_obj(data)        # v1
            return self.output_model(**data)                    # plain
        except Exception as e:
            raise OutputValidationError(
                f"validation failed: {e}",
                raw_output=raw,
                validation_errors=[str(e)],
            ) from e

    async def run(self, input_data: InputT) -> OutputT:
        """Run the agent. Returns an instance of ``output_model``."""
        if self.llm_runner is None:
            raise RuntimeError(
                "llm_runner not set; assign a callable that takes "
                "messages and returns the response text"
            )

        messages = self._build_prompt(input_data)
        last_error: Exception | None = None
        last_raw = ""

        for attempt in range(self.max_retries + 1):
            try:
                raw = await self.llm_runner(messages, model=self.model)
            except Exception as e:
                last_error = e
                continue
            last_raw = raw if isinstance(raw, str) else str(raw)
            try:
                return self._validate_output(last_raw)
            except OutputValidationError as e:
                last_error = e
                # On retry, append the error so the LLM can self-correct
                messages.append({
                    "role": "assistant", "content": last_raw,
                })
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous response failed validation: {e}. "
                        f"Please retry with a strictly-valid JSON object."
                    ),
                })

        if isinstance(last_error, OutputValidationError):
            raise last_error
        raise OutputValidationError(
            f"all retries failed: {last_error}",
            raw_output=last_raw,
        )

    async def run_with_dict(
        self, input_dict: dict[str, Any],
    ) -> OutputT:
        """Convenience: hydrate ``input_model`` from a dict and run."""
        if hasattr(self.input_model, "model_validate"):
            obj = self.input_model.model_validate(input_dict)
        elif hasattr(self.input_model, "parse_obj"):
            obj = self.input_model.parse_obj(input_dict)
        else:
            obj = self.input_model(**input_dict)
        return await self.run(obj)


__all__ = [
    "TypedAgent", "OutputValidationError",
    "InputT", "OutputT",
]
