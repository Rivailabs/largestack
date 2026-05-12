"""YAML schema + env interpolation + validation (v0.9.0).

Closes the LangGraph YAML config gap. Provides:

- ``load_yaml_with_env`` — loads YAML with ``${VAR}`` and ``${VAR:default}`` interpolation
- ``validate_agent_yaml`` — validates agent definitions against schema
- ``validate_workflow_yaml`` — validates multi-agent workflow YAML
- ``load_multi_agent_yaml`` — loads multiple agents from a single YAML file

Schemas use jsonschema if available; falls back to manual validation.
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("largestack.yaml_schema")


# Pattern for ${VAR} and ${VAR:default} substitution
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def interpolate_env(value: Any) -> Any:
    """Recursively substitute ``${VAR}`` and ``${VAR:default}`` in YAML data.

    Args:
        value: any YAML-loaded structure (dict / list / str / scalar).

    Returns:
        Same structure with strings interpolated. Non-strings unchanged.

    Examples:
        ``"${OPENAI_API_KEY}"`` → value of OPENAI_API_KEY env var
        ``"${MODEL:gpt-4o-mini}"`` → MODEL value or "gpt-4o-mini" default
    """
    if isinstance(value, str):
        def _sub(m: re.Match) -> str:
            var_name = m.group(1)
            default = m.group(2)
            return os.environ.get(var_name, default if default is not None else m.group(0))
        return _ENV_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {k: interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_env(v) for v in value]
    return value


def load_yaml_with_env(path: str | Path) -> dict:
    """Load a YAML file with environment variable interpolation.

    Args:
        path: file path.

    Returns:
        Parsed YAML with all ``${VAR}`` and ``${VAR:default}``
        substitutions applied.
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("pyyaml required: pip install pyyaml") from e

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"YAML file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"YAML must be a dict at top level, got {type(raw).__name__}")

    return interpolate_env(raw)


# -------------------- Agent YAML schema --------------------

AGENT_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "model": {"type": "string"},
        "instructions": {"type": "string"},
        "tools": {"type": "array", "items": {"type": "string"}},
        "guardrails": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "pii", "indian_pii", "injection", "prompt_leak",
                    "hallucination", "toxicity", "off_topic",
                ],
            },
        },
        "max_turns": {"type": "integer", "minimum": 1, "maximum": 100},
        "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0},
        "compliance": {"type": "array", "items": {"type": "string"}},
        "memory": {"type": "object"},
        "callbacks": {"type": "array"},
    },
}

WORKFLOW_SCHEMA = {
    "type": "object",
    "required": ["name", "agents"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "agents": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": AGENT_SCHEMA,
        },
        "graph": {
            "type": "object",
            "properties": {
                "nodes": {"type": "array", "items": {"type": "string"}},
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["from", "to"],
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "condition": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def validate_agent_yaml(data: dict) -> list[str]:
    """Validate an agent YAML structure.

    Returns:
        List of validation error messages. Empty list = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["agent config must be a dict"]

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' is required and must be a non-empty string")

    model = data.get("model")
    if model is not None and not isinstance(model, str):
        errors.append("'model' must be a string")

    instructions = data.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        errors.append("'instructions' must be a string")

    tools = data.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            errors.append("'tools' must be a list")
        elif not all(isinstance(t, str) for t in tools):
            errors.append("'tools' items must be strings")

    guardrails = data.get("guardrails")
    if guardrails is not None:
        if not isinstance(guardrails, list):
            errors.append("'guardrails' must be a list")
        else:
            allowed = {
                "pii", "indian_pii", "injection", "prompt_leak",
                "hallucination", "toxicity", "off_topic",
            }
            for g in guardrails:
                if g not in allowed:
                    errors.append(f"unknown guardrail {g!r}; allowed: {sorted(allowed)}")

    max_turns = data.get("max_turns")
    if max_turns is not None:
        if not isinstance(max_turns, int):
            errors.append("'max_turns' must be an integer")
        elif not (1 <= max_turns <= 100):
            errors.append("'max_turns' must be between 1 and 100")

    temperature = data.get("temperature")
    if temperature is not None:
        if not isinstance(temperature, (int, float)):
            errors.append("'temperature' must be numeric")
        elif not (0.0 <= temperature <= 2.0):
            errors.append("'temperature' must be in [0.0, 2.0]")

    return errors


def validate_workflow_yaml(data: dict) -> list[str]:
    """Validate a workflow / multi-agent YAML structure.

    Returns:
        List of validation errors. Empty = valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["workflow config must be a dict"]

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' is required")

    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        errors.append("'agents' must be a non-empty dict")
    else:
        for agent_name, agent_def in agents.items():
            if not isinstance(agent_def, dict):
                errors.append(f"agent {agent_name!r} must be a dict")
                continue
            # Validate each as an agent (minus the "name" requirement, since
            # the dict key IS the name)
            sub_errs = validate_agent_yaml({**agent_def, "name": agent_name})
            for e in sub_errs:
                errors.append(f"agent[{agent_name}]: {e}")

    graph = data.get("graph")
    if graph is not None:
        if not isinstance(graph, dict):
            errors.append("'graph' must be a dict")
        else:
            nodes = graph.get("nodes", [])
            if nodes and not isinstance(nodes, list):
                errors.append("graph.nodes must be a list")
            edges = graph.get("edges", [])
            if not isinstance(edges, list):
                errors.append("graph.edges must be a list")
            else:
                # Validate each edge references known agent (or START/END)
                known = (set(agents.keys()) if isinstance(agents, dict) else set()) | {"START", "END"}
                for i, edge in enumerate(edges):
                    if not isinstance(edge, dict):
                        errors.append(f"graph.edges[{i}] must be a dict")
                        continue
                    src = edge.get("from")
                    dst = edge.get("to")
                    if src not in known:
                        errors.append(f"graph.edges[{i}].from references unknown node: {src!r}")
                    if dst not in known:
                        errors.append(f"graph.edges[{i}].to references unknown node: {dst!r}")

    return errors


# -------------------- Multi-agent loading --------------------

def load_multi_agent_yaml(path: str | Path) -> dict:
    """Load a multi-agent YAML file with validation.

    Returns:
        Dict with parsed and validated structure.

    Raises:
        ValueError if the YAML doesn't pass validation.
    """
    data = load_yaml_with_env(path)
    errors = validate_workflow_yaml(data)
    if errors:
        raise ValueError(
            f"workflow YAML {path} validation failed:\n  - "
            + "\n  - ".join(errors)
        )
    return data
