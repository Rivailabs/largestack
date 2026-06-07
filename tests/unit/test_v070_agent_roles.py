"""v0.7.0: Agent role template tests."""

from __future__ import annotations

import pytest


def test_list_roles_returns_all_nine():
    from largestack._core.agent_roles import list_roles

    roles = list_roles()
    assert len(roles) == 9
    assert "researcher" in roles
    assert "writer" in roles
    assert "critic" in roles
    assert "reviewer" in roles
    assert "planner" in roles
    assert "summarizer" in roles
    assert "analyst" in roles
    assert "coder" in roles
    assert "editor" in roles


def test_role_prompt_returns_template_text():
    from largestack._core.agent_roles import role_prompt

    text = role_prompt("researcher")
    assert "research agent" in text.lower()
    assert "verifiable facts" in text.lower()


def test_role_prompt_case_insensitive():
    from largestack._core.agent_roles import role_prompt

    assert role_prompt("WRITER") == role_prompt("writer")
    assert role_prompt(" Critic ") == role_prompt("critic")


def test_role_prompt_unknown_raises():
    from largestack._core.agent_roles import role_prompt

    with pytest.raises(ValueError, match="unknown role"):
        role_prompt("supervillain")


def test_each_role_has_substantive_content():
    """Every template should be at least 200 chars (i.e. real content)."""
    from largestack._core.agent_roles import ROLES

    for role, prompt in ROLES.items():
        assert len(prompt) >= 200, f"role {role!r} template too short"
        assert "\n" in prompt  # multi-line


def test_role_agent_builds_agent_with_role_prompt():
    from largestack._core.agent_roles import role_agent

    agent = role_agent("researcher", llm="openai/gpt-4o-mini")
    assert agent.name == "researcher"
    assert agent.llm == "openai/gpt-4o-mini"
    assert "research agent" in agent.instructions.lower()


def test_role_agent_custom_name():
    from largestack._core.agent_roles import role_agent

    agent = role_agent("writer", llm="openai/gpt-4o-mini", name="my_writer")
    assert agent.name == "my_writer"


def test_role_agent_forwards_kwargs():
    from largestack._core.agent_roles import role_agent

    agent = role_agent(
        "critic",
        llm="openai/gpt-4o-mini",
        cost_budget=0.10,
        max_turns=5,
    )
    assert agent.cost_budget == 0.10
    assert agent.max_turns == 5
