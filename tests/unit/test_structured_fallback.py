"""Structured output must work on providers that lack native json_schema (e.g. DeepSeek).

These cover the prompt-based fallback added so `response_model=` no longer fails
outright with AllProvidersFailedError on DeepSeek and similar providers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel, Field

from largestack._core.structured import build_native_params, run_structured
from largestack.errors import AllProvidersFailedError


class Review(BaseModel):
    title: str
    rating: int = Field(ge=1, le=10)
    summary: str


def _agent(model: str, execute) -> SimpleNamespace:
    return SimpleNamespace(llm=model, _engine=SimpleNamespace(execute=execute))


def test_deepseek_is_not_routed_to_native_json_schema():
    # DeepSeek rejects strict json_schema live, so it must use the prompt fallback.
    assert build_native_params("deepseek/deepseek-chat", Review.model_json_schema()) == {}


def test_openai_still_uses_native_json_schema():
    params = build_native_params("openai/gpt-4o", Review.model_json_schema())
    assert params["response_format"]["type"] == "json_schema"


async def test_deepseek_prompt_path_returns_typed_object():
    execute = AsyncMock(
        return_value=SimpleNamespace(
            content='{"title": "Inception", "rating": 9, "summary": "A heist inside dreams."}'
        )
    )
    out = await run_structured(
        _agent("deepseek/deepseek-chat", execute), "Review Inception", Review
    )
    assert isinstance(out, Review)
    assert out.rating == 9 and out.title == "Inception"
    # Prompt path must NOT send a native response_format.
    for call in execute.await_args_list:
        assert "response_format" not in call.kwargs


async def test_native_provider_error_falls_back_to_prompt():
    # First (native) call is rejected by the provider; prompt fallback then succeeds.
    execute = AsyncMock(
        side_effect=[
            AllProvidersFailedError(["openai"]),
            SimpleNamespace(content='```json\n{"title": "X", "rating": 7, "summary": "ok"}\n```'),
        ]
    )
    out = await run_structured(_agent("openai/gpt-4o", execute), "Review X", Review)
    assert isinstance(out, Review) and out.rating == 7
    assert execute.await_count == 2  # native attempt + prompt fallback
