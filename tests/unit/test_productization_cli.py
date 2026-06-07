"""Productization tests for the beginner-facing Largestack AI CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from typer.testing import CliRunner

from largestack._cli.main import app


runner = CliRunner()


def test_cli_help_and_version_use_largestack_ai_brand():
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "Largestack AI" in help_result.output
    assert "Agentic AI" not in help_result.output

    version_result = runner.invoke(app, ["version"])
    assert version_result.exit_code == 0
    assert "Largestack AI" in version_result.output


def test_init_options_generate_beginner_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "init",
            "starter",
            "--template",
            "support-ticket",
            "--style",
            "yaml",
            "--provider",
            "multi",
            "--rag",
            "graph",
            "--guardrails",
            "strict",
        ],
    )
    assert result.exit_code == 0, result.output
    project = tmp_path / "starter"
    assert (project / ".env.example").exists()
    assert (project / "providers.yaml").exists()
    assert (project / "agent_groups.yaml").exists()
    assert (project / "workflow_graph.mmd").exists()
    assert "config_style: yaml" in (project / "largestack.yaml").read_text()
    assert "anthropic/claude" in (project / "providers.yaml").read_text()
    assert "mode: graph" in (project / "rag.yaml").read_text()
    assert "mode: strict" in (project / "guardrails.yaml").read_text()


def test_explain_doctor_graph_for_generated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "support-ticket-ai"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "support-ticket-ai")

    explain = runner.invoke(app, ["explain"])
    assert explain.exit_code == 0
    assert "Agents" in explain.output
    assert "Tools" in explain.output
    assert "Guardrails" in explain.output
    assert "What To Edit First" in explain.output

    explain_agents = runner.invoke(app, ["explain", "agents"])
    assert explain_agents.exit_code == 0
    assert "edit first" in explain_agents.output

    explain_workflow = runner.invoke(app, ["explain", "workflow"])
    assert explain_workflow.exit_code == 0
    assert "supported modes" in explain_workflow.output

    explain_rag = runner.invoke(app, ["explain", "rag"])
    assert explain_rag.exit_code == 0
    assert "retrieval" in explain_rag.output

    explain_guardrails = runner.invoke(app, ["explain", "guardrails"])
    assert explain_guardrails.exit_code == 0
    assert "modes" in explain_guardrails.output

    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exit_code == 0
    assert "Guardrail mode" in doctor.output
    assert "Workflow agent refs" in doctor.output
    assert "Tests" in doctor.output

    graph = runner.invoke(app, ["graph", "--write"])
    assert graph.exit_code == 0
    graph_text = Path("workflow_graph.mmd").read_text()
    assert "RAG Search" in graph_text
    assert "Tool Checks" in graph_text
    assert "Approval" in graph_text

    graph_text_output = runner.invoke(app, ["graph"])
    assert graph_text_output.exit_code == 0
    assert "route:" in graph_text_output.output

    graph_mermaid = runner.invoke(app, ["graph", "--mermaid"])
    assert graph_mermaid.exit_code == 0
    assert "flowchart TD" in graph_mermaid.output

    graph_html = runner.invoke(app, ["graph", "--html"])
    assert graph_html.exit_code == 0
    assert Path("workflow_graph.html").exists()


def test_rag_commands_build_test_and_explain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "rag-demo", "--template", "rag"]).exit_code == 0
    project = tmp_path / "rag-demo"
    monkeypatch.chdir(project)

    build = runner.invoke(app, ["rag", "build"])
    assert build.exit_code == 0, build.output
    manifest = json.loads((project / ".largestack" / "rag_manifest.json").read_text())
    assert manifest["file_count"] >= 1

    test = runner.invoke(app, ["rag", "test"])
    assert test.exit_code == 0, test.output

    explain = runner.invoke(app, ["rag", "explain"])
    assert explain.exit_code == 0
    assert "retrieval" in explain.output
    assert "optional deps missing" in explain.output

    inspect = runner.invoke(app, ["rag", "inspect"])
    assert inspect.exit_code == 0
    assert "files:" in inspect.output


def test_add_commands_update_project_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "app"]).exit_code == 0
    project = tmp_path / "app"
    source = tmp_path / "policy.md"
    source.write_text("refund policy")
    monkeypatch.chdir(project)

    assert runner.invoke(app, ["add", "knowledge", str(source)]).exit_code == 0
    assert (project / "app" / "rag" / "knowledge" / "policy.md").exists()

    assert (
        runner.invoke(app, ["add", "agent", "auditor", "--role", "Audit final answers"]).exit_code
        == 0
    )
    agents = yaml.safe_load((project / "agents.yaml").read_text())
    assert any(agent["id"] == "auditor" for agent in agents["agents"])

    assert (
        runner.invoke(
            app, ["add", "tool", "lookup_customer", "--approval", "require_approval"]
        ).exit_code
        == 0
    )
    tools = yaml.safe_load((project / "tools.yaml").read_text())
    assert any(tool["id"] == "lookup_customer" for tool in tools["tools"])


def test_integration_registry_and_add_integration(tmp_path, monkeypatch):
    from largestack._integrations.registry import available_integrations, get_integration

    assert {
        "jira",
        "slack",
        "postgres",
        "qdrant",
        "chroma",
        "pgvector",
        "opensearch",
        "github",
        "youtube",
        "stripe",
        "razorpay",
        "mcp",
    } <= set(available_integrations())
    stripe = get_integration("stripe")
    assert stripe.approval == "require_approval"
    assert "payment" in stripe.approval_actions

    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "billing"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "billing")
    result = runner.invoke(app, ["add", "integration", "stripe"])
    assert result.exit_code == 0, result.output
    integrations = yaml.safe_load(Path("integrations.yaml").read_text())
    assert integrations["integrations"][0]["name"] == "stripe"
    tools = yaml.safe_load(Path("tools.yaml").read_text())
    assert tools["approval_policy"]["payment"] == "require_approval"


def test_mcp_commands_validate_beginner_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "mcp-demo"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "mcp-demo")

    empty = runner.invoke(app, ["mcp", "list"])
    assert empty.exit_code == 0
    assert "no MCP servers" in empty.output

    added = runner.invoke(app, ["mcp", "add", "docs", "--url", "http://localhost:8080/mcp"])
    assert added.exit_code == 0, added.output
    cfg = yaml.safe_load(Path("mcp.yaml").read_text())
    assert cfg["mcp"]["servers"][0]["approval"] == "require_approval"

    listed = runner.invoke(app, ["mcp", "list"])
    assert listed.exit_code == 0
    assert "docs" in listed.output

    tested = runner.invoke(app, ["mcp", "test"])
    assert tested.exit_code == 0
    assert "MCP config valid" in tested.output


def test_templates_explain_and_new_template_shortcut(tmp_path, monkeypatch):
    list_result = runner.invoke(app, ["templates"])
    assert list_result.exit_code == 0
    assert "support-ticket" in list_result.output

    explain_result = runner.invoke(app, ["templates", "explain", "support-ticket"])
    assert explain_result.exit_code == 0
    assert "Support Ticket AI" in explain_result.output

    monkeypatch.chdir(tmp_path)
    new_result = runner.invoke(app, ["new", "shortcut-demo", "--template", "support-ticket"])
    assert new_result.exit_code == 0, new_result.output
    assert (tmp_path / "shortcut-demo" / "agents.yaml").exists()
    assert "# Beginner file" in (tmp_path / "shortcut-demo" / "agents.yaml").read_text()
