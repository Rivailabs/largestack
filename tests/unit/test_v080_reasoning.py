"""v0.8.0: Reasoning pattern tests (CoT, Self-Ask, Plan-and-Execute, Reflexion)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- ChainOfThought --------------------

@pytest.mark.asyncio
async def test_cot_extracts_final_answer():
    from largestack._core.reasoning import ChainOfThought

    fake_result = MagicMock()
    fake_result.content = (
        "Reasoning:\n"
        "17 * 23 = 17 * 20 + 17 * 3 = 340 + 51 = 391\n\n"
        "Final Answer:\n"
        "391"
    )
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    cot = ChainOfThought(agent)
    result = await cot.run("What is 17 * 23?")

    # Agent was called with CoT prefix
    call_arg = agent.run.await_args.args[0]
    assert "step by step" in call_arg.lower()
    # Final answer extracted
    assert getattr(result, "final_answer", "").strip() == "391"


@pytest.mark.asyncio
async def test_cot_handles_missing_final_answer_section():
    """If LLM doesn't follow format, full content becomes final_answer."""
    from largestack._core.reasoning import ChainOfThought

    fake_result = MagicMock()
    fake_result.content = "Just a plain answer with no format."
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    cot = ChainOfThought(agent)
    result = await cot.run("Q?")
    assert "plain answer" in getattr(result, "final_answer", "")


# -------------------- SelfAsk --------------------

@pytest.mark.asyncio
async def test_self_ask_decomposes_and_synthesizes():
    from largestack._core.reasoning import SelfAsk

    fake_response = """Sub-questions:
- Q1: What year did the moon landing occur?
- Q2: Who was US president that year?

Sub-answers:
- A1: 1969
- A2: Richard Nixon

Final Answer:
Richard Nixon was president when the moon landing occurred."""

    fake_result = MagicMock()
    fake_result.content = fake_response
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    self_ask = SelfAsk(agent)
    result = await self_ask.run("Who was US president when the moon landing happened?")

    assert len(result.sub_questions) == 2
    assert "moon landing" in result.sub_questions[0].lower()
    assert len(result.sub_answers) == 2
    assert "1969" in result.sub_answers[0]
    assert "Nixon" in result.final_answer


@pytest.mark.asyncio
async def test_self_ask_handles_partial_format():
    from largestack._core.reasoning import SelfAsk
    fake_result = MagicMock()
    fake_result.content = "Just a plain response without sections."
    agent = MagicMock()
    agent.run = AsyncMock(return_value=fake_result)

    self_ask = SelfAsk(agent)
    result = await self_ask.run("Q")
    assert result.sub_questions == []
    assert "Just a plain" in result.final_answer


# -------------------- PlanAndExecute --------------------

@pytest.mark.asyncio
async def test_plan_and_execute_full_flow():
    """Planner produces 3 steps, executor runs each in sequence."""
    from largestack._core.reasoning import PlanAndExecute

    plan_text = """1. Identify the topic
2. Gather facts
3. Write a summary"""

    plan_response = MagicMock()
    plan_response.content = plan_text

    exec_responses = [
        MagicMock(content="Topic: AI agents"),
        MagicMock(content="Facts: agents use LLMs + tools"),
        MagicMock(content="Summary: AI agents combine LLMs with tools to perform tasks."),
    ]
    exec_iter = iter(exec_responses)

    planner = MagicMock()
    planner.run = AsyncMock(return_value=plan_response)
    executor = MagicMock()
    executor.run = AsyncMock(side_effect=lambda *a, **kw: next(exec_iter))

    pe = PlanAndExecute(planner=planner, executor=executor)
    result = await pe.run("Write a short summary about AI agents")

    assert len(result.plan) == 3
    assert len(result.steps) == 3
    assert "Summary" in result.final_answer
    assert result.steps[0].number == 1
    assert "Topic" in result.steps[0].result


@pytest.mark.asyncio
async def test_plan_and_execute_respects_max_steps():
    from largestack._core.reasoning import PlanAndExecute
    plan_text = "\n".join(f"{i}. step {i}" for i in range(1, 11))
    plan_response = MagicMock()
    plan_response.content = plan_text
    exec_response = MagicMock()
    exec_response.content = "result"

    planner = MagicMock()
    planner.run = AsyncMock(return_value=plan_response)
    executor = MagicMock()
    executor.run = AsyncMock(return_value=exec_response)

    pe = PlanAndExecute(planner=planner, executor=executor, max_steps=3)
    result = await pe.run("goal")
    assert len(result.steps) == 3


@pytest.mark.asyncio
async def test_plan_and_execute_handles_step_failure():
    """A failing step doesn't kill the run — error captured, plan continues."""
    from largestack._core.reasoning import PlanAndExecute

    plan_response = MagicMock()
    plan_response.content = "1. step a\n2. step b"

    call_count = [0]
    async def exec_fn(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("step 1 failed")
        return MagicMock(content="step 2 result")

    planner = MagicMock()
    planner.run = AsyncMock(return_value=plan_response)
    executor = MagicMock()
    executor.run = AsyncMock(side_effect=exec_fn)

    pe = PlanAndExecute(planner=planner, executor=executor)
    result = await pe.run("goal")
    assert len(result.steps) == 2
    assert "failed" in result.steps[0].result.lower()
    assert "step 2 result" in result.steps[1].result


@pytest.mark.asyncio
async def test_plan_and_execute_no_plan_returns_empty():
    """If planner produces nothing parseable, no steps run."""
    from largestack._core.reasoning import PlanAndExecute
    plan_response = MagicMock()
    plan_response.content = "I don't know how to plan this."

    planner = MagicMock()
    planner.run = AsyncMock(return_value=plan_response)
    executor = MagicMock()
    executor.run = AsyncMock()

    pe = PlanAndExecute(planner=planner, executor=executor)
    result = await pe.run("vague goal")
    assert result.plan == []
    assert result.steps == []
    executor.run.assert_not_awaited()


# -------------------- Reflexion --------------------

@pytest.mark.asyncio
async def test_reflexion_stops_on_approved():
    """When critic returns APPROVED, the loop ends."""
    from largestack._core.reasoning import Reflexion

    answer = MagicMock(content="initial answer")
    critique = MagicMock(content="APPROVED — looks good.")

    agent = MagicMock()
    agent.run = AsyncMock(return_value=answer)
    critic = MagicMock()
    critic.run = AsyncMock(return_value=critique)

    rfx = Reflexion(agent=agent, critic=critic, max_iterations=3)
    result = await rfx.run("question?")
    assert result.final_answer == "initial answer"
    # Should have called: 1 answer + 1 critique
    assert agent.run.await_count == 1


@pytest.mark.asyncio
async def test_reflexion_revises_until_approved():
    """Revise → critique → approve flow."""
    from largestack._core.reasoning import Reflexion

    initial = MagicMock(content="first attempt")
    revised = MagicMock(content="better answer")
    critique_bad = MagicMock(content="Issues: wrong, fix it")
    critique_good = MagicMock(content="APPROVED")

    agent_responses = [initial, revised]
    agent_iter = iter(agent_responses)
    critic_responses = [critique_bad, critique_good]
    critic_iter = iter(critic_responses)

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=lambda *a, **kw: next(agent_iter))
    critic = MagicMock()
    critic.run = AsyncMock(side_effect=lambda *a, **kw: next(critic_iter))

    rfx = Reflexion(agent=agent, critic=critic, max_iterations=3)
    result = await rfx.run("Q?")
    assert result.final_answer == "better answer"


@pytest.mark.asyncio
async def test_reflexion_caps_at_max_iterations():
    """If never approved, loop stops at max_iterations."""
    from largestack._core.reasoning import Reflexion

    answer_count = [0]
    async def agent_run(*a, **kw):
        answer_count[0] += 1
        return MagicMock(content=f"attempt {answer_count[0]}")

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=agent_run)
    critic = MagicMock()
    critic.run = AsyncMock(return_value=MagicMock(content="needs improvement"))

    rfx = Reflexion(agent=agent, critic=critic, max_iterations=2)
    result = await rfx.run("Q?")
    # 1 initial + 2 revisions = 3 agent calls
    assert agent.run.await_count == 3
    # 2 critiques
    assert critic.run.await_count == 2


@pytest.mark.asyncio
async def test_reflexion_history_tracked():
    """History should record all attempts and critiques."""
    from largestack._core.reasoning import Reflexion
    agent = MagicMock()
    agent.run = AsyncMock(return_value=MagicMock(content="x"))
    critic = MagicMock()
    critic.run = AsyncMock(return_value=MagicMock(content="APPROVED"))
    rfx = Reflexion(agent=agent, critic=critic)
    result = await rfx.run("Q")
    assert len(result.history) >= 2  # at least answer + critique
    assert result.history[0]["role"] == "answer"
    assert result.history[1]["role"] == "critique"
