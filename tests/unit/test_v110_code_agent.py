"""v0.11.0: Tests for CodeAgentV11 — Smolagents-style code-gen agent."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Response parsing --------------------

def test_parse_response_extracts_thought():
    from largestack._core.code_agent_v11 import _parse_response
    text = "<thought>I need to compute factorial</thought>"
    thought, code, final = _parse_response(text)
    assert thought == "I need to compute factorial"
    assert code == ""
    assert final is None


def test_parse_response_extracts_code_with_wrapper():
    from largestack._core.code_agent_v11 import _parse_response
    text = """<thought>compute fib</thought>
<code>```python
def fib(n):
    if n < 2: return n
    return fib(n-1) + fib(n-2)
print(fib(10))
```</code>"""
    thought, code, final = _parse_response(text)
    assert "compute fib" in thought
    assert "def fib" in code
    assert "print(fib(10))" in code


def test_parse_response_extracts_code_fallback():
    """Even without <code> wrapper, ```python``` blocks should work."""
    from largestack._core.code_agent_v11 import _parse_response
    text = """Sure, here's the code:
```python
print("hello")
```"""
    _, code, _ = _parse_response(text)
    assert 'print("hello")' in code


def test_parse_response_extracts_final():
    from largestack._core.code_agent_v11 import _parse_response
    text = "<final>The answer is 42</final>"
    _, _, final = _parse_response(text)
    assert final == "The answer is 42"


def test_parse_response_handles_empty():
    from largestack._core.code_agent_v11 import _parse_response
    thought, code, final = _parse_response("")
    assert thought == ""
    assert code == ""
    assert final is None


# -------------------- CodeAgentV11 execution --------------------

@pytest.mark.asyncio
async def test_code_agent_solves_simple_task_in_one_step():
    """LLM produces code → sandbox runs → LLM gives final answer."""
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(side_effect=[
        # Step 1: write code
        MagicMock(content=(
            "<thought>compute 2+2</thought>\n"
            "<code>```python\nprint(2+2)\n```</code>"
        )),
        # Step 2: see "4" in stdout, give final
        MagicMock(content="<final>4</final>"),
    ])

    agent = CodeAgentV11(llm_agent=llm, tools=[], max_steps=5)
    result = await agent.run("What is 2+2?")

    assert result.succeeded is True
    assert result.final_answer == "4"
    assert result.total_llm_calls == 2
    assert result.step_count == 2
    # Step 1 should have stdout = "4"
    assert "4" in result.steps[0].stdout


@pytest.mark.asyncio
async def test_code_agent_immediate_final():
    """LLM can answer without running code."""
    from largestack._core.code_agent_v11 import CodeAgentV11
    llm = MagicMock()
    llm.run = AsyncMock(return_value=MagicMock(
        content="<final>The capital of France is Paris.</final>"
    ))

    agent = CodeAgentV11(llm_agent=llm)
    result = await agent.run("What is the capital of France?")

    assert result.succeeded is True
    assert "Paris" in result.final_answer
    assert result.total_llm_calls == 1


@pytest.mark.asyncio
async def test_code_agent_handles_code_failure():
    """Bad code → sandbox stderr → LLM sees error and recovers."""
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(side_effect=[
        # Step 1: write buggy code
        MagicMock(content=(
            "<code>```python\nundefined_var + 1\n```</code>"
        )),
        # Step 2: fix it
        MagicMock(content=(
            "<code>```python\nprint(2 + 1)\n```</code>"
        )),
        # Step 3: final
        MagicMock(content="<final>3</final>"),
    ])

    agent = CodeAgentV11(llm_agent=llm, max_steps=5)
    result = await agent.run("What is 2+1?")

    assert result.succeeded is True
    # Step 1 should show error
    assert result.steps[0].error or result.steps[0].stderr


@pytest.mark.asyncio
async def test_code_agent_hits_max_steps():
    """If LLM never produces final, hit the limit."""
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    # Always produce code, never a final
    llm.run = AsyncMock(return_value=MagicMock(
        content="<code>```python\nprint('looping')\n```</code>"
    ))

    agent = CodeAgentV11(llm_agent=llm, max_steps=3)
    result = await agent.run("Endless task")

    assert result.succeeded is False
    assert "max_steps" in result.failure_reason
    assert result.step_count == 3


@pytest.mark.asyncio
async def test_code_agent_no_code_no_final():
    """LLM produces only thought, no code or final → fails."""
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(return_value=MagicMock(
        content="<thought>I'm just thinking, not doing anything.</thought>"
    ))

    agent = CodeAgentV11(llm_agent=llm, max_steps=5)
    result = await agent.run("Do something")

    assert result.succeeded is False
    assert "no code" in result.failure_reason


@pytest.mark.asyncio
async def test_code_agent_handles_llm_failure():
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(side_effect=RuntimeError("LLM down"))

    agent = CodeAgentV11(llm_agent=llm, max_steps=3)
    result = await agent.run("Anything")

    assert result.succeeded is False
    assert "LLM error" in result.failure_reason


@pytest.mark.asyncio
async def test_code_agent_with_tools_in_signature():
    from largestack._core.code_agent_v11 import CodeAgentV11
    from largestack._core.tools import tool

    @tool(name="my_tool", description="Does something useful")
    async def my_tool(x: int) -> int:
        return x * 2

    llm = MagicMock()
    llm.run = AsyncMock(return_value=MagicMock(
        content="<final>done</final>"
    ))

    agent = CodeAgentV11(llm_agent=llm, tools=[my_tool])
    # Verify the tool signature is in the system prompt
    sys_prompt = agent._system_prompt()
    assert "my_tool" in sys_prompt
    assert "Does something useful" in sys_prompt


def test_code_agent_tool_signatures_handle_no_tools():
    from largestack._core.code_agent_v11 import CodeAgentV11
    llm = MagicMock()
    agent = CodeAgentV11(llm_agent=llm, tools=[])
    sys_prompt = agent._system_prompt()
    assert "no tools available" in sys_prompt


@pytest.mark.asyncio
async def test_code_agent_default_allowed_modules():
    """Default allowlist includes math, json, re — common needs."""
    from largestack._core.code_agent_v11 import CodeAgentV11
    llm = MagicMock()
    agent = CodeAgentV11(llm_agent=llm)
    assert "math" in agent.allowed_modules
    assert "json" in agent.allowed_modules
    assert "re" in agent.allowed_modules


@pytest.mark.asyncio
async def test_code_agent_sandbox_blocks_disallowed_imports():
    """Sandbox enforces module allowlist."""
    from largestack._core.code_agent_v11 import CodeAgentV11
    from largestack._core.citation_sandbox import CodeInterpreter

    # Restrict to only `math`
    sandbox = CodeInterpreter(
        timeout_seconds=10, allowed_modules=["math"],
    )
    llm = MagicMock()
    # Two-step: first try forbidden import, then succeed
    llm.run = AsyncMock(side_effect=[
        MagicMock(content="<code>```python\nimport socket\nprint('hi')\n```</code>"),
        MagicMock(content="<final>blocked</final>"),
    ])
    agent = CodeAgentV11(
        llm_agent=llm, sandbox=sandbox, allowed_modules=["math"],
    )
    result = await agent.run("Try a forbidden import")
    # Step 1 should have error or stderr indicating block
    step1 = result.steps[0]
    assert "not in allowlist" in step1.stderr or step1.error


@pytest.mark.asyncio
async def test_code_agent_step_count_property():
    from largestack._core.code_agent_v11 import CodeAgentResult, CodeStep
    result = CodeAgentResult()
    assert result.step_count == 0
    result.steps.append(CodeStep(step_number=1))
    assert result.step_count == 1


@pytest.mark.asyncio
async def test_code_agent_attaches_thought_and_code_to_step():
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(side_effect=[
        MagicMock(content=(
            "<thought>First I'll print hello</thought>\n"
            "<code>```python\nprint('hello')\n```</code>"
        )),
        MagicMock(content="<final>greeting sent</final>"),
    ])
    agent = CodeAgentV11(llm_agent=llm, max_steps=3)
    result = await agent.run("Greet me")

    step1 = result.steps[0]
    assert "First I'll print" in step1.thought
    assert "print('hello')" in step1.code
    assert "hello" in step1.stdout


@pytest.mark.asyncio
async def test_code_agent_total_llm_calls_count():
    from largestack._core.code_agent_v11 import CodeAgentV11

    llm = MagicMock()
    llm.run = AsyncMock(side_effect=[
        MagicMock(content="<code>```python\nprint(1)\n```</code>"),
        MagicMock(content="<code>```python\nprint(2)\n```</code>"),
        MagicMock(content="<final>done</final>"),
    ])
    agent = CodeAgentV11(llm_agent=llm, max_steps=5)
    result = await agent.run("Multi-step")

    assert result.total_llm_calls == 3


@pytest.mark.asyncio
async def test_code_agent_failure_reason_set():
    from largestack._core.code_agent_v11 import CodeAgentV11
    llm = MagicMock()
    llm.run = AsyncMock(return_value=MagicMock(content=""))
    agent = CodeAgentV11(llm_agent=llm, max_steps=2)
    result = await agent.run("Anything")
    assert result.failure_reason
    assert result.succeeded is False
