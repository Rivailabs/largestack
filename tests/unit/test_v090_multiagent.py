"""v0.9.0: Tests for Supervisor, Swarm, and StructuredChatAgent."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Supervisor --------------------

@pytest.mark.asyncio
async def test_supervisor_routes_to_specialist():
    from largestack._core.multiagent import Supervisor

    routing = MagicMock(content="researcher\nGather facts about X")
    final = MagicMock(content="research findings")

    routing_2 = MagicMock(content="FINAL_ANSWER")

    supervisor = MagicMock()
    supervisor.run = AsyncMock(side_effect=[routing, routing_2])
    researcher = MagicMock()
    researcher.run = AsyncMock(return_value=final)

    sv = Supervisor(
        supervisor_agent=supervisor,
        agents={"researcher": researcher, "writer": MagicMock()},
        agent_descriptions={"researcher": "research", "writer": "write"},
    )
    result = await sv.run("Find out about X")

    assert len(result.steps) == 1
    assert result.steps[0].agent_name == "researcher"
    assert "research findings" in result.final_answer


@pytest.mark.asyncio
async def test_supervisor_handles_unknown_agent_name():
    from largestack._core.multiagent import Supervisor

    bad = MagicMock(content="nonexistent_agent\ntask")
    good = MagicMock(content="researcher\ntask")
    final = MagicMock(content="done")
    final_route = MagicMock(content="FINAL_ANSWER")

    supervisor = MagicMock()
    supervisor.run = AsyncMock(side_effect=[bad, good, final_route])
    researcher = MagicMock()
    researcher.run = AsyncMock(return_value=final)

    sv = Supervisor(
        supervisor_agent=supervisor,
        agents={"researcher": researcher},
    )
    result = await sv.run("task")
    # First step records error, second routes correctly
    assert any(s.agent_name == "researcher" for s in result.steps)


@pytest.mark.asyncio
async def test_supervisor_caps_at_max_iterations():
    from largestack._core.multiagent import Supervisor
    # Always route, never finish
    forever = MagicMock(content="researcher\ntask")
    research_resp = MagicMock(content="more")

    supervisor = MagicMock()
    supervisor.run = AsyncMock(return_value=forever)
    researcher = MagicMock()
    researcher.run = AsyncMock(return_value=research_resp)

    sv = Supervisor(
        supervisor_agent=supervisor,
        agents={"researcher": researcher},
        max_iterations=3,
    )
    result = await sv.run("task")
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_supervisor_validates_empty_agents():
    from largestack._core.multiagent import Supervisor
    supervisor = MagicMock()
    with pytest.raises(ValueError, match="empty"):
        Supervisor(supervisor_agent=supervisor, agents={})


# -------------------- Swarm --------------------

@pytest.mark.asyncio
async def test_swarm_no_handoff_returns_first_agent_answer():
    from largestack._core.multiagent import Swarm

    a1 = MagicMock()
    a1.run = AsyncMock(return_value=MagicMock(content="I can answer this directly: 42"))
    a2 = MagicMock()
    a2.run = AsyncMock()

    swarm = Swarm(
        agents={"first": a1, "second": a2},
        starting_agent="first",
    )
    result = await swarm.run("simple question")
    assert "42" in result.final_answer
    assert result.final_agent == "first"
    assert len(result.steps) == 1
    a2.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_swarm_handoff_chains():
    from largestack._core.multiagent import Swarm

    a1_resp = MagicMock(content="I need help with this.\nHANDOFF: specialist")
    a2_resp = MagicMock(content="The answer is 42.")

    a1 = MagicMock()
    a1.run = AsyncMock(return_value=a1_resp)
    a2 = MagicMock()
    a2.run = AsyncMock(return_value=a2_resp)

    swarm = Swarm(
        agents={"general": a1, "specialist": a2},
        starting_agent="general",
    )
    result = await swarm.run("complex question")
    assert "42" in result.final_answer
    assert result.final_agent == "specialist"
    assert len(result.steps) == 2
    assert result.steps[0].handed_off is True
    assert result.steps[0].to_agent == "specialist"


@pytest.mark.asyncio
async def test_swarm_unknown_handoff_target_treated_as_final():
    from largestack._core.multiagent import Swarm

    a1_resp = MagicMock(content="HANDOFF: nonexistent")
    a1 = MagicMock()
    a1.run = AsyncMock(return_value=a1_resp)

    swarm = Swarm(
        agents={"only": a1},
        starting_agent="only",
    )
    result = await swarm.run("q")
    assert result.final_agent == "only"
    assert len(result.steps) == 1


@pytest.mark.asyncio
async def test_swarm_validates():
    from largestack._core.multiagent import Swarm
    with pytest.raises(ValueError, match="empty"):
        Swarm(agents={})

    a = MagicMock()
    with pytest.raises(ValueError):
        Swarm(agents={"a": a}, starting_agent="missing")


@pytest.mark.asyncio
async def test_swarm_caps_handoff_chain():
    from largestack._core.multiagent import Swarm
    # Two agents that hand off forever
    a_handoff = MagicMock(content="HANDOFF: b")
    b_handoff = MagicMock(content="HANDOFF: a")

    a = MagicMock()
    a.run = AsyncMock(return_value=a_handoff)
    b = MagicMock()
    b.run = AsyncMock(return_value=b_handoff)

    swarm = Swarm(
        agents={"a": a, "b": b},
        starting_agent="a",
        max_iterations=3,
    )
    result = await swarm.run("q")
    assert len(result.steps) == 3


# -------------------- StructuredChatAgent --------------------

@pytest.mark.asyncio
async def test_structured_chat_executes_tool_then_final():
    from largestack._core.multiagent import StructuredChatAgent

    # Build a fake tool with LARGESTACK schema
    fake_tool = AsyncMock(return_value="search returned: 42")
    fake_tool._tool_schema = {"name": "search", "description": "search the web"}

    # Step 1: agent says use tool
    step1 = MagicMock(content=json.dumps({
        "action": "search", "action_input": {"q": "answer to life"}
    }))
    # Step 2: agent gives final answer
    step2 = MagicMock(content=json.dumps({
        "action": "Final Answer", "action_input": "The answer is 42"
    }))

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=[step1, step2])
    agent.tools = [fake_tool]

    sca = StructuredChatAgent(agent)
    result = await sca.run("What is the answer?")

    assert "42" in result.final_answer
    assert len(result.steps) == 1  # 1 tool execution before final
    fake_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_structured_chat_handles_invalid_json():
    from largestack._core.multiagent import StructuredChatAgent

    # LLM returned plain text not JSON
    step = MagicMock(content="I think the answer is 42, but I'm not sure.")
    agent = MagicMock()
    agent.run = AsyncMock(return_value=step)
    agent.tools = []

    sca = StructuredChatAgent(agent)
    result = await sca.run("q")
    # Falls through to plain text
    assert "42" in result.final_answer


@pytest.mark.asyncio
async def test_structured_chat_unknown_tool_recovers():
    from largestack._core.multiagent import StructuredChatAgent

    # Step 1: try unknown tool
    step1 = MagicMock(content=json.dumps({
        "action": "nonexistent_tool", "action_input": {}
    }))
    # Step 2: give up and answer
    step2 = MagicMock(content=json.dumps({
        "action": "Final Answer", "action_input": "ok"
    }))

    agent = MagicMock()
    agent.run = AsyncMock(side_effect=[step1, step2])
    agent.tools = []

    sca = StructuredChatAgent(agent)
    result = await sca.run("q")
    assert result.final_answer == "ok"
    # First step records the unknown-tool error
    assert any("unknown tool" in s.get("error", "") for s in result.steps)


@pytest.mark.asyncio
async def test_structured_chat_strips_code_fences():
    """LLMs often wrap JSON in ```json fences."""
    from largestack._core.multiagent import StructuredChatAgent

    step1 = MagicMock(content="```json\n" + json.dumps({
        "action": "Final Answer", "action_input": "wrapped"
    }) + "\n```")
    agent = MagicMock()
    agent.run = AsyncMock(return_value=step1)
    agent.tools = []

    sca = StructuredChatAgent(agent)
    result = await sca.run("q")
    assert result.final_answer == "wrapped"


@pytest.mark.asyncio
async def test_structured_chat_max_iterations():
    """Loop without Final Answer eventually terminates."""
    from largestack._core.multiagent import StructuredChatAgent

    fake_tool = AsyncMock(return_value="x")
    fake_tool._tool_schema = {"name": "t", "description": "t"}

    forever = MagicMock(content=json.dumps({
        "action": "t", "action_input": {}
    }))
    agent = MagicMock()
    agent.run = AsyncMock(return_value=forever)
    agent.tools = [fake_tool]

    sca = StructuredChatAgent(agent, max_iterations=3)
    result = await sca.run("q")
    assert result.iterations == 3
    assert "max iterations" in result.final_answer
