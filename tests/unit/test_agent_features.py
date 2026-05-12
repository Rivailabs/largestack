"""Tests for Agent features: structured output, vision, retry, callbacks, shared memory."""
import asyncio, sys, os, pytest
sys.path.insert(0, ".")

def test_agent_retries_default_zero():
    from largestack import Agent
    a = Agent(name="t", llm="deepseek/deepseek-chat", guardrails=None)
    assert a.retries == 0  # No retry by default

def test_agent_retries_naming():
    from largestack import Agent
    a = Agent(name="t", llm="deepseek/deepseek-chat", guardrails=None, retries=2)
    assert a.retries == 2  # 2 retries = 3 total attempts

def test_agent_fallback_set():
    from largestack import Agent
    backup = Agent(name="backup", llm="deepseek/deepseek-chat", guardrails=None)
    primary = Agent(name="primary", llm="deepseek/deepseek-chat", guardrails=None, fallback=backup)
    assert primary.fallback is backup

def test_agent_shared_memory():
    from largestack import Agent
    from largestack._memory.shared import SharedMemorySpace
    shared = SharedMemorySpace()
    a = Agent(name="t", shared_memory=shared, llm="deepseek/deepseek-chat", guardrails=None)
    assert a.shared_memory is shared

def test_agent_callbacks():
    from largestack import Agent
    results = []
    a = Agent(name="t", llm="deepseek/deepseek-chat", guardrails=None,
              on_complete=lambda r: results.append("done"),
              on_error=lambda e: results.append("err"))
    assert a._on_complete is not None
    assert a._on_error is not None

def test_agent_clone():
    from largestack import Agent
    a = Agent(name="original", instructions="Be helpful", llm="deepseek/deepseek-chat", guardrails=None)
    b = a.clone(name="clone", llm="openai/gpt-4o-mini")
    assert b.name == "clone" and b.llm == "openai/gpt-4o-mini"

def test_agent_guardrails_from_names():
    from largestack import Agent
    a = Agent(name="t", guardrails=["pii", "injection", "toxicity"], llm="deepseek/deepseek-chat")
    assert len(a._guards.guards) == 3

def test_agent_repr():
    from largestack import Agent
    a = Agent(name="test", llm="deepseek/deepseek-chat", guardrails=None)
    r = repr(a)
    assert "test" in r and "deepseek" in r
