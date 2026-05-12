"""Tests for AgentContext structured data passing."""
import sys; sys.path.insert(0, ".")
from largestack._core.context import AgentContext
from largestack.types import AgentResult

def test_context_creation():
    ctx = AgentContext(task="Analyze data")
    assert ctx.task == "Analyze data" and len(ctx.outputs) == 0

def test_context_add_result():
    ctx = AgentContext(task="test")
    ctx.add_result("agent1", AgentResult(content="output1", agent_name="agent1", total_cost=0.01))
    assert ctx.total_cost == 0.01 and "agent1" in ctx.history

def test_context_build_prompt():
    ctx = AgentContext(task="Analyze AI")
    ctx.add_result("researcher", AgentResult(content="AI is growing", agent_name="researcher",
        total_cost=0.01, tool_calls_made=["web_search"]))
    prompt = ctx.build_prompt("writer")
    assert "Analyze AI" in prompt and "AI is growing" in prompt and "web_search" in prompt

def test_context_last_output():
    ctx = AgentContext(task="test")
    assert ctx.last_output() == "test"  # No history, returns task
    ctx.add_result("a1", AgentResult(content="result1", agent_name="a1"))
    assert ctx.last_output() == "result1"

def test_context_shared_state():
    ctx = AgentContext(task="t")
    ctx.set("key", "value")
    assert ctx.get("key") == "value"
    assert ctx.get("missing", "default") == "default"

def test_context_multiple_agents():
    ctx = AgentContext(task="pipeline")
    for i in range(5):
        ctx.add_result(f"agent{i}", AgentResult(content=f"output{i}", agent_name=f"agent{i}", total_cost=0.01))
    assert len(ctx.history) == 5 and ctx.total_cost == 0.05
    prompt = ctx.build_prompt("final")
    for i in range(5):
        assert f"output{i}" in prompt
