"""Largestack AI CLI."""

from __future__ import annotations
import os
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="largestack",
    help="Largestack AI — Universal Multi-Agent AI Framework",
    no_args_is_help=True,
)
console = Console()


def _command_exists(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def _load_yaml(path):
    import yaml

    target = Path(path)
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text()) or {}


_YAML_HEADERS = {
    "agents.yaml": "# Beginner file: define the agents in your app.\n# Edit role first. workflow.yaml references these ids.\n",
    "tools.yaml": "# Beginner file: list tools agents may call.\n# Unsafe write/delete/send/payment tools should require approval.\n",
    "integrations.yaml": "# Beginner file: external services and their approval metadata.\n",
    "mcp.yaml": "# Beginner file: optional MCP tool servers.\n# Keep approval: require_approval until you trust discovered tools.\n",
}


def _write_yaml(path, data) -> None:
    import yaml

    target = Path(path)
    header = _YAML_HEADERS.get(target.name, "")
    body = yaml.safe_dump(data, sort_keys=False)
    target.write_text(header + body)


@app.command()
def version():
    """Show Largestack AI version."""
    from largestack import __version__

    console.print(f"[bold purple]Largestack AI[/bold purple] v{__version__}")


@app.command()
def init(
    name: str = typer.Argument("my-agent", help="Project name"),
    template: str = typer.Option(
        "support-ticket",
        "--template",
        "-t",
        help="Template: support-ticket, rag, code-review, ml-automation, website-builder, video-pipeline, social-media, bfsi, document-extraction, agent, crew, workflow, mcp-server",
    ),
    style: str = typer.Option("hybrid", help="Config style: yaml, python, hybrid"),
    provider: str = typer.Option(
        "deepseek", help="Provider: deepseek, openai, anthropic, gemini, groq, ollama, multi"
    ),
    rag: str = typer.Option(
        "hybrid", help="RAG mode: none, local, vector, hybrid, graph, sql-vector"
    ),
    guardrails: str = typer.Option("protect", help="Guardrails: warn, protect, strict, custom"),
    wizard: bool = typer.Option(False, "--wizard", help="Ask beginner-friendly setup questions"),
):
    """Initialize a production-shaped Largestack AI project."""
    from largestack._cli.scaffold import scaffold

    if wizard:
        template = typer.prompt("Template", default=template)
        style = typer.prompt("Config style", default=style)
        provider = typer.prompt("Provider", default=provider)
        rag = typer.prompt("RAG mode", default=rag)
        guardrails = typer.prompt("Guardrails", default=guardrails)
    try:
        result = scaffold(
            name,
            template,
            style=style,
            provider=provider,
            rag=rag,
            guardrails=guardrails,
        )
    except FileExistsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(
        Panel(
            f"[green]Project '{result['project_path']}' created![/green]\n\n"
            f"  cd {result['project_path']}\n"
            f"  cp .env.example .env\n"
            f"  pip install -e .\\[dev]\n"
            f"  largestack doctor\n"
            f"  largestack explain\n"
            f"  largestack run app/main.py\n"
            f"  largestack test",
            title="Largestack AI",
            border_style="purple",
        )
    )


@app.command()
def doctor():
    """Diagnose Largestack AI setup and the current project scaffold."""
    import os, sys
    from pathlib import Path
    import yaml

    checks = [
        (
            "Python",
            f"{sys.version_info.major}.{sys.version_info.minor}",
            sys.version_info >= (3, 10),
        )
    ]
    try:
        from largestack import __version__

        checks.append(("LARGESTACK", __version__, True))
    except:
        checks.append(("LARGESTACK", "not installed", False))
    project_files = (
        "largestack.yaml",
        "providers.yaml",
        "agents.yaml",
        "agent_groups.yaml",
        "tools.yaml",
        "workflow.yaml",
        "workflow_graph.mmd",
        "rag.yaml",
        "guardrails.yaml",
        "mcp.yaml",
    )
    root = Path(".")
    if any(Path(path).exists() for path in project_files):
        for path in project_files:
            checks.append(
                (path, "present" if Path(path).exists() else "missing", Path(path).exists())
            )
        parsed = {}
        for path in project_files:
            if not path.endswith(".yaml") or not Path(path).exists():
                continue
            try:
                parsed[path] = yaml.safe_load(Path(path).read_text()) or {}
                checks.append((f"{path} parse", "valid YAML", True))
            except Exception as exc:
                parsed[path] = {}
                checks.append((f"{path} parse", f"invalid YAML: {exc}", False))
        agents = (parsed.get("agents.yaml") or {}).get("agents") or []
        tools = (parsed.get("tools.yaml") or {}).get("tools") or []
        workflow = (parsed.get("workflow.yaml") or {}).get("workflow") or {}
        workflow_agents = workflow.get("agents") or []
        checks.append(("Agents", f"{len(agents)} configured", bool(agents)))
        checks.append(("Tools", f"{len(tools)} configured", True))
        checks.append(("Workflow", f"{len(workflow_agents)} agents routed", bool(workflow_agents)))
        missing_workflow_agents = [
            agent for agent in workflow_agents if agent not in {a.get("id") for a in agents}
        ]
        checks.append(
            (
                "Workflow agent refs",
                "valid"
                if not missing_workflow_agents
                else f"missing: {', '.join(missing_workflow_agents)}",
                not missing_workflow_agents,
            )
        )
        rag_cfg = (parsed.get("rag.yaml") or {}).get("rag") or {}
        rag_sources = rag_cfg.get("sources") or []
        missing_sources = []
        for source in rag_sources:
            source_path = source.get("path")
            if source_path and not (root / source_path).exists():
                missing_sources.append(source_path)
        rag_enabled = bool(rag_cfg.get("enabled"))
        checks.append(("RAG", "enabled" if rag_enabled else "disabled", True))
        checks.append(
            (
                "RAG sources",
                "valid" if not missing_sources else f"missing: {', '.join(missing_sources)}",
                not missing_sources,
            )
        )
        guard_cfg = (parsed.get("guardrails.yaml") or {}).get("guardrails") or {}
        checks.append(
            ("Guardrail mode", guard_cfg.get("mode", "not set"), bool(guard_cfg.get("mode")))
        )
        strict = guard_cfg.get("mode") == "strict" or guard_cfg.get("context") == "bfsi"
        if strict:
            bfsi_cfg = (parsed.get("guardrails.yaml") or {}).get("bfsi") or {}
            provider_bfsi = (parsed.get("providers.yaml") or {}).get("bfsi") or {}
            approved = (
                provider_bfsi.get("approved_providers") or bfsi_cfg.get("approved_providers") or []
            )
            checks.append(
                (
                    "BFSI approved providers",
                    ", ".join(approved) if approved else "missing",
                    bool(approved),
                )
            )
            checks.append(
                (
                    "Maker-checker",
                    "enabled" if bfsi_cfg.get("maker_checker") else "missing",
                    bool(bfsi_cfg.get("maker_checker")),
                )
            )
            checks.append(
                (
                    "Audit",
                    "enabled" if bfsi_cfg.get("audit") else "missing",
                    bool(bfsi_cfg.get("audit")),
                )
            )
            production = os.environ.get("LARGESTACK_ENV", "").lower() in {"prod", "production"}
            dashboard_key_set = bool(os.environ.get("LARGESTACK_DASHBOARD_KEY"))
            dashboard_status = (
                "set" if dashboard_key_set else "not set (required before production)"
            )
            checks.append(("Dashboard auth", dashboard_status, dashboard_key_set or not production))
        checks.append(
            ("Tests", "present" if Path("tests").exists() else "missing", Path("tests").exists())
        )
    else:
        checks.append(("Project scaffold", "not detected in current directory", True))
    checks.append(
        (
            "OpenAI key",
            "set" if os.environ.get("LARGESTACK_OPENAI_API_KEY") else "not set (optional)",
            True,
        )
    )
    checks.append(
        (
            "DeepSeek key",
            "set" if os.environ.get("LARGESTACK_DEEPSEEK_API_KEY") else "not set (optional)",
            True,
        )
    )
    checks.append(
        (
            "Anthropic key",
            "set" if os.environ.get("LARGESTACK_ANTHROPIC_API_KEY") else "not set (optional)",
            True,
        )
    )
    checks.append(
        ("Docker", "available" if _command_exists("docker") else "not found (optional)", True)
    )
    try:
        import httpx

        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        checks.append(("Ollama", f"running ({len(r.json().get('models', []))} models)", True))
    except:
        checks.append(("Ollama", "not running (optional)", True))
    console.print("\n[bold]Largestack AI Doctor[/bold]\n")
    issues = 0
    for n, s, ok in checks:
        console.print(f"  {'[green]✓[/green]' if ok else '[red]✗[/red]'} {n}: {s}")
        if not ok:
            issues += 1
    console.print(f"\nIssues: [{'red' if issues else 'green'}]{issues}[/]")


@app.command()
def explain(
    section: str = typer.Argument(
        "project",
        help="What to explain: project, agents, workflow, rag, guardrails, or a project path",
    ),
    path: str = typer.Option(".", "--project", "-p", help="Project path"),
):
    """Explain a generated project or one beginner-facing section."""
    from pathlib import Path
    import yaml

    valid_sections = {
        "project",
        "agents",
        "workflow",
        "rag",
        "guardrails",
        "tools",
        "providers",
        "all",
    }
    if section not in valid_sections:
        path = section
        section = "project"
    show_all = section in {"project", "all"}
    root = Path(path)
    files = {
        "largestack.yaml": "runtime defaults: model, budget, tracing, guardrails",
        "providers.yaml": "multi-provider defaults, fallback, key env names, and BFSI provider allowlist",
        "agents.yaml": "beginner-editable agent roster and responsibilities",
        "agent_groups.yaml": "agent group mode and approval expectations",
        "tools.yaml": "tool catalog and approval expectations",
        "workflow.yaml": "agent routing/orchestration shape",
        "workflow_graph.mmd": "Mermaid graph for architecture review and documentation",
        "rag.yaml": "knowledge sources and retrieval settings",
        "guardrails.yaml": "mode, redaction, approval, and BFSI controls",
        "mcp.yaml": "optional MCP tool servers and approval metadata",
        "app/agents": "advanced Python agent definitions",
        "app/tools": "advanced Python tools",
        "app/workflows": "advanced orchestration code",
        "app/rag": "knowledge ingestion code and local documents",
        "tests": "offline tests for generated project behavior",
    }
    console.print(
        Panel(
            f"[bold]Project:[/bold] {root.resolve()}\n[bold]Section:[/bold] {section}",
            title="Largestack AI Explain",
            border_style="purple",
        )
    )
    if show_all:
        for rel, description in files.items():
            target = root / rel
            marker = "[green]✓[/green]" if target.exists() else "[yellow]○[/yellow]"
            console.print(f"  {marker} [bold]{rel}[/bold] — {description}")

    agents_path = root / "agents.yaml"
    if agents_path.exists() and section in {"project", "all", "agents"}:
        try:
            data = yaml.safe_load(agents_path.read_text()) or {}
            agents = data.get("agents", [])
            if agents:
                console.print(f"\n[bold]Agents[/bold] ({len(agents)})")
                for agent in agents:
                    console.print(
                        f"  - {agent.get('id', agent.get('name', 'agent'))}: {agent.get('role', agent.get('instructions', ''))}"
                    )
                console.print("  edit first: role, model, max_retries, cost_budget")
        except Exception as exc:
            console.print(f"[yellow]Could not parse agents.yaml: {exc}[/yellow]")

    tools_path = root / "tools.yaml"
    if tools_path.exists() and section in {"project", "all", "tools"}:
        try:
            data = yaml.safe_load(tools_path.read_text()) or {}
            tools = data.get("tools") or []
            approvals = data.get("approval_policy") or {}
            console.print(f"\n[bold]Tools[/bold] ({len(tools)})")
            for tool in tools:
                console.print(
                    f"  - {tool.get('id', tool.get('name', 'tool'))}: approval={tool.get('approval', False)}"
                )
            if approvals:
                console.print(
                    f"  approval policy: {', '.join(f'{k}={v}' for k, v in approvals.items())}"
                )
            console.print(
                "  rule: read tools can run; write/delete/send/payment tools need approval"
            )
        except Exception as exc:
            console.print(f"[yellow]Could not parse tools.yaml: {exc}[/yellow]")

    providers_path = root / "providers.yaml"
    if providers_path.exists() and section in {"project", "all", "providers"}:
        try:
            data = yaml.safe_load(providers_path.read_text()) or {}
            providers = data.get("providers", {})
            console.print("\n[bold]Provider Routing[/bold]")
            console.print(f"  default: {providers.get('default', 'not set')}")
            fallback = providers.get("fallback") or []
            if fallback:
                console.print(f"  fallback: {', '.join(fallback)}")
        except Exception as exc:
            console.print(f"[yellow]Could not parse providers.yaml: {exc}[/yellow]")

    guardrails_path = root / "guardrails.yaml"
    if guardrails_path.exists() and section in {"project", "all", "guardrails"}:
        try:
            data = yaml.safe_load(guardrails_path.read_text()) or {}
            guardrails = data.get("guardrails", {})
            console.print("\n[bold]Guardrails[/bold]")
            console.print(f"  mode: {guardrails.get('mode', 'not set')}")
            console.print(f"  context: {guardrails.get('context', 'not set')}")
            console.print(f"  risky tools: {guardrails.get('tool_write_action', 'not set')}")
            console.print("  modes: warn/protect/strict/custom")
            console.print(
                "  use warn for benchmarks, protect for products, strict for BFSI/customer-sensitive work"
            )
        except Exception as exc:
            console.print(f"[yellow]Could not parse guardrails.yaml: {exc}[/yellow]")

    rag_path = root / "rag.yaml"
    if rag_path.exists() and section in {"project", "all", "rag"}:
        try:
            data = yaml.safe_load(rag_path.read_text()) or {}
            rag = data.get("rag", {})
            retrieval = rag.get("retrieval", {})
            graph = rag.get("graph", {})
            console.print("\n[bold]RAG[/bold]")
            console.print(f"  enabled: {bool(rag.get('enabled'))}")
            console.print(f"  retrieval: {retrieval.get('mode', 'not set')}")
            console.print(f"  graph: {'enabled' if graph.get('enabled') else 'disabled'}")
            console.print("  edit first: sources[].path and retrieval.mode")
        except Exception as exc:
            console.print(f"[yellow]Could not parse rag.yaml: {exc}[/yellow]")

    workflow_path = root / "workflow.yaml"
    if workflow_path.exists() and section in {"project", "all", "workflow"}:
        try:
            data = yaml.safe_load(workflow_path.read_text()) or {}
            workflow = data.get("workflow", data)
            agents = workflow.get("agents") or []
            console.print("\n[bold]Workflow[/bold]")
            console.print(f"  mode: {workflow.get('mode', 'not set')}")
            console.print(f"  route: {' -> '.join(agents) if agents else 'not set'}")
            console.print("  supported modes: sequential, parallel, router, supervisor, debate")
            console.print("  refresh visual docs: largestack graph --write")
        except Exception as exc:
            console.print(f"[yellow]Could not parse workflow.yaml: {exc}[/yellow]")

    if show_all:
        console.print("\n[bold]What To Edit First[/bold]")
        console.print("  1. agents.yaml — rename roles and responsibilities")
        console.print("  2. tools.yaml — add real read tools, keep risky actions approved")
        console.print("  3. app/rag/knowledge — add your policy/docs, then largestack rag build")
        console.print(
            "  4. workflow.yaml — choose sequential, parallel, router, supervisor, or debate"
        )
        console.print("  5. guardrails.yaml — warn/protect/strict based on environment")


templates_app = typer.Typer(help="List and explain project templates", invoke_without_command=True)
app.add_typer(templates_app, name="templates")


def list_templates():
    """Backward-compatible helper used by older tests/importers."""
    from largestack._cli.scaffold import available_templates

    console.print("[bold]Available templates[/bold]")
    for name in available_templates():
        console.print(f"  - {name}")


@templates_app.callback(invoke_without_command=True)
def templates_callback(ctx: typer.Context):
    """List built-in project templates."""
    if ctx.invoked_subcommand is not None:
        return
    list_templates()
    console.print("\nExplain one: [bold]largestack templates explain support-ticket[/bold]")


@templates_app.command("explain")
def templates_explain(template: str = typer.Argument(..., help="Template name")):
    """Explain what a template creates and when to use it."""
    from largestack._cli.scaffold import (
        PRODUCT_TEMPLATE_ALIASES,
        PRODUCT_TEMPLATES,
        available_templates,
    )

    key = PRODUCT_TEMPLATE_ALIASES.get(template.replace("_", "-"), template.replace("_", "-"))
    if key == "support-ticket":
        info = {
            "title": "Support Ticket AI",
            "description": "Flagship beginner demo for customer support, RAG, approvals, and guardrails.",
            "workflow": "supervisor",
            "context": "customer_support",
            "agents": [("triage", "Classify"), ("resolver", "Draft"), ("qa", "Review")],
        }
    else:
        info = PRODUCT_TEMPLATES.get(key)
    if not info:
        raise typer.BadParameter(
            f"Unknown template: {template}. Choose from: {available_templates()}"
        )
    console.print(
        Panel(
            f"[bold]{info['title']}[/bold]\n{info['description']}",
            title="Largestack AI Template",
            border_style="purple",
        )
    )
    console.print(f"  workflow: {info.get('workflow', 'agent')}")
    console.print(f"  context: {info.get('context', 'general')}")
    console.print("  agents:")
    for agent_id, role in info.get("agents", []):
        console.print(f"    - {agent_id}: {role}")
    console.print("  first run: largestack init my-app --template " + key)


@app.command()
def providers(path: str = typer.Argument(".", help="Project path")):
    """Show provider routing without printing any API keys."""
    from pathlib import Path
    import yaml

    root = Path(path)
    cfg = root / "providers.yaml"
    if not cfg.exists():
        raise typer.BadParameter(f"providers.yaml not found in {root}")
    data = yaml.safe_load(cfg.read_text()) or {}
    provider_cfg = data.get("providers", {})
    console.print(
        Panel(
            f"[bold]Project:[/bold] {root.resolve()}",
            title="Largestack AI Providers",
            border_style="purple",
        )
    )
    console.print(f"  default: {provider_cfg.get('default', 'not set')}")
    console.print(f"  fallback: {', '.join(provider_cfg.get('fallback') or []) or 'none'}")
    keys = provider_cfg.get("keys") or {}
    for provider_name, env_name in keys.items():
        status = "set" if os.environ.get(str(env_name)) else "not set"
        console.print(f"  {provider_name}: env {env_name} ({status})")
    bfsi = data.get("bfsi", {})
    approved = bfsi.get("approved_providers") or []
    console.print(
        f"  bfsi approved providers: {', '.join(approved) if approved else 'none configured'}"
    )


@app.command()
def graph(
    path: str = typer.Argument(".", help="Project path"),
    write: bool = typer.Option(
        False, "--write", help="Write workflow_graph.mmd from workflow.yaml"
    ),
    mermaid: bool = typer.Option(False, "--mermaid", help="Print Mermaid graph text"),
    html: bool = typer.Option(False, "--html", help="Write a simple workflow_graph.html report"),
):
    """Explain or regenerate a workflow graph."""
    from pathlib import Path
    import yaml

    root = Path(path)
    graph_path = root / "workflow_graph.mmd"
    if graph_path.exists() and mermaid and not write and not html:
        console.print(graph_path.read_text().rstrip())
        return

    workflow_path = root / "workflow.yaml"
    if not workflow_path.exists():
        raise typer.BadParameter(f"workflow.yaml not found in {root}")
    data = yaml.safe_load(workflow_path.read_text()) or {}
    workflow = data.get("workflow", data)
    agents = workflow.get("agents") or []
    if not agents:
        raise typer.BadParameter("workflow.yaml does not define workflow.agents")
    rag = {}
    if (root / "rag.yaml").exists():
        rag = (yaml.safe_load((root / "rag.yaml").read_text()) or {}).get("rag") or {}
    tools = {}
    if (root / "tools.yaml").exists():
        tools = yaml.safe_load((root / "tools.yaml").read_text()) or {}
    approval_policy = tools.get("approval_policy") or {}
    tool_list = tools.get("tools") or []
    chain = ["start([start])", *agents, "finish([finish])"]
    if rag.get("enabled"):
        insert_at = min(2, len(chain) - 1)
        chain.insert(insert_at, "rag_search[[RAG Search]]")
    if tool_list:
        insert_at = min(3 if rag.get("enabled") else 2, len(chain) - 1)
        chain.insert(insert_at, "tool_checks[[Tool Checks]]")
    if approval_policy:
        chain.insert(len(chain) - 1, "approval{Approval}")
    lines = ["flowchart TD"]
    for left, right in zip(chain, chain[1:]):
        lines.append(f"  {left} --> {right}")
    lines.append("  classDef agent fill:#eef6ff,stroke:#2f5597,color:#111827")
    for agent in agents:
        lines.append(f"  class {agent} agent")
    text = "\n".join(lines) + "\n"
    if html:
        html_path = root / "workflow_graph.html"
        html_path.write_text(
            """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Largestack AI Workflow</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111827; }}
    pre {{ background: #f8fafc; border: 1px solid #d1d5db; padding: 1rem; overflow: auto; }}
    .node {{ margin: .4rem 0; }}
  </style>
</head>
<body>
  <h1>Largestack AI Workflow</h1>
  <p>Mode: <strong>{mode}</strong></p>
  <h2>Route</h2>
  {nodes}
  <h2>Mermaid</h2>
  <pre>{graph}</pre>
</body>
</html>
""".format(
                mode=workflow.get("mode", "not set"),
                nodes="\n  ".join(
                    f"<div class='node'>{idx}. {agent}</div>" for idx, agent in enumerate(agents, 1)
                ),
                graph=text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            ),
            encoding="utf-8",
        )
        console.print(f"[green]Wrote {html_path}[/green]")
        return
    if write:
        graph_path.write_text(text)
        console.print(f"[green]Wrote {graph_path}[/green]")
    elif mermaid:
        console.print(text.rstrip())
    else:
        console.print(
            Panel(str(root.resolve()), title="Largestack AI Workflow Graph", border_style="purple")
        )
        console.print(f"  mode: {workflow.get('mode', 'not set')}")
        console.print(f"  route: {' -> '.join(agents)}")
        console.print(f"  rag: {'enabled' if rag.get('enabled') else 'disabled'}")
        console.print(f"  tools: {len(tool_list)} configured")
        console.print(f"  approvals: {len(approval_policy)} policy entries")
        console.print("\nCommands:")
        console.print("  largestack graph --mermaid")
        console.print("  largestack graph --write")
        console.print("  largestack graph --html")


knowledge_app = typer.Typer(help="Manage local project knowledge sources")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("list")
def knowledge_list(path: str = typer.Argument(".", help="Project path")):
    """List files under app/rag/knowledge."""
    from pathlib import Path

    knowledge_dir = Path(path) / "app" / "rag" / "knowledge"
    if not knowledge_dir.exists():
        raise typer.BadParameter(f"Knowledge directory not found: {knowledge_dir}")
    files = sorted(p for p in knowledge_dir.rglob("*") if p.is_file())
    console.print(
        Panel(str(knowledge_dir.resolve()), title="Largestack AI Knowledge", border_style="purple")
    )
    if not files:
        console.print("  no files")
        return
    for file_path in files:
        console.print(f"  - {file_path.relative_to(knowledge_dir)}")


@knowledge_app.command("add")
def knowledge_add(
    source: str = typer.Argument(..., help="File or directory to copy into app/rag/knowledge"),
    path: str = typer.Option(".", "--project", "-p", help="Project path"),
):
    """Copy a file or directory into app/rag/knowledge."""
    from pathlib import Path
    import shutil

    src = Path(source)
    if not src.exists():
        raise typer.BadParameter(f"Source not found: {src}")
    knowledge_dir = Path(path) / "app" / "rag" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        dest = knowledge_dir / src.name
        if dest.exists():
            raise typer.BadParameter(f"Destination already exists: {dest}")
        shutil.copytree(src, dest)
    else:
        dest = knowledge_dir / src.name
        if dest.exists():
            raise typer.BadParameter(f"Destination already exists: {dest}")
        shutil.copy2(src, dest)
    console.print(f"[green]Added {dest}[/green]")


rag_app = typer.Typer(help="Build, test, and explain local RAG config")
app.add_typer(rag_app, name="rag")


@rag_app.command("build")
def rag_build(path: str = typer.Argument(".", help="Project path")):
    """Create a local RAG manifest from configured knowledge files."""
    import json
    from pathlib import Path
    import yaml

    root = Path(path)
    rag_cfg = _load_yaml(root / "rag.yaml").get("rag", {})
    sources = rag_cfg.get("sources") or []
    files = []
    for source in sources:
        source_path = root / str(source.get("path", ""))
        if source_path.exists():
            files.extend(sorted(p for p in source_path.rglob("*") if p.is_file()))
    state_dir = root / ".largestack"
    state_dir.mkdir(exist_ok=True)
    manifest = {
        "source_count": len(sources),
        "file_count": len(files),
        "retrieval_mode": (rag_cfg.get("retrieval") or {}).get("mode", "not set"),
        "graph_enabled": bool((rag_cfg.get("graph") or {}).get("enabled")),
        "files": [str(p.relative_to(root)) for p in files],
    }
    out = state_dir / "rag_manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    console.print(f"[green]Built RAG manifest:[/green] {out}")
    console.print(f"  files: {manifest['file_count']}")


@rag_app.command("test")
def rag_test(path: str = typer.Argument(".", help="Project path")):
    """Run offline checks against local RAG sources."""
    from pathlib import Path

    root = Path(path)
    rag_cfg = _load_yaml(root / "rag.yaml").get("rag", {})
    if not rag_cfg.get("enabled"):
        console.print("[yellow]RAG is disabled.[/yellow]")
        raise typer.Exit(0)
    sources = rag_cfg.get("sources") or []
    missing = []
    files = []
    for source in sources:
        source_path = root / str(source.get("path", ""))
        if not source_path.exists():
            missing.append(str(source_path))
        else:
            files.extend(p for p in source_path.rglob("*") if p.is_file())
    if missing:
        console.print(f"[red]Missing RAG sources:[/red] {', '.join(missing)}")
        raise typer.Exit(1)
    if not files:
        console.print("[red]No knowledge files found.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]RAG offline test passed[/green]: {len(files)} knowledge files")


@rag_app.command("explain")
def rag_explain(path: str = typer.Argument(".", help="Project path")):
    """Explain local RAG mode, sources, graph setting, and optional dependencies."""
    import importlib.util
    from pathlib import Path

    root = Path(path)
    rag_cfg = _load_yaml(root / "rag.yaml").get("rag", {})
    sources = rag_cfg.get("sources") or []
    retrieval = rag_cfg.get("retrieval") or {}
    graph = rag_cfg.get("graph") or {}
    files = []
    for source in sources:
        source_path = root / str(source.get("path", ""))
        if source_path.exists():
            files.extend(p for p in source_path.rglob("*") if p.is_file())
    console.print(Panel(str(root.resolve()), title="Largestack AI RAG", border_style="purple"))
    console.print(f"  enabled: {bool(rag_cfg.get('enabled'))}")
    console.print(f"  sources: {len(sources)}")
    console.print(f"  files: {len(files)}")
    console.print(f"  retrieval: {retrieval.get('mode', 'not set')}")
    console.print(f"  graph: {'enabled' if graph.get('enabled') else 'disabled'}")
    console.print(f"  citations: {rag_cfg.get('citations', 'not configured')}")
    optional = {
        "faiss": "faiss",
        "duckdb": "duckdb",
        "qdrant-client": "qdrant_client",
    }
    missing = [
        name for name, module in optional.items() if importlib.util.find_spec(module) is None
    ]
    console.print(f"  optional deps missing: {', '.join(missing) if missing else 'none'}")


@rag_app.command("inspect")
def rag_inspect(path: str = typer.Argument(".", help="Project path")):
    """Inspect the local RAG manifest and knowledge files."""
    import json
    from pathlib import Path

    root = Path(path)
    manifest_path = root / ".largestack" / "rag_manifest.json"
    if not manifest_path.exists():
        console.print("[yellow]No RAG manifest found. Run: largestack rag build[/yellow]")
        raise typer.Exit(1)
    manifest = json.loads(manifest_path.read_text())
    console.print(
        Panel(str(manifest_path), title="Largestack AI RAG Inspect", border_style="purple")
    )
    console.print(f"  sources: {manifest.get('source_count', 0)}")
    console.print(f"  files: {manifest.get('file_count', 0)}")
    console.print(f"  retrieval: {manifest.get('retrieval_mode', 'not set')}")
    console.print(f"  graph: {'enabled' if manifest.get('graph_enabled') else 'disabled'}")
    for file_path in manifest.get("files", [])[:20]:
        console.print(f"  - {file_path}")


add_app = typer.Typer(help="Add knowledge, integrations, agents, or tools to a project")
app.add_typer(add_app, name="add")


@add_app.command("knowledge")
def add_knowledge(
    source: str = typer.Argument(..., help="File or directory to add"),
    path: str = typer.Option(".", "--project", "-p"),
):
    """Alias for `largestack knowledge add`."""
    knowledge_add(source, path)


@add_app.command("integration")
def add_integration(
    name: str = typer.Argument(..., help="Integration name"),
    path: str = typer.Option(".", "--project", "-p"),
):
    """Add integration metadata and approval policy to a project."""
    import yaml
    from pathlib import Path
    from largestack._integrations.registry import get_integration

    spec = get_integration(name)
    root = Path(path)
    cfg_path = root / "integrations.yaml"
    data = _load_yaml(cfg_path)
    integrations = data.setdefault("integrations", [])
    if not any(item.get("name") == spec.name for item in integrations):
        integrations.append(spec.as_project_entry())
    _write_yaml(cfg_path, data)

    tools_path = root / "tools.yaml"
    tools_data = _load_yaml(tools_path)
    policy = tools_data.setdefault("approval_policy", {})
    for action in spec.approval_actions:
        policy[action] = spec.approval
    _write_yaml(tools_path, tools_data)
    console.print(f"[green]Added integration:[/green] {spec.name}")
    console.print(f"  env vars: {', '.join(spec.env_vars)}")
    console.print(f"  approval: {spec.approval}")


@add_app.command("agent")
def add_agent(
    agent_id: str = typer.Argument(..., help="Agent id"),
    path: str = typer.Option(".", "--project", "-p"),
    role: str = typer.Option("Describe this agent role.", help="Agent role"),
):
    """Append a beginner-editable agent entry to agents.yaml."""
    import yaml
    from pathlib import Path

    cfg_path = Path(path) / "agents.yaml"
    data = _load_yaml(cfg_path)
    agents = data.setdefault("agents", [])
    if any(agent.get("id") == agent_id for agent in agents):
        raise typer.BadParameter(f"Agent already exists: {agent_id}")
    agents.append(
        {
            "id": agent_id,
            "role": role,
            "model": "deepseek/deepseek-chat",
            "max_retries": 2,
            "cost_budget": 1.0,
        }
    )
    _write_yaml(cfg_path, data)
    console.print(f"[green]Added agent:[/green] {agent_id}")


@add_app.command("tool")
def add_tool(
    tool_id: str = typer.Argument(..., help="Tool id"),
    path: str = typer.Option(".", "--project", "-p"),
    approval: str = typer.Option("false", help="false or require_approval"),
):
    """Append a beginner-editable tool entry to tools.yaml."""
    import yaml
    from pathlib import Path

    cfg_path = Path(path) / "tools.yaml"
    data = _load_yaml(cfg_path)
    tools = data.setdefault("tools", [])
    if any(tool.get("id") == tool_id for tool in tools):
        raise typer.BadParameter(f"Tool already exists: {tool_id}")
    approval_value = False if approval.lower() == "false" else approval
    tools.append(
        {
            "id": tool_id,
            "module": "app.tools.business_tools",
            "function": tool_id,
            "access": "read",
            "approval": approval_value,
        }
    )
    _write_yaml(cfg_path, data)
    console.print(f"[green]Added tool:[/green] {tool_id}")


mcp_app = typer.Typer(help="Manage MCP tool servers")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("list")
def mcp_list(path: str = typer.Argument(".", help="Project path")):
    """List configured MCP servers without connecting to them."""
    root = Path(path)
    cfg = _load_yaml(root / "mcp.yaml")
    servers = cfg.get("mcp", {}).get("servers") or cfg.get("servers") or []
    console.print(Panel(str(root.resolve()), title="Largestack AI MCP", border_style="purple"))
    if not servers:
        console.print("  no MCP servers configured")
        console.print("  add one: largestack mcp add docs --url http://localhost:8080/mcp")
        return
    for server in servers:
        target = server.get("url") or server.get("command") or "not configured"
        approval = server.get("approval", "require_approval")
        console.print(f"  - {server.get('name', 'mcp')}: {target} approval={approval}")


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Server name"),
    url: str | None = typer.Option(None, "--url", help="HTTP MCP endpoint"),
    command: str | None = typer.Option(
        None, "--command", help="stdio command for local MCP server"
    ),
    path: str = typer.Option(".", "--project", "-p", help="Project path"),
    approval: str = typer.Option("require_approval", help="Approval for MCP tool calls"),
):
    """Add an MCP server entry to mcp.yaml."""
    import yaml

    if not (url or command):
        raise typer.BadParameter("Provide --url or --command")
    root = Path(path)
    cfg_path = root / "mcp.yaml"
    data = _load_yaml(cfg_path)
    mcp = data.setdefault("mcp", {})
    servers = mcp.setdefault("servers", [])
    if any(server.get("name") == name for server in servers):
        raise typer.BadParameter(f"MCP server already exists: {name}")
    servers.append(
        {
            "name": name,
            "url": url,
            "command": command,
            "approval": approval,
            "risk_type": "unsafe_tool",
            "notes": "Review discovered tools for prompt injection and require approval for writes.",
        }
    )
    _write_yaml(cfg_path, data)
    console.print(f"[green]Added MCP server:[/green] {name}")


@mcp_app.command("test")
def mcp_test(
    path: str = typer.Argument(".", help="Project path"),
    connect: bool = typer.Option(False, "--connect", help="Connect to configured MCP servers"),
):
    """Validate MCP config; optionally connect and list tools."""
    import asyncio

    root = Path(path)
    cfg = _load_yaml(root / "mcp.yaml")
    servers = cfg.get("mcp", {}).get("servers") or cfg.get("servers") or []
    if not servers:
        console.print("[yellow]No MCP servers configured.[/yellow]")
        raise typer.Exit(1)
    issues = []
    for server in servers:
        if not (server.get("url") or server.get("command")):
            issues.append(f"{server.get('name', 'mcp')}: missing url or command")
        if server.get("approval") not in {"warn", "require_approval", "block"}:
            issues.append(
                f"{server.get('name', 'mcp')}: approval should be warn/require_approval/block"
            )
    if issues:
        for issue in issues:
            console.print(f"[red]✗[/red] {issue}")
        raise typer.Exit(1)
    if not connect:
        console.print(f"[green]MCP config valid[/green]: {len(servers)} server(s)")
        console.print("  use --connect to perform live discovery")
        return

    async def _connect_all():
        from largestack._core.mcp_client import MCPClient

        for server in servers:
            client = MCPClient(url=server.get("url"), command=server.get("command"))
            try:
                await client.connect()
                tools = await client.list_tools()
                suspicious = client.scan_for_poisoning()
                console.print(
                    f"[green]Connected[/green] {server.get('name')}: {len(tools)} tool(s)"
                )
                if suspicious:
                    console.print(
                        f"[yellow]Suspicious tool descriptions:[/yellow] {len(suspicious)}"
                    )
            finally:
                await client.disconnect()

    asyncio.run(_connect_all())


@app.command()
def run(
    file: str = typer.Argument("agent.py"),
    task: str = typer.Option(
        "Hello from LARGESTACK", help="Task/prompt for YAML agents or workflows"
    ),
):
    """Run a Python agent file or YAML agent/workflow config."""
    from pathlib import Path
    import asyncio
    import runpy
    import sys

    path = Path(file)
    console.print(f"[dim]Running {file}...[/dim]")
    if path.suffix.lower() in {".yaml", ".yml"}:
        from largestack._core.yaml_agent import load_agent, load_workflow
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        # Legacy workflow YAML: {name, mode, nodes:[{id, agent, deps}]}
        if "nodes" in data:
            wf = load_workflow(path)
            result = asyncio.run(wf.run({"input": task, "task": task}))
            console.print(result.final_output if hasattr(result, "final_output") else result)
            return

        # Single agent YAML: {name, model, instructions, tools, ...}
        if "agents" not in data:
            agent = load_agent(path)
            result = (
                agent.run_sync(task) if hasattr(agent, "run_sync") else asyncio.run(agent.run(task))
            )
            console.print(getattr(result, "content", result))
            return

        raise typer.BadParameter(
            "Graph-style multi-agent YAML is validated by largestack._core.yaml_schema "
            "but not executed by `largestack run` yet. Use Python Workflow/Team or "
            "legacy `nodes:` workflow YAML for execution."
        )

    project_root = str(Path.cwd())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    runpy.run_path(str(path), run_name="__main__")


@app.command()
def dashboard(
    host: str = typer.Option(
        None, help="Host to bind. Default: 0.0.0.0 in container, 127.0.0.1 locally"
    ),
    port: int = typer.Option(8787, help="Port"),
):
    """Start Largestack AI dashboard.

    v0.3.6: Auto-detects container environment via LARGESTACK_IN_CONTAINER=1 or
    /.dockerenv presence and binds to 0.0.0.0 (so the port is reachable from
    outside the container). Locally, binds to 127.0.0.1 unless --host overrides.
    Set LARGESTACK_DASHBOARD_HOST env to override across both modes.
    """
    if host is None:
        env_host = os.environ.get("LARGESTACK_DASHBOARD_HOST")
        if env_host:
            host = env_host
        elif os.environ.get("LARGESTACK_IN_CONTAINER") == "1" or os.path.exists("/.dockerenv"):
            host = "0.0.0.0"  # nosec B104
        else:
            host = "127.0.0.1"
    console.print(f"[bold purple]Largestack AI Dashboard[/bold purple] → http://{host}:{port}")
    try:
        import uvicorn
        from largestack._dashboard.app import create_app

        uvicorn.run(create_app(), host=host, port=port, log_level="warning")
    except ImportError:
        console.print("[red]Install: pip install largestack[all][/red]")


migrate_app = typer.Typer(help="Check and apply compatibility migrations")
app.add_typer(migrate_app, name="migrate")


@migrate_app.command("check")
def migrate_check(path: str = typer.Argument(".", help="Project path to inspect")):
    """Check project migration status."""
    from largestack.migrations import check_project

    result = check_project(path)
    console.print(result)
    if not result.get("ok", False):
        raise typer.Exit(1)


@migrate_app.command("apply")
def migrate_apply(path: str = typer.Argument(".", help="Project path to migrate")):
    """Apply safe, idempotent migrations in a project."""
    from largestack.migrations import apply_project_migrations

    console.print(apply_project_migrations(path))


@migrate_app.command("config")
def migrate_config(
    path: str = typer.Argument("largestack.yaml", help="Config file path"),
    write: bool = typer.Option(False, "--write"),
):
    """Check or rewrite a LARGESTACK config file."""
    from largestack.migrations import migrate_config as _migrate

    console.print(_migrate(path, write=write))


@migrate_app.command("memory")
def migrate_memory(
    path: str = typer.Argument("memory.json", help="Memory JSON file path"),
    write: bool = typer.Option(False, "--write"),
):
    """Check or rewrite a memory JSON file."""
    from largestack.migrations import migrate_memory as _migrate

    console.print(_migrate(path, write=write))


@migrate_app.command("traces")
def migrate_traces(
    path: str = typer.Argument("traces.db", help="Trace SQLite DB path"),
    write: bool = typer.Option(False, "--write"),
):
    """Check or migrate a trace SQLite database."""
    from largestack.migrations import migrate_trace_db

    console.print(migrate_trace_db(path, write=write))


@migrate_app.command("project")
def migrate_project(path: str = typer.Argument(".", help="Project path to migrate")):
    """Alias for migrate apply."""
    from largestack.migrations import apply_project_migrations

    console.print(apply_project_migrations(path))


from largestack._cli.commands import register_commands

register_commands(app)


@app.command()
def new(
    name: str = typer.Argument(..., help="Project name"),
    type: str = typer.Option("agent", help="Template: agent, crew, workflow, mcp-server"),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Beginner template shortcut, e.g. support-ticket"
    ),
):
    """Create new Largestack AI project from template."""
    from largestack._cli.scaffold import scaffold

    chosen_template = template or type
    try:
        result = scaffold(name, chosen_template)
        console.print(
            Panel(
                f"[green]✓ Created {result['type']} project: {result['project_name']}[/green]\n"
                f"\nFiles: {len(result['files_created'])}\n\n"
                f"Next steps:\n" + "\n".join(f"  {s}" for s in result["next_steps"]),
                title=f"Largestack AI: {name}",
                border_style="purple",
            )
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command()
def dev(
    port: int = typer.Option(4111, help="Port for dev server"),
    host: str = typer.Option("127.0.0.1", help="Host"),
):
    """Start LARGESTACK dev server with hot-reload + playground at http://localhost:4111

    v0.3.10: hot-reload is real (uses `watchfiles`). If `watchfiles` is not
    installed, the banner reports it honestly instead of always claiming "enabled".
    """
    try:
        from largestack._cli.dev_server import watchfiles_available

        hr_status = (
            "enabled (watchfiles)"
            if watchfiles_available()
            else ("disabled — install largestack[dev-server] for hot-reload")
        )
    except Exception:
        hr_status = "unknown"
    console.print(
        Panel(
            f"[purple]Starting LARGESTACK dev server[/purple]\n"
            f"  URL: http://{host}:{port}\n"
            f"  Playground: http://{host}:{port}/playground\n"
            f"  Health: http://{host}:{port}/api/health\n"
            f"  Hot-reload: {hr_status}\n"
            f"\n[dim]Press Ctrl+C to stop[/dim]",
            title="LARGESTACK Dev",
            border_style="purple",
        )
    )
    try:
        from largestack._cli.dev_server import run_dev_server

        run_dev_server(host=host, port=port)
    except ImportError:
        console.print(
            "[yellow]Install dev dependencies: pip install largestack[dev-server][/yellow]"
        )


@app.command()
def test(
    path: str = typer.Argument(".", help="Path to test"),
):
    """Run tests for LARGESTACK agents."""
    import subprocess
    import sys

    console.print(f"[purple]Running tests in {path}...[/purple]")
    raise typer.Exit(subprocess.run([sys.executable, "-m", "pytest", path, "-q"]).returncode)


if __name__ == "__main__":
    app()
