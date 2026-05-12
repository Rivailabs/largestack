"""v0.9.0: Tests for cookiecutter-style template directories."""
from __future__ import annotations

from pathlib import Path

import pytest


TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def test_all_template_directories_exist():
    """All 5 template directories shipped."""
    expected = {"simple_agent", "rag_app", "multi_agent", "fintech_app", "legaltech_app"}
    actual = {d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir()}
    assert expected.issubset(actual), f"Missing: {expected - actual}"


def test_each_template_has_readme():
    """Every template directory ships with a README."""
    for tpl_dir in TEMPLATES_DIR.iterdir():
        if not tpl_dir.is_dir():
            continue
        readme = tpl_dir / "README.md"
        assert readme.exists(), f"{tpl_dir.name} missing README.md"
        assert len(readme.read_text()) > 50, f"{tpl_dir.name} README too short"


def test_each_template_has_agent_or_workflow_yaml():
    """Every template has at least one yaml definition."""
    for tpl_dir in TEMPLATES_DIR.iterdir():
        if not tpl_dir.is_dir():
            continue
        has_yaml = (
            (tpl_dir / "agent.yaml").exists()
            or (tpl_dir / "workflow.yaml").exists()
        )
        assert has_yaml, f"{tpl_dir.name} has no agent.yaml or workflow.yaml"


def test_fintech_template_includes_dpdp_marker():
    """Fintech template explicitly references DPDP Act."""
    yaml_path = TEMPLATES_DIR / "fintech_app" / "agent.yaml"
    content = yaml_path.read_text()
    assert "DPDP_Act_2023" in content
    assert "RBI" in content


def test_legaltech_template_includes_act_markers():
    """Legal template references Indian Acts."""
    yaml_path = TEMPLATES_DIR / "legaltech_app" / "agent.yaml"
    content = yaml_path.read_text()
    assert "Indian_Contract_Act" in content


def test_template_yaml_validates_with_schema():
    """Each agent.yaml passes our v0.9 validator."""
    pytest.importorskip("yaml")
    import yaml as _yaml
    from largestack._core.yaml_schema import validate_agent_yaml, validate_workflow_yaml

    for tpl_dir in TEMPLATES_DIR.iterdir():
        if not tpl_dir.is_dir():
            continue
        agent_yaml = tpl_dir / "agent.yaml"
        if agent_yaml.exists():
            with open(agent_yaml) as f:
                data = _yaml.safe_load(f)
            errors = validate_agent_yaml(data)
            assert errors == [], f"{tpl_dir.name}/agent.yaml errors: {errors}"
        wf_yaml = tpl_dir / "workflow.yaml"
        if wf_yaml.exists():
            with open(wf_yaml) as f:
                data = _yaml.safe_load(f)
            errors = validate_workflow_yaml(data)
            assert errors == [], f"{tpl_dir.name}/workflow.yaml errors: {errors}"
