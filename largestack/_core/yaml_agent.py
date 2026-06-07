"""YAML-declarative agents — load agents/workflows from config.

Inspired by Microsoft Agent Framework + Google ADK Agent Config.

Usage:
    # agent.yaml:
    # name: support-bot
    # model: openai/gpt-4o-mini
    # instructions: Be helpful
    # tools: [search_kb, create_ticket]
    # guardrails: [pii, injection]

    from largestack._core.yaml_agent import load_agent
    agent = load_agent("agent.yaml")
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("largestack.yaml_agent")


def load_agent(path: str | Path, tool_registry: dict | None = None):
    """Load an agent from a YAML config file."""
    try:
        import yaml
    except ImportError:
        raise ImportError("pip install pyyaml for YAML agent support")

    path = Path(path)
    config = yaml.safe_load(path.read_text())
    return build_agent(config, tool_registry or {})


def build_agent(config: dict, tool_registry: dict | None = None):
    """Build an Agent from a config dict."""
    from largestack import Agent
    from largestack.guardrails import create_guardrails

    # Resolve tools
    tools = []
    for tname in config.get("tools", []):
        if tool_registry and tname in tool_registry:
            tools.append(tool_registry[tname])
        else:
            log.warning(f"Tool '{tname}' not found in registry")

    # Resolve guardrails (validate names)
    guards_config = config.get("guardrails", [])
    if guards_config:
        valid_guards = {
            "pii",
            "injection",
            "toxicity",
            "hallucination",
            "topic",
            "pii_ml",
            "prompt_guard",
            "nli_hallucination",
        }
        invalid = [g for g in guards_config if g not in valid_guards]
        if invalid:
            raise ValueError(f"Unknown guardrail(s) {invalid}. Valid: {sorted(valid_guards)}")
        guards = create_guardrails(**{g: True for g in guards_config})
    else:
        guards = None

    return Agent(
        name=config.get("name", "agent"),
        instructions=config.get("instructions", ""),
        llm=config.get("model", config.get("llm", "openai/gpt-4o-mini")),
        tools=tools,
        guardrails=guards,
        cost_budget=config.get("cost_budget", 1.0),
        max_turns=config.get("max_turns", 5),
    )


def load_workflow(path: str | Path, tool_registry: dict | None = None):
    """Load a workflow from YAML.

    workflow.yaml:
      name: research_pipeline
      mode: dag
      nodes:
        - id: research
          agent: researcher.yaml
        - id: write
          agent: writer.yaml
          deps: [research]
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("pip install pyyaml for YAML workflow support")

    from largestack import Workflow

    path = Path(path)
    config = yaml.safe_load(path.read_text())

    wf = Workflow(config.get("name", "workflow"), mode=config.get("mode", "dag"))
    base = path.parent

    for node in config.get("nodes", []):
        node_id = node["id"]
        agent_path = node.get("agent")
        if agent_path:
            # Resolve relative paths
            ap = (base / agent_path) if not Path(agent_path).is_absolute() else Path(agent_path)
            agent = load_agent(ap, tool_registry)

            # Capture both agent AND node_id via default args
            async def fn(state, _agent=agent, _node_id=node_id):
                r = await _agent.run(state.get("input", ""))
                state[f"{_node_id}_output"] = r.content
                return state

            wf.add_node(node_id, fn, deps=node.get("deps", []))

    return wf


def export_agent(agent, path: str | Path):
    """Export an Agent's config to YAML."""
    try:
        import yaml
    except ImportError:
        raise ImportError("pip install pyyaml")

    config = {
        "name": agent.name,
        "model": agent.llm,
        "instructions": agent.instructions,
        "cost_budget": agent.cost_budget,
        "max_turns": agent.max_turns,
        "tools": [t.name if hasattr(t, "name") else str(t) for t in (agent.tools or [])],
    }

    Path(path).write_text(yaml.safe_dump(config, sort_keys=False))
