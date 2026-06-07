"""v0.9.0: Tests for YAML schema + env interpolation."""

from __future__ import annotations

import pytest

yaml = pytest.importorskip("yaml")


# -------------------- env interpolation --------------------


def test_interpolate_simple_var(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.setenv("MY_VAR", "hello")
    assert interpolate_env("${MY_VAR}") == "hello"


def test_interpolate_with_default_when_var_missing(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.delenv("UNSET_VAR", raising=False)
    assert interpolate_env("${UNSET_VAR:fallback}") == "fallback"


def test_interpolate_with_default_when_var_set(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.setenv("SET_VAR", "actual")
    # Set values override defaults
    assert interpolate_env("${SET_VAR:fallback}") == "actual"


def test_interpolate_unset_no_default_keeps_placeholder(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.delenv("UNSET_NO_DEFAULT", raising=False)
    # Unset with no default: leave the original placeholder
    assert interpolate_env("${UNSET_NO_DEFAULT}") == "${UNSET_NO_DEFAULT}"


def test_interpolate_recursive_dict(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.setenv("API_KEY", "secret123")
    monkeypatch.setenv("MODEL", "gpt-4")
    config = {
        "name": "agent",
        "credentials": {"key": "${API_KEY}"},
        "model": "${MODEL:default}",
    }
    out = interpolate_env(config)
    assert out["credentials"]["key"] == "secret123"
    assert out["model"] == "gpt-4"


def test_interpolate_recursive_list(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.setenv("X", "x_val")
    monkeypatch.setenv("Y", "y_val")
    out = interpolate_env(["${X}", "${Y}", "literal"])
    assert out == ["x_val", "y_val", "literal"]


def test_interpolate_preserves_non_strings():
    from largestack._core.yaml_schema import interpolate_env

    assert interpolate_env(42) == 42
    assert interpolate_env(3.14) == 3.14
    assert interpolate_env(None) is None
    assert interpolate_env(True) is True


def test_interpolate_multiple_vars_in_one_string(monkeypatch):
    from largestack._core.yaml_schema import interpolate_env

    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.setenv("PORT", "5432")
    result = interpolate_env("postgresql://${HOST}:${PORT}/db")
    assert result == "postgresql://localhost:5432/db"


# -------------------- load_yaml_with_env --------------------


def test_load_yaml_with_env(tmp_path, monkeypatch):
    from largestack._core.yaml_schema import load_yaml_with_env

    monkeypatch.setenv("MY_KEY", "abc123")
    p = tmp_path / "config.yaml"
    p.write_text("""\
name: test-agent
api_key: ${MY_KEY}
model: ${MODEL:gpt-4o-mini}
tools:
  - search
""")
    data = load_yaml_with_env(p)
    assert data["api_key"] == "abc123"
    assert data["model"] == "gpt-4o-mini"
    assert data["tools"] == ["search"]


def test_load_yaml_missing_file():
    from largestack._core.yaml_schema import load_yaml_with_env

    with pytest.raises(FileNotFoundError):
        load_yaml_with_env("/nonexistent.yaml")


def test_load_yaml_must_be_dict_at_root(tmp_path):
    from largestack._core.yaml_schema import load_yaml_with_env

    p = tmp_path / "list.yaml"
    p.write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="dict at top level"):
        load_yaml_with_env(p)


# -------------------- validate_agent_yaml --------------------


def test_validate_agent_minimal_valid():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml({"name": "agent1"})
    assert errors == []


def test_validate_agent_full_config():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml(
        {
            "name": "rich-agent",
            "model": "openai/gpt-4o-mini",
            "instructions": "Be helpful",
            "tools": ["search", "calculator"],
            "guardrails": ["pii", "injection"],
            "max_turns": 25,
            "temperature": 0.7,
        }
    )
    assert errors == []


def test_validate_agent_missing_name():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml({"model": "x"})
    assert any("name" in e for e in errors)


def test_validate_agent_unknown_guardrail():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml(
        {
            "name": "x",
            "guardrails": ["nonexistent_guardrail"],
        }
    )
    assert any("unknown guardrail" in e for e in errors)


def test_validate_agent_invalid_temperature():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml({"name": "x", "temperature": 5.0})
    assert any("temperature" in e for e in errors)


def test_validate_agent_invalid_max_turns():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml({"name": "x", "max_turns": 0})
    assert any("max_turns" in e for e in errors)


def test_validate_agent_tools_must_be_strings():
    from largestack._core.yaml_schema import validate_agent_yaml

    errors = validate_agent_yaml(
        {
            "name": "x",
            "tools": [{"obj": "not a string"}],
        }
    )
    assert any("tools" in e for e in errors)


# -------------------- validate_workflow_yaml --------------------


def test_validate_workflow_basic():
    from largestack._core.yaml_schema import validate_workflow_yaml

    errors = validate_workflow_yaml(
        {
            "name": "wf",
            "agents": {
                "researcher": {"model": "openai/gpt-4o-mini"},
                "writer": {"model": "openai/gpt-4o-mini"},
            },
        }
    )
    assert errors == []


def test_validate_workflow_with_graph():
    from largestack._core.yaml_schema import validate_workflow_yaml

    errors = validate_workflow_yaml(
        {
            "name": "wf",
            "agents": {"a": {}, "b": {}},
            "graph": {
                "nodes": ["a", "b"],
                "edges": [
                    {"from": "START", "to": "a"},
                    {"from": "a", "to": "b"},
                    {"from": "b", "to": "END"},
                ],
            },
        }
    )
    assert errors == []


def test_validate_workflow_unknown_node_in_edge():
    from largestack._core.yaml_schema import validate_workflow_yaml

    errors = validate_workflow_yaml(
        {
            "name": "wf",
            "agents": {"a": {}},
            "graph": {
                "edges": [{"from": "a", "to": "nonexistent"}],
            },
        }
    )
    assert any("nonexistent" in e for e in errors)


def test_validate_workflow_missing_agents():
    from largestack._core.yaml_schema import validate_workflow_yaml

    errors = validate_workflow_yaml({"name": "wf"})
    assert any("agents" in e for e in errors)


def test_validate_workflow_empty_agents():
    from largestack._core.yaml_schema import validate_workflow_yaml

    errors = validate_workflow_yaml({"name": "wf", "agents": {}})
    assert any("agents" in e for e in errors)


# -------------------- load_multi_agent_yaml --------------------


def test_load_multi_agent_full(tmp_path, monkeypatch):
    from largestack._core.yaml_schema import load_multi_agent_yaml

    monkeypatch.setenv("OPENAI_API_KEY", "sk-xxx")
    p = tmp_path / "wf.yaml"
    p.write_text("""\
name: my-workflow
agents:
  researcher:
    model: openai/gpt-4o-mini
    instructions: Research things
    tools: [web_search]
  writer:
    model: openai/gpt-4o-mini
graph:
  nodes: [researcher, writer]
  edges:
    - {from: START, to: researcher}
    - {from: researcher, to: writer}
    - {from: writer, to: END}
""")
    data = load_multi_agent_yaml(p)
    assert data["name"] == "my-workflow"
    assert "researcher" in data["agents"]
    assert "writer" in data["agents"]


def test_load_multi_agent_invalid_raises(tmp_path):
    from largestack._core.yaml_schema import load_multi_agent_yaml

    p = tmp_path / "bad.yaml"
    p.write_text("""\
name: bad
# missing agents key
""")
    with pytest.raises(ValueError, match="validation failed"):
        load_multi_agent_yaml(p)
