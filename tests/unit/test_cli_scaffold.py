"""Tests for largestack new/init production scaffolding."""

from pathlib import Path
import os
import pytest
import sys
import tempfile

sys.path.insert(0, ".")


def test_scaffold_agent_template():
    from largestack._cli.scaffold import TEMPLATES, available_templates

    assert "agent" in TEMPLATES
    assert "crew" in TEMPLATES
    assert "workflow" in TEMPLATES
    assert "mcp-server" in TEMPLATES
    for template in [
        "support-ticket",
        "rag",
        "code-review",
        "ml-automation",
        "website-builder",
        "video-pipeline",
        "social-media",
        "bfsi",
        "document-extraction",
    ]:
        assert template in available_templates()


def test_scaffold_creates_agent_project():
    from largestack._cli.scaffold import scaffold

    tmpdir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    try:
        os.chdir(tmpdir)
        result = scaffold("test-agent", "agent")
        assert result["type"] == "agent"
        assert len(result["files_created"]) >= 20
        assert os.path.exists("test-agent/main.py")
        assert os.path.exists("test-agent/pyproject.toml")
        assert os.path.exists("test-agent/AGENTS.md")
        for path in [
            "largestack.yaml",
            "providers.yaml",
            "agents.yaml",
            "agent_groups.yaml",
            "tools.yaml",
            "workflow.yaml",
            "workflow_graph.mmd",
            "rag.yaml",
            "guardrails.yaml",
            "app/main.py",
            "app/agents/planner.py",
            "app/agents/executor.py",
            "app/agents/reviewer.py",
            "app/tools/business_tools.py",
            "app/workflows/main_flow.py",
            "app/rag/knowledge/README.md",
            "tests/test_agents.py",
            "tests/test_tools.py",
            "tests/test_workflow.py",
            "deploy/Dockerfile",
            "deploy/docker-compose.yml",
            "scripts/smoke_test.py",
        ]:
            assert os.path.exists(os.path.join("test-agent", path)), path
        assert "schema_version: '1.1'" in Path("test-agent/largestack.yaml").read_text()
        assert "mode: protect" in Path("test-agent/guardrails.yaml").read_text()
        assert "approval_policy" in Path("test-agent/tools.yaml").read_text()
        assert "groups:" in Path("test-agent/agent_groups.yaml").read_text()
        assert "flowchart TD" in Path("test-agent/workflow_graph.mmd").read_text()
    finally:
        os.chdir(old_cwd)
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_scaffold_creates_support_ticket_template():
    from largestack._cli.scaffold import scaffold

    tmpdir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    try:
        os.chdir(tmpdir)
        result = scaffold("support-ticket-ai", "support-ticket")
        assert result["type"] == "support-ticket"
        for path in [
            "agents.yaml",
            "agent_groups.yaml",
            "tools.yaml",
            "workflow.yaml",
            "workflow_graph.mmd",
            "rag.yaml",
            "guardrails.yaml",
            "app/tools/ticket_tools.py",
            "app/workflows/support_flow.py",
            "app/rag/knowledge/refund_policy.md",
            "tests/test_support_ticket.py",
        ]:
            assert os.path.exists(os.path.join("support-ticket-ai", path)), path
        assert "triage" in Path("support-ticket-ai/agents.yaml").read_text()
        assert "send_email: require_approval" in Path("support-ticket-ai/tools.yaml").read_text()
        assert "enabled: true" in Path("support-ticket-ai/rag.yaml").read_text()
        assert "largestack>=1.0.0" in Path("support-ticket-ai/pyproject.toml").read_text()
    finally:
        os.chdir(old_cwd)
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.parametrize(
    "template",
    [
        "rag",
        "code-review",
        "ml-automation",
        "website-builder",
        "video-pipeline",
        "social-media",
        "bfsi",
        "document-extraction",
    ],
)
def test_scaffold_creates_product_templates(template):
    from largestack._cli.scaffold import scaffold

    tmpdir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    try:
        os.chdir(tmpdir)
        result = scaffold(f"{template}-demo", template)
        project = Path(f"{template}-demo")
        assert result["type"] == template
        for path in [
            "providers.yaml",
            "agents.yaml",
            "agent_groups.yaml",
            "workflow.yaml",
            "workflow_graph.mmd",
            "rag.yaml",
            "guardrails.yaml",
            "app/main.py",
        ]:
            assert (project / path).exists(), path
        assert "flowchart TD" in (project / "workflow_graph.mmd").read_text()
        assert "graph:" in (project / "rag.yaml").read_text()
        assert "largestack graph" in (project / "README.md").read_text()
        if template == "bfsi":
            assert "mode: strict" in (project / "guardrails.yaml").read_text()
            assert "context: bfsi" in (project / "guardrails.yaml").read_text()
    finally:
        os.chdir(old_cwd)
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_scaffold_invalid_template():
    from largestack._cli.scaffold import scaffold
    import pytest

    with pytest.raises(ValueError):
        scaffold("test", "invalid-template")
