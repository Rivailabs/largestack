"""YAML declarative agent tests."""

import sys, tempfile, os

sys.path.insert(0, ".")


def test_load_agent_from_yaml():
    try:
        import yaml
    except ImportError:
        return  # skip
    from largestack._core.yaml_agent import build_agent

    config = {
        "name": "test",
        "model": "openai/gpt-4o-mini",
        "instructions": "Be concise",
        "cost_budget": 0.50,
    }
    agent = build_agent(config)
    assert agent.name == "test"
    assert agent.llm == "openai/gpt-4o-mini"


def test_export_agent_to_yaml():
    try:
        import yaml
    except ImportError:
        return
    from largestack._core.yaml_agent import build_agent, export_agent

    agent = build_agent({"name": "exporter", "model": "openai/gpt-4o-mini"})
    path = os.path.join(tempfile.mkdtemp(), "out.yaml")
    export_agent(agent, path)
    assert os.path.exists(path)
