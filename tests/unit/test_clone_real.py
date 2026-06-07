"""Tests that actually verify Agent.clone() forwarding (reviewer's critique addressed)."""

import sys, asyncio

sys.path.insert(0, ".")


def test_clone_forwards_on_complete_callback():
    """Verify clone preserves _on_complete callback (was None before fix)."""
    from largestack import Agent

    fired = []

    def cb(result):
        fired.append("called")

    a = Agent(name="orig", llm="openai/gpt-4o-mini", on_complete=cb)
    b = a.clone()
    assert b._on_complete is not None, "clone dropped on_complete callback"
    assert b._on_complete is cb, "clone has wrong callback"


def test_clone_forwards_on_error():
    from largestack import Agent

    def err_cb(e):
        pass

    a = Agent(name="orig", llm="openai/gpt-4o-mini", on_error=err_cb)
    b = a.clone()
    assert b._on_error is err_cb


def test_clone_forwards_steering_rules():
    """Steering rules must be forwarded so cloned agent has same behavior."""
    from largestack import Agent

    rules = []  # empty list of steering rules
    a = Agent(name="orig", llm="openai/gpt-4o-mini", steering=rules)
    b = a.clone()
    # Cloned must have its own SteeringEngine built from same rules
    assert hasattr(b, "_steer")
    assert b._steering_rules == rules


def test_clone_forwards_retries():
    from largestack import Agent

    a = Agent(name="orig", llm="openai/gpt-4o-mini", retries=5)
    b = a.clone()
    assert b.retries == 5


def test_clone_overrides_take_precedence():
    from largestack import Agent

    a = Agent(name="orig", llm="openai/gpt-4o-mini", retries=3)
    b = a.clone(retries=10)
    assert b.retries == 10
