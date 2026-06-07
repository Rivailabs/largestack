"""v0.14.0: Tests for generic typed Agent class."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# -------------------- _extract_json_from_response --------------------


def test_extract_json_bare():
    from largestack._core.typed_agent import _extract_json_from_response

    assert _extract_json_from_response('{"a": 1}') == {"a": 1}


def test_extract_json_from_code_fence():
    from largestack._core.typed_agent import _extract_json_from_response

    text = 'Here is the result:\n```json\n{"verified": true}\n```\nThanks'
    assert _extract_json_from_response(text) == {"verified": True}


def test_extract_json_from_xml_tag():
    from largestack._core.typed_agent import _extract_json_from_response

    text = '<json>{"a": 1, "b": "x"}</json>'
    assert _extract_json_from_response(text) == {"a": 1, "b": "x"}


def test_extract_json_with_leading_prose():
    from largestack._core.typed_agent import _extract_json_from_response

    text = 'Sure! Here is the JSON: {"score": 0.85, "name": "x"}'
    result = _extract_json_from_response(text)
    assert result == {"score": 0.85, "name": "x"}


def test_extract_json_returns_none_for_garbage():
    from largestack._core.typed_agent import _extract_json_from_response

    assert _extract_json_from_response("this is not JSON at all") is None
    assert _extract_json_from_response("") is None


# -------------------- TypedAgent construction --------------------


def test_typed_agent_requires_name():
    from largestack._core.typed_agent import TypedAgent

    pytest.importorskip("pydantic")
    from pydantic import BaseModel

    class M(BaseModel):
        x: str

    with pytest.raises(ValueError, match="name"):
        TypedAgent(
            name="",
            model="x",
            input_model=M,
            output_model=M,
        )


def test_typed_agent_requires_model():
    from largestack._core.typed_agent import TypedAgent

    pytest.importorskip("pydantic")
    from pydantic import BaseModel

    class M(BaseModel):
        x: str

    with pytest.raises(ValueError, match="model"):
        TypedAgent(name="x", model="", input_model=M, output_model=M)


def test_typed_agent_accepts_pydantic_models():
    from largestack._core.typed_agent import TypedAgent

    pytest.importorskip("pydantic")
    from pydantic import BaseModel

    class InputModel(BaseModel):
        pan: str

    class OutputModel(BaseModel):
        verified: bool

    agent = TypedAgent(
        name="kyc",
        model="openai/gpt-4o",
        input_model=InputModel,
        output_model=OutputModel,
    )
    assert agent.name == "kyc"
    assert agent.input_model is InputModel
    assert agent.output_model is OutputModel


# -------------------- run() with mocked LLM --------------------


@pytest.mark.asyncio
async def test_run_returns_validated_output():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class InputModel(BaseModel):
        pan: str

    class OutputModel(BaseModel):
        verified: bool
        risk_score: float

    fake_llm = AsyncMock(
        return_value='{"verified": true, "risk_score": 0.85}',
    )

    agent: TypedAgent = TypedAgent(
        name="kyc",
        model="openai/gpt-4o",
        input_model=InputModel,
        output_model=OutputModel,
        llm_runner=fake_llm,
    )

    result = await agent.run(InputModel(pan="ABCDE1234F"))
    assert isinstance(result, OutputModel)
    assert result.verified is True
    assert result.risk_score == 0.85


@pytest.mark.asyncio
async def test_run_handles_code_fenced_json():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class M(BaseModel):
        x: int

    fake_llm = AsyncMock(
        return_value='Here you go:\n```json\n{"x": 42}\n```',
    )

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=M,
        llm_runner=fake_llm,
    )
    result = await agent.run(M(x=1))
    assert result.x == 42


@pytest.mark.asyncio
async def test_run_retries_on_validation_failure():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class M(BaseModel):
        x: int

    # First call: invalid JSON. Second: valid.
    fake_llm = AsyncMock(
        side_effect=["this is not JSON at all", '{"x": 5}'],
    )

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=M,
        llm_runner=fake_llm,
        max_retries=1,
    )
    result = await agent.run(M(x=1))
    assert result.x == 5
    assert fake_llm.await_count == 2


@pytest.mark.asyncio
async def test_run_raises_after_exhausted_retries():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import (
        TypedAgent,
        OutputValidationError,
    )

    class M(BaseModel):
        x: int

    fake_llm = AsyncMock(return_value="garbage")

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=M,
        llm_runner=fake_llm,
        max_retries=1,
    )
    with pytest.raises(OutputValidationError):
        await agent.run(M(x=1))


@pytest.mark.asyncio
async def test_run_raises_when_llm_runner_missing():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class M(BaseModel):
        x: int

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=M,
    )
    with pytest.raises(RuntimeError, match="llm_runner"):
        await agent.run(M(x=1))


@pytest.mark.asyncio
async def test_run_with_dict_hydrates_input():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class InputModel(BaseModel):
        pan: str

    class OutputModel(BaseModel):
        verified: bool

    fake_llm = AsyncMock(return_value='{"verified": true}')

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=InputModel,
        output_model=OutputModel,
        llm_runner=fake_llm,
    )
    result = await agent.run_with_dict({"pan": "ABCDE1234F"})
    assert result.verified is True


# -------------------- _build_prompt --------------------


def test_build_prompt_includes_input_data():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class M(BaseModel):
        pan: str

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=M,
        instructions="You are a KYC agent",
    )
    msgs = agent._build_prompt(M(pan="ABCDE1234F"))
    assert msgs[0]["role"] == "system"
    assert "KYC agent" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "ABCDE1234F" in msgs[1]["content"]


def test_build_prompt_includes_output_schema():
    pytest.importorskip("pydantic")
    from pydantic import BaseModel
    from largestack._core.typed_agent import TypedAgent

    class M(BaseModel):
        x: int

    class O(BaseModel):
        result: str

    agent: TypedAgent = TypedAgent(
        name="x",
        model="m",
        input_model=M,
        output_model=O,
    )
    msgs = agent._build_prompt(M(x=1))
    # Schema mention in system prompt
    assert "schema" in msgs[0]["content"].lower()


# -------------------- OutputValidationError --------------------


def test_output_validation_error_carries_raw():
    from largestack._core.typed_agent import OutputValidationError

    e = OutputValidationError(
        "boom",
        raw_output="garbage",
        validation_errors=["err1"],
    )
    assert e.raw_output == "garbage"
    assert e.validation_errors == ["err1"]
