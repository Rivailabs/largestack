"""Largestack AI project scaffolding.

Usage:
    largestack new my-agent
    largestack new my-agent --type crew
    largestack new my-agent --type workflow
    largestack new my-agent --type mcp-server
"""
from __future__ import annotations
import os
from pathlib import Path

TEMPLATES = {
    "agent": {
        "main.py": '''"""{{ project_name }} — Largestack AI agent."""
import asyncio
from dataclasses import dataclass

from largestack.decorators import Agent, RunContext


@dataclass
class Deps:
    user_id: str = "default"


agent = Agent[Deps, str](
    "openai/gpt-4o-mini",
    deps_type=Deps,
    instructions="You are a helpful assistant.",
)


@agent.tool
async def greet(ctx: RunContext[Deps], name: str) -> str:
    """Greet a user by name."""
    return f"Hello {name}, your user_id is {ctx.deps.user_id}!"


async def main():
    result = await agent.run("Greet Sachith", deps=Deps(user_id="sachith"))
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
''',
        "pyproject.toml": '''[project]
name = "{{ project_name }}"
version = "0.1.0"
description = "{{ project_name }} agent built with Largestack AI"
requires-python = ">=3.11"
dependencies = [
    "largestack>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[tool.largestack]
type = "agent"

[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["tests*", "deploy*", "scripts*"]

''',
        ".env.example": '''# Copy to .env and fill in your keys
LARGESTACK_OPENAI_API_KEY=<openai-api-key>
LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
LARGESTACK_ANTHROPIC_API_KEY=<anthropic-api-key>
''',
        ".gitignore": '''__pycache__/
*.pyc
.env
.venv/
.pytest_cache/
.largestack/
''',
        "README.md": '''# {{ display_name }}

A Largestack AI project with beginner YAML controls and advanced Python edit points.

## Setup

```bash
cp .env.example .env
# Add your API keys to .env
pip install -e .[dev]
```

## Run

```bash
largestack doctor
largestack explain
largestack run app/main.py
largestack test
```

## Edit Points

- `agents.yaml`: tune agents and roles without touching Python.
- `tools.yaml`: register tools and approval expectations.
- `workflow.yaml`: choose sequential, parallel, router, supervisor, debate, or map-reduce flow.
- `rag.yaml`: point to local documents or vector/graph stores.
- `guardrails.yaml`: configure observe/warn/protect/strict/custom safety behavior.
- `app/agents/`: advanced typed agent definitions.
- `app/tools/`: Python tools with annotations and docstrings.
- `app/workflows/`: production workflow code.
- `app/rag/`: ingestion and retrieval customization.

## Develop with hot-reload

```bash
largestack dev
# Opens http://localhost:4111 with playground
```
''',
        "AGENTS.md": '''# {{ project_name }} — Agent Coding Rules

This project uses Largestack AI.

## Patterns

- Use `Agent[DepsT, OutputT]` generics for type safety
- Tools take `RunContext[Deps]` as first arg
- Use `@agent.tool` for tools that need context
- Use `@agent.tool_plain` for stateless tools
- Use `@agent.output_validator` with `ModelRetry()` for retry-on-fail
- Test with `TestModel` and `FunctionModel` from `largestack.testing`
''',
    },
    "crew": {
        "main.py": '''"""{{ project_name }} — Largestack AI multi-agent crew."""
import asyncio

from largestack import Agent, Team


researcher = Agent(
    name="researcher",
    instructions="Research topics and list 3 key facts.",
    llm="openai/gpt-4o-mini",
)

writer = Agent(
    name="writer",
    instructions="Take research and write a summary in 2 sentences.",
    llm="openai/gpt-4o-mini",
)


async def main():
    crew = Team(agents=[researcher, writer], strategy="sequential")
    result = await crew.run("Benefits of TypeScript")
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
''',
        "pyproject.toml": '''[project]
name = "{{ project_name }}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["largestack>=1.0.0"]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[tool.largestack]
type = "crew"

[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["tests*", "deploy*", "scripts*"]

''',
    },
    "workflow": {
        "main.py": '''"""{{ project_name }} — LARGESTACK workflow."""
import asyncio

from largestack import Workflow, Agent


async def fetch(state):
    agent = Agent(name="fetcher", llm="openai/gpt-4o-mini")
    r = await agent.run(state["topic"])
    state["facts"] = r.content
    return state


async def summarize(state):
    agent = Agent(name="summarizer", llm="openai/gpt-4o-mini")
    r = await agent.run(f"Summarize: {state['facts']}")
    state["summary"] = r.content
    return state


async def main():
    wf = Workflow("pipeline", mode="dag")
    wf.add_node("fetch", fetch)
    wf.add_node("summarize", summarize, deps=["fetch"])

    result = await wf.run({"topic": "Python async"})
    print(result["summary"])


if __name__ == "__main__":
    asyncio.run(main())
''',
        "pyproject.toml": '''[project]
name = "{{ project_name }}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["largestack>=1.0.0"]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[tool.largestack]
type = "workflow"

[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["tests*", "deploy*", "scripts*"]

''',
    },
    "mcp-server": {
        "main.py": '''"""{{ project_name }} — MCP server."""
from largestack._core.mcp_streamable import StreamableHTTPServer, create_fastapi_app

server = StreamableHTTPServer(
    name="{{ project_name }}",
    version="0.1.0",
)


async def search(query: str) -> str:
    """Search the knowledge base."""
    return f"Results for: {query}"


server.register_tool(
    "search",
    search,
    description="Search knowledge base",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)

app = create_fastapi_app(server)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
''',
        "pyproject.toml": '''[project]
name = "{{ project_name }}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "largestack>=1.0.0",
    "fastapi>=0.110",
    "uvicorn>=0.27",
]

[tool.largestack]
type = "mcp-server"

[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["tests*", "deploy*", "scripts*"]

''',
    },
}


PRODUCT_TEMPLATES = {
    "rag": {
        "title": "RAG Knowledge Assistant",
        "description": "Answer questions from local knowledge with retrieval and review.",
        "agents": [
            ("retriever", "Find relevant source material and cite it."),
            ("synthesizer", "Draft grounded answers from retrieved context."),
            ("evaluator", "Check answer faithfulness and missing citations."),
        ],
        "workflow": "router",
        "rag_mode": "hybrid",
        "graph_rag": True,
        "context": "knowledge",
        "knowledge_file": "product_faq.md",
        "knowledge_text": "# Product FAQ\n\nLARGESTACK projects keep source documents in app/rag/knowledge.\n",
        "sample_task": "What does this product do?",
    },
    "code-review": {
        "title": "Code Review Assistant",
        "description": "Review diffs for correctness, tests, security, and maintainability.",
        "agents": [
            ("scanner", "Scan changed files and identify risky areas."),
            ("reviewer", "Write actionable review findings with file references."),
            ("test-planner", "Suggest focused tests for the changed behavior."),
        ],
        "workflow": "sequential",
        "rag_mode": "local",
        "graph_rag": False,
        "context": "engineering",
        "knowledge_file": "review_policy.md",
        "knowledge_text": "# Review Policy\n\nLead with bugs, regressions, security risks, and missing tests.\n",
        "sample_task": "Review an authentication change.",
    },
    "ml-automation": {
        "title": "ML Automation Pipeline",
        "description": "Profile data, plan training, and review model readiness.",
        "agents": [
            ("data-profiler", "Summarize data quality and leakage risks."),
            ("trainer", "Plan model training and evaluation steps."),
            ("model-reviewer", "Review metrics, bias, drift, and deployment risk."),
        ],
        "workflow": "dag",
        "rag_mode": "hybrid",
        "graph_rag": False,
        "context": "ml",
        "knowledge_file": "model_card.md",
        "knowledge_text": "# Model Card\n\nTrack intended use, metrics, limits, and monitoring needs.\n",
        "sample_task": "Plan a churn model release.",
    },
    "website-builder": {
        "title": "Website Builder Agent",
        "description": "Plan pages, generate implementation tasks, and review UX quality.",
        "agents": [
            ("product-planner", "Clarify audience, pages, and success criteria."),
            ("builder", "Generate component and content tasks."),
            ("ux-reviewer", "Review responsiveness, accessibility, and polish."),
        ],
        "workflow": "supervisor",
        "rag_mode": "local",
        "graph_rag": False,
        "context": "web",
        "knowledge_file": "brand_notes.md",
        "knowledge_text": "# Brand Notes\n\nKeep layouts usable, responsive, accessible, and domain-specific.\n",
        "sample_task": "Design a services website.",
    },
    "video-pipeline": {
        "title": "Video Production Pipeline",
        "description": "Plan scripts, shots, assets, and production review.",
        "agents": [
            ("scriptwriter", "Draft scripts and scene beats."),
            ("producer", "Plan assets, timeline, and production steps."),
            ("quality-reviewer", "Review pacing, safety, and delivery readiness."),
        ],
        "workflow": "map-reduce",
        "rag_mode": "local",
        "graph_rag": False,
        "context": "media",
        "knowledge_file": "style_guide.md",
        "knowledge_text": "# Style Guide\n\nDefine tone, pacing, asset rules, and review standards.\n",
        "sample_task": "Plan a 60 second product demo.",
    },
    "social-media": {
        "title": "Social Media Automation",
        "description": "Plan campaigns, create posts, and review safety/brand fit.",
        "agents": [
            ("strategist", "Plan channels, audience, and message pillars."),
            ("creator", "Draft posts and variants."),
            ("safety-reviewer", "Check brand, policy, and sensitive claims."),
        ],
        "workflow": "debate",
        "rag_mode": "local",
        "graph_rag": False,
        "context": "marketing",
        "knowledge_file": "brand_policy.md",
        "knowledge_text": "# Brand Policy\n\nAvoid unsupported claims and keep approval for scheduled posts.\n",
        "sample_task": "Create a launch week campaign.",
    },
    "bfsi": {
        "title": "BFSI Regulated Assistant",
        "description": "Plan regulated workflows with strict guardrails and maker-checker controls.",
        "agents": [
            ("kyc-analyst", "Review KYC completeness and missing evidence."),
            ("risk-officer", "Assess financial, fraud, and compliance risk."),
            ("compliance-reviewer", "Check policy, audit, and approval requirements."),
        ],
        "workflow": "supervisor",
        "rag_mode": "hybrid",
        "graph_rag": True,
        "context": "bfsi",
        "strict": True,
        "knowledge_file": "compliance_policy.md",
        "knowledge_text": "# Compliance Policy\n\nCustomer PII and financial data require redaction, audit, and approved provider routing.\n",
        "sample_task": "Plan an NBFC onboarding workflow.",
    },
    "document-extraction": {
        "title": "Document Extraction Automation",
        "description": "Extract fields, validate evidence, and prepare export-ready results.",
        "agents": [
            ("extractor", "Extract requested fields from documents."),
            ("validator", "Validate confidence, source spans, and missing fields."),
            ("exporter", "Prepare normalized output for downstream systems."),
        ],
        "workflow": "sequential",
        "rag_mode": "hybrid",
        "graph_rag": True,
        "context": "document",
        "knowledge_file": "schema.md",
        "knowledge_text": "# Extraction Schema\n\nCapture source, confidence, and validation status for each field.\n",
        "sample_task": "Extract invoice fields.",
    },
}

PRODUCT_TEMPLATE_ALIASES = {
    "support-ticket": "support-ticket",
    "support-ticket-ai": "support-ticket",
    "rag-assistant": "rag",
    "knowledge": "rag",
    "code-reviewer": "code-review",
    "ml": "ml-automation",
    "ml-pipeline": "ml-automation",
    "website": "website-builder",
    "video": "video-pipeline",
    "social": "social-media",
    "social-media-automation": "social-media",
    "document": "document-extraction",
}

STYLE_CHOICES = {"yaml", "python", "hybrid"}
PROVIDER_CHOICES = {"deepseek", "openai", "anthropic", "gemini", "groq", "ollama", "multi"}
RAG_CHOICES = {"none", "local", "vector", "hybrid", "graph", "sql-vector"}
GUARDRAIL_CHOICES = {"warn", "protect", "strict", "custom"}

PROVIDER_MODELS = {
    "deepseek": "deepseek/deepseek-chat",
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-3-5-sonnet-latest",
    "gemini": "google/gemini-1.5-pro",
    "groq": "groq/llama-3.1-70b-versatile",
    "ollama": "ollama/llama3.1",
    "multi": "deepseek/deepseek-chat",
}

PROVIDER_ENV = {
    "deepseek": "LARGESTACK_DEEPSEEK_API_KEY",
    "openai": "LARGESTACK_OPENAI_API_KEY",
    "anthropic": "LARGESTACK_ANTHROPIC_API_KEY",
    "gemini": "LARGESTACK_GOOGLE_API_KEY",
    "groq": "LARGESTACK_GROQ_API_KEY",
    "ollama": "LARGESTACK_OLLAMA_BASE_URL",
}


def _normalise_package_name(value: str) -> str:
    """Return a valid PEP 621-ish project name from a path or display name."""
    import re
    base = Path(value).name or "largestack-agent"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._").lower()
    return name or "largestack-agent"


def available_templates() -> list[str]:
    """Return user-facing scaffold template names."""
    product_names = ["support-ticket", *PRODUCT_TEMPLATES.keys()]
    return sorted({*TEMPLATES.keys(), *product_names})


def _agent_yaml(agents: list[tuple[str, str]], *, model: str = "deepseek/deepseek-chat") -> str:
    lines = [
        "# Beginner file: define who works in your app.",
        "# Edit role first. Keep ids short because workflow.yaml references them.",
        "# Example agent:",
        "#   - id: researcher",
        "#     role: Find facts and cite sources.",
        f"#     model: {model}",
        "agents:",
    ]
    for agent_id, role in agents:
        lines.extend([
            f"  - id: {agent_id}",
            f"    role: {role}",
            f"    model: {model}",
            "    max_retries: 2",
            "    cost_budget: 1.0",
        ])
    return "\n".join(lines) + "\n"


def _workflow_yaml(workflow_id: str, mode: str, agents: list[tuple[str, str]], *, input_key: str = "task", output_key: str = "result") -> str:
    agent_ids = "\n".join(f"    - {agent_id}" for agent_id, _ in agents)
    return f"""# Beginner file: choose how agents run.
# Supported modes: sequential, parallel, router, supervisor, debate.
# Example: change mode to sequential for a simple left-to-right pipeline.
workflow:
  id: {workflow_id}
  mode: {mode}
  agents:
{agent_ids}
  input_key: {input_key}
  output_key: {output_key}
"""


def _workflow_graph(workflow_id: str, agents: list[tuple[str, str]]) -> str:
    lines = ["flowchart TD", f"  start([start]) --> {agents[0][0]}"]
    for (left, _), (right, _) in zip(agents, agents[1:]):
        lines.append(f"  {left} --> {right}")
    lines.append(f"  {agents[-1][0]} --> finish([finish])")
    lines.append("  classDef agent fill:#eef6ff,stroke:#2f5597,color:#111827")
    for agent_id, _ in agents:
        lines.append(f"  class {agent_id} agent")
    lines.append(f"  %% workflow: {workflow_id}")
    return "\n".join(lines) + "\n"


def _agent_groups_yaml(agents: list[tuple[str, str]], mode: str) -> str:
    agent_ids = "\n".join(f"      - {agent_id}" for agent_id, _ in agents)
    return f"""# Beginner file: group agents when your app grows past a few agents.
# For 10+ agents, create groups like intake, research, execution, review.
groups:
  - id: core
    mode: {mode}
    agents:
{agent_ids}
    approval:
      risky_tools: require_approval
      external_upload: block
"""


def _providers_yaml(provider: str) -> str:
    model = PROVIDER_MODELS[provider]
    fallback = ["openai/gpt-4o-mini"] if provider != "multi" else [
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-sonnet-latest",
        "groq/llama-3.1-70b-versatile",
    ]
    fallback_yaml = "\n".join(f"    - {item}" for item in fallback)
    keys_yaml = "\n".join(f"    {name}: {env}" for name, env in PROVIDER_ENV.items())
    return f"""# Beginner file: choose the default model and safe fallbacks.
# Do not paste API keys here. Put keys in .env using the env var names below.
# Example default: deepseek/deepseek-chat
providers:
  default: {model}
  fallback:
{fallback_yaml}
  keys:
{keys_yaml}
bfsi:
  # Strict/BFSI projects should route sensitive data only to approved providers.
  approved_providers:
    - {model}
"""


def _rag_yaml(spec: dict, rag_mode: str | None = None) -> str:
    mode = rag_mode or spec.get("rag_mode", "hybrid")
    enabled = mode != "none"
    graph_enabled = mode == "graph" or bool(spec.get("graph_rag"))
    return f"""# Beginner file: point Largestack AI at your knowledge files.
# Add Markdown/PDF/DOCX/CSV-derived files under app/rag/knowledge.
# Modes: none, local, vector, hybrid, graph, sql-vector.
rag:
  enabled: {"true" if enabled else "false"}
  sources:
    - id: local_knowledge
      type: local
      path: app/rag/knowledge
  retrieval:
    mode: {mode}
    top_k: 5
  citations: true  # Keep true when answers must cite source documents.
  graph:
    enabled: {"true" if graph_enabled else "false"}
    store: local
    relation_extraction: heuristic
"""


def _guardrails_yaml(
    context: str,
    *,
    strict: bool = False,
    mode_override: str | None = None,
    approved_provider: str | None = None,
) -> str:
    mode = mode_override or ("strict" if strict else "protect")
    strictish = mode == "strict" or strict
    pii_action = "redact" if strictish else "warn"
    provider = approved_provider or "deepseek/deepseek-chat"
    return f"""# Beginner file: configure safety without disabling intelligence.
# Modes: warn for benchmarks, protect for products, strict for BFSI/customer data.
# Risky write/delete/send/payment tools should require approval.
guardrails:
  mode: {mode}
  context: {context}
  pii_action: {pii_action}
  secret_action: redact
  financial_data_action: redact
  prompt_injection_action: warn
  tool_write_action: require_approval
  external_upload_action: block
  critical_risk_action: block
bfsi:
  strict_mode: {"true" if strictish else "false"}
  approved_providers:
    - {provider}
  maker_checker: true
  audit: true
"""


def _mcp_yaml() -> str:
    return """# Beginner file: optional MCP tool servers.
# Add servers with: largestack mcp add docs --url http://localhost:8080/mcp
# Keep approval: require_approval until you trust the server and its tools.
mcp:
  servers: []
"""


def _product_template_files(
    template_type: str,
    display_name: str,
    *,
    provider: str = "deepseek",
    rag: str | None = None,
    guardrails: str | None = None,
) -> dict[str, str]:
    spec = PRODUCT_TEMPLATES[template_type]
    agents = spec["agents"]
    module_name = template_type.replace("-", "_")
    workflow_id = template_type.replace("-", "_")
    title = spec["title"]
    sample_task = spec["sample_task"]
    first_agent = agents[0][0]
    model = PROVIDER_MODELS[provider]
    return {
        "README.md": f"""# {display_name}

{title} template for Largestack AI.

## First Run

```bash
cp .env.example .env
pip install -e .[dev]
largestack doctor
largestack explain
largestack graph
largestack knowledge list
largestack rag explain
largestack run app/main.py --task "{sample_task}"
largestack test
```

## What To Edit

- `providers.yaml`: provider defaults, fallback routing, and BFSI approved providers.
- `agents.yaml`: per-agent model, budget, retries, and role definitions.
- `agent_groups.yaml`: group mode for sequential, parallel, router, supervisor, debate, or map-reduce.
- `workflow.yaml`: runnable workflow shape.
- `workflow_graph.mmd`: Mermaid graph for documentation and review.
- `rag.yaml`: local/vector/graph RAG source settings.
- `guardrails.yaml`: redaction, approval, provider routing, and strict-mode controls.
- `mcp.yaml`: optional MCP servers that expose external tools.
- `app/`: advanced Python code for agents, tools, workflow, and RAG.

## What Each File Does

- `.env.example`: copy to `.env`; add provider keys locally, never commit them.
- `largestack.yaml`: project defaults such as model, tracing, budget, and config style.
- `providers.yaml`: default model, fallback models, key env var names, and approved providers.
- `agents.yaml`: beginner agent list and responsibilities.
- `agent_groups.yaml`: how to organize many agents into safe teams.
- `tools.yaml`: tool list plus approval policy for risky actions.
- `workflow.yaml`: route and orchestration mode.
- `workflow_graph.mmd`: Mermaid diagram for docs/reviews.
- `rag.yaml`: local/vector/hybrid/graph knowledge settings.
- `guardrails.yaml`: warn/protect/strict safety behavior.
- `mcp.yaml`: optional MCP servers; discovered tools should stay approval-gated.
- `app/`: Python implementation.
- `tests/`: offline tests that should pass before using live providers.

## Provider Setup

Default model: `{model}`. Put provider keys in `.env`; keys are never printed by Largestack AI.

## RAG And Guardrails

Knowledge lives in `app/rag/knowledge`. Run `largestack rag build` after adding documents.
Risky write, delete, send, and payment tools require approval by default.
""",
        "providers.yaml": _providers_yaml(provider),
        "agents.yaml": _agent_yaml(agents, model=model),
        "agent_groups.yaml": _agent_groups_yaml(agents, spec["workflow"]),
        "workflow.yaml": _workflow_yaml(workflow_id, spec["workflow"], agents),
        "workflow_graph.mmd": _workflow_graph(workflow_id, agents),
        "rag.yaml": _rag_yaml(spec, rag),
        "guardrails.yaml": _guardrails_yaml(
            spec["context"],
            strict=bool(spec.get("strict")),
            mode_override=("strict" if spec.get("strict") and guardrails == "protect" else guardrails),
            approved_provider=model,
        ),
        "mcp.yaml": _mcp_yaml(),
        f"app/agents/{module_name}.py": "\n".join(
            [
                "from largestack import Agent",
                "",
                *[
                    (
                        f"{agent_id.replace('-', '_')} = Agent("
                        f"name='{agent_id}', llm='{model}', instructions='{role}')"
                    )
                    for agent_id, role in agents
                ],
                "",
            ]
        ),
        f"app/tools/{module_name}_tools.py": f"""def classify_task(task: str) -> dict:
    lowered = task.lower()
    priority = 'high' if any(word in lowered for word in ['urgent', 'risk', 'breach', 'fraud']) else 'normal'
    return {{'template': '{template_type}', 'priority': priority, 'length': len(task)}}


def summarize_result(task: str) -> str:
    return f"{title}: ready to process {{task}}"
""",
        f"app/workflows/{module_name}_flow.py": f"""from app.tools.{module_name}_tools import classify_task, summarize_result


def run_template(task: str) -> dict:
    return {{
        'classification': classify_task(task),
        'summary': summarize_result(task),
    }}
""",
        "app/main.py": f"""from app.workflows.{module_name}_flow import run_template


if __name__ == '__main__':
    result = run_template('{sample_task}')
    print(result['summary'])
""",
        f"app/rag/knowledge/{spec['knowledge_file']}": spec["knowledge_text"],
        f"tests/test_{module_name}.py": f"""from app.tools.{module_name}_tools import classify_task, summarize_result
from app.workflows.{module_name}_flow import run_template


def test_classify_task_offline():
    result = classify_task('urgent review')
    assert result['template'] == '{template_type}'
    assert result['priority'] == 'high'


def test_run_template_offline():
    result = run_template('{sample_task}')
    assert '{title}' in result['summary']


def test_first_agent_is_documented():
    assert '{first_agent}' in open('agents.yaml').read()
""",
    }


def scaffold(
    project_name: str,
    template_type: str = "agent",
    *,
    style: str = "hybrid",
    provider: str = "deepseek",
    rag: str = "hybrid",
    guardrails: str = "protect",
) -> dict:
    """Create a new Largestack AI project from a template."""
    style = style.replace("_", "-").lower()
    provider = provider.replace("_", "-").lower()
    rag = rag.replace("_", "-").lower()
    guardrails = guardrails.replace("_", "-").lower()
    if style not in STYLE_CHOICES:
        raise ValueError(f"Unknown style: {style}. Choose from: {sorted(STYLE_CHOICES)}")
    if provider not in PROVIDER_CHOICES:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {sorted(PROVIDER_CHOICES)}")
    if rag not in RAG_CHOICES:
        raise ValueError(f"Unknown rag mode: {rag}. Choose from: {sorted(RAG_CHOICES)}")
    if guardrails not in GUARDRAIL_CHOICES:
        raise ValueError(f"Unknown guardrails mode: {guardrails}. Choose from: {sorted(GUARDRAIL_CHOICES)}")
    requested_template = template_type
    template_type = template_type.replace("_", "-")
    product_template = PRODUCT_TEMPLATE_ALIASES.get(template_type, template_type)
    template_key = "agent" if product_template in {"support-ticket", *PRODUCT_TEMPLATES.keys()} else product_template
    if template_key not in TEMPLATES:
        choices = available_templates()
        raise ValueError(f"Unknown template: {requested_template}. Choose from: {choices}")
    
    project_path = Path(project_name)
    if project_path.exists():
        raise FileExistsError(f"Directory already exists: {project_path}")
    
    project_path.mkdir(parents=True)
    package_name = _normalise_package_name(project_name)
    display_name = project_path.name or package_name
    
    template = TEMPLATES[template_key]
    files_created = []
    model = PROVIDER_MODELS[provider]
    
    for filename, content in template.items():
        rendered = (
            content
            .replace("{{ project_name }}", package_name)
            .replace("{{ display_name }}", display_name)
        )
        file_path = project_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(rendered)
        files_created.append(str(file_path))
    
    # Production-shaped common scaffold for agent projects. Keep legacy root
    # main.py/AGENTS.md while adding the app/tests/deploy layout documented for
    # largestack init.
    if template_key == "agent":
        common_files = {
            "largestack.yaml": f"""# Beginner file: project-wide runtime defaults.
# Edit default_llm and cost_budget first.
# Example model: deepseek/deepseek-chat
schema_version: '1.1'
project_name: {display_name}
config_style: {style}
default_llm: {model}
max_turns: 25
cost_budget: 5.0
trace_enabled: true
guardrails_enabled: true
""",
            "providers.yaml": _providers_yaml(provider),
            "agents.yaml": f"""# Beginner file: define the agents in your app.
# Edit role first. workflow.yaml references these ids.
# Example: add another agent with `largestack add agent auditor`.
agents:
  - id: planner
    role: Plan the work and identify risks.
    model: {model}
    max_retries: 2
    cost_budget: 1.0
  - id: executor
    role: Execute the plan with tools and RAG.
    model: {model}
    max_retries: 2
    cost_budget: 2.0
  - id: reviewer
    role: Review output for correctness, safety, and completeness.
    model: {model}
    max_retries: 2
    cost_budget: 1.0
""",
            "tools.yaml": """# Beginner file: list tools agents may call.
# Read-only tools can set approval: false.
# Unsafe actions like write/delete/send/payment should require approval.
tools:
  - id: add
    module: app.tools.business_tools
    function: add
    access: read
    approval: false
approval_policy:
  write: require_approval
  delete: require_approval
  payment: require_approval
  send: require_approval
""",
            "workflow.yaml": """# Beginner file: choose how agents run.
# Supported modes: sequential, parallel, router, supervisor, debate.
# Example: switch to sequential for planner -> executor -> reviewer.
workflow:
  id: main
  mode: supervisor
  agents:
    - planner
    - executor
    - reviewer
  input_key: task
  output_key: final_output
""",
            "agent_groups.yaml": """# Beginner file: group agents when the project grows.
# For 10+ agents, create groups such as intake, research, execution, review.
groups:
  - id: core
    mode: supervisor
    agents:
      - planner
      - executor
      - reviewer
    approval:
      risky_tools: require_approval
      external_upload: block
""",
            "workflow_graph.mmd": """%% Generated by Largestack AI. Refresh with: largestack graph --write
flowchart TD
  start([start]) --> planner
  planner --> executor
  executor --> reviewer
  reviewer --> finish([finish])
  classDef agent fill:#eef6ff,stroke:#2f5597,color:#111827
  class planner,executor,reviewer agent
""",
            "rag.yaml": _rag_yaml({"rag_mode": "hybrid", "graph_rag": False}, rag),
            "guardrails.yaml": _guardrails_yaml("general", mode_override=guardrails, approved_provider=model),
            "mcp.yaml": _mcp_yaml(),
            "app/__init__.py": "",
            "app/agents/__init__.py": "",
            "app/agents/planner.py": f"""from largestack import Agent

planner = Agent(name='planner', llm='{model}', instructions='Plan the work.')
""",
            "app/agents/executor.py": f"""from largestack import Agent

executor = Agent(name='executor', llm='{model}', instructions='Execute the plan.')
""",
            "app/agents/reviewer.py": f"""from largestack import Agent

reviewer = Agent(name='reviewer', llm='{model}', instructions='Review and validate the result.')
""",
            "app/tools/__init__.py": "",
            "app/tools/business_tools.py": """from largestack import tool

@tool
def add(a: int, b: int) -> int:
    return a + b
""",
            "app/workflows/__init__.py": "",
            "app/workflows/main_flow.py": """from largestack import Orchestrator
from app.agents.planner import planner
from app.agents.executor import executor
from app.agents.reviewer import reviewer

orchestrator = Orchestrator(strategy='supervisor', agents=[planner, executor, reviewer])
""",
            "app/rag/ingest.py": """from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / 'knowledge'

def documents() -> list[Path]:
    return sorted(KNOWLEDGE_DIR.glob('*.md'))
""",
            "app/rag/knowledge/README.md": "# Knowledge base\n\nAdd Markdown/PDF-derived text here.\n",
            "app/main.py": """from app.workflows.main_flow import orchestrator

if __name__ == '__main__':
    result = orchestrator.run_sync('Create a short validation plan') if hasattr(orchestrator, 'run_sync') else None
    print(result.final_output if result else 'Project scaffold ready')
""",
            "tests/test_agents.py": """from app.agents.planner import planner
from app.agents.executor import executor
from app.agents.reviewer import reviewer

def test_agents_named():
    assert planner.name == 'planner'
    assert executor.name == 'executor'
    assert reviewer.name == 'reviewer'
""",
            "tests/test_tools.py": """from app.tools.business_tools import add

def test_add_tool():
    assert add(2, 3) == 5
""",
            "tests/test_workflow.py": """from app.workflows.main_flow import orchestrator

def test_workflow_has_agents():
    assert len(orchestrator.agents) == 3
""",
            "deploy/Dockerfile": """FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .
CMD ['python', 'main.py']
""".replace("'", '"'),
            "deploy/docker-compose.yml": """services:
  app:
    build: .
    env_file: ../.env
""",
            "deploy/helm/README.md": "# Helm chart placeholder\n\nAdd deployment-specific chart values before production.\n",
            "scripts/run_local.py": """from app.main import *  # noqa: F401,F403
""",
            "scripts/smoke_test.py": """from app.tools.business_tools import add

assert add(1, 2) == 3
print('smoke ok')
""",
        }
        for filename, content in common_files.items():
            file_path = project_path / filename
            if file_path.exists():
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            files_created.append(str(file_path))

    if product_template in PRODUCT_TEMPLATES:
        product_files = _product_template_files(
            product_template,
            display_name,
            provider=provider,
            rag=rag,
            guardrails=guardrails,
        )
        for filename, content in product_files.items():
            file_path = project_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            if str(file_path) not in files_created:
                files_created.append(str(file_path))

    if product_template == "support-ticket":
        support_files = {
            "README.md": f"""# {display_name}

Support-ticket AI template for Largestack AI.

## First Run

```bash
cp .env.example .env
pip install -e .[dev]
largestack doctor
largestack explain
largestack graph
largestack rag explain
largestack run app/main.py --task "Triage refund request for order 123"
largestack test
```

## What To Edit

- `agents.yaml`: tune `triage`, `resolver`, and `qa` responsibilities.
- `tools.yaml`: add CRM/helpdesk tools. Write/send/delete/payment tools should require approval.
- `workflow.yaml`: change routing from supervisor to sequential/router as needed.
- `rag.yaml`: add help-center articles under `app/rag/knowledge`.
- `guardrails.yaml`: set `mode: strict` for customer-sensitive or BFSI deployments.
- `mcp.yaml`: add external MCP tool servers only after review.
- `app/agents/`: advanced Python agent code.
- `app/tools/ticket_tools.py`: deterministic support utilities.
- `tests/`: offline safety checks that do not call an LLM.

## What Each File Does

- `.env.example`: copy to `.env`; add DeepSeek/OpenAI/etc keys locally.
- `largestack.yaml`: project defaults for model, budget, tracing, and guardrails.
- `providers.yaml`: model routing and approved provider list.
- `agents.yaml`: the simple triage/resolver/qa roster.
- `agent_groups.yaml`: the support team grouping and approval expectations.
- `tools.yaml`: safe read tools plus refund/email/delete approval policy.
- `workflow.yaml`: ticket -> triage -> resolver -> qa route.
- `workflow_graph.mmd`: visual Mermaid workflow.
- `rag.yaml`: support docs and retrieval mode.
- `guardrails.yaml`: customer-support safety mode.
- `mcp.yaml`: optional MCP servers for third-party tools.
- `app/tools/ticket_tools.py`: deterministic helper functions.
- `app/workflows/support_flow.py`: offline runnable support flow.
- `tests/`: provider-free checks for generated behavior.

## Approval Demo

Refunds, CRM updates, customer-data deletes, and email sends are configured as `require_approval`.
This means the project can plan the action, but production code should pause for a human or maker-checker before execution.

## Provider Setup

Default model: `{model}`. Add provider keys to `.env`; Largestack AI diagnostics only show whether keys are set.

## RAG And Guardrails

Add support docs under `app/rag/knowledge`, then run `largestack rag build`.
CRM updates, email sends, refunds, and deletes require approval by default.
""",
            "agents.yaml": f"""# Beginner file: support-ticket agents.
# Edit role first. Keep ids because workflow.yaml references them.
# Example: add `billing-reviewer` with largestack add agent billing-reviewer.
agents:
  - id: triage
    role: Classify ticket priority, product area, sentiment, and missing information.
    model: {model}
    max_retries: 2
    cost_budget: 1.0
  - id: resolver
    role: Draft grounded support replies using policy/RAG and tool results.
    model: {model}
    max_retries: 2
    cost_budget: 2.0
  - id: qa
    role: Check tone, correctness, escalation, PII, and approval requirements.
    model: {model}
    max_retries: 2
    cost_budget: 1.0
""",
            "tools.yaml": """# Beginner file: support tools.
# Read tools are allowed. CRM updates, email sends, refunds, and deletes require approval.
# Example unsafe tool: refund_payment -> require_approval.
tools:
  - id: classify_ticket
    module: app.tools.ticket_tools
    function: classify_ticket
    access: read
    approval: false
  - id: draft_reply
    module: app.tools.ticket_tools
    function: draft_reply
    access: read
    approval: false
approval_policy:
  crm_update: require_approval
  send_email: require_approval
  refund_payment: require_approval
  delete_customer_data: require_approval
""",
            "workflow.yaml": """# Beginner file: support-ticket workflow.
# Supported modes: sequential, parallel, router, supervisor, debate.
# Example: use router when ticket type decides which agent runs next.
workflow:
  id: support_ticket
  mode: supervisor
  agents:
    - triage
    - resolver
    - qa
  input_key: ticket
  output_key: response
""",
            "agent_groups.yaml": """# Beginner file: group support agents.
# For 10+ agents, split into intake, billing, technical, escalation, and QA groups.
groups:
  - id: support_team
    mode: supervisor
    agents:
      - triage
      - resolver
      - qa
    approval:
      crm_update: require_approval
      send_email: require_approval
      refund_payment: require_approval
""",
            "workflow_graph.mmd": """%% Generated by Largestack AI. Refresh with: largestack graph --write
flowchart TD
  start([ticket]) --> triage
  triage --> resolver
  resolver --> qa
  qa --> finish([response])
  classDef agent fill:#eef6ff,stroke:#2f5597,color:#111827
  class triage,resolver,qa agent
""",
            "rag.yaml": _rag_yaml({"rag_mode": "hybrid", "graph_rag": True}, rag),
            "guardrails.yaml": _guardrails_yaml("customer_support", mode_override=guardrails, approved_provider=model),
            "app/agents/triage.py": f"""from largestack import Agent

triage = Agent(
    name='triage',
    llm='{model}',
    instructions='Classify support tickets and identify escalation needs.',
)
""",
            "app/agents/resolver.py": f"""from largestack import Agent

resolver = Agent(
    name='resolver',
    llm='{model}',
    instructions='Draft grounded, concise customer support replies.',
)
""",
            "app/agents/qa.py": f"""from largestack import Agent

qa = Agent(
    name='qa',
    llm='{model}',
    instructions='Review support responses for safety, policy, tone, and correctness.',
)
""",
            "app/tools/ticket_tools.py": """from dataclasses import dataclass


@dataclass(frozen=True)
class TicketClassification:
    priority: str
    category: str
    needs_human: bool


def classify_ticket(text: str) -> TicketClassification:
    lowered = text.lower()
    priority = 'high' if any(word in lowered for word in ['urgent', 'fraud', 'breach', 'legal']) else 'normal'
    category = 'refund' if 'refund' in lowered else 'general'
    return TicketClassification(priority=priority, category=category, needs_human=priority == 'high')


def draft_reply(customer_name: str, issue: str) -> str:
    return f'Hi {customer_name}, thanks for contacting support. We are reviewing: {issue}'
""",
            "app/workflows/support_flow.py": """from app.tools.ticket_tools import classify_ticket, draft_reply


def run_support_ticket(ticket: str, customer_name: str = 'there') -> dict:
    classification = classify_ticket(ticket)
    reply = draft_reply(customer_name, ticket)
    return {'classification': classification, 'reply': reply}
""",
            "app/main.py": """from app.workflows.support_flow import run_support_ticket


if __name__ == '__main__':
    result = run_support_ticket('Customer asks for refund on a delayed order')
    print(result['reply'])
""",
            "app/rag/knowledge/refund_policy.md": """# Refund Policy

Refund requests should be acknowledged, checked against order status, and escalated for high-risk or regulated cases.
""",
            "tests/test_support_ticket.py": """from app.tools.ticket_tools import classify_ticket, draft_reply


def test_classify_refund_ticket():
    result = classify_ticket('urgent refund request')
    assert result.priority == 'high'
    assert result.category == 'refund'
    assert result.needs_human is True


def test_draft_reply_does_not_need_provider():
    assert 'reviewing' in draft_reply('Asha', 'refund request')
""",
        }
        for filename, content in support_files.items():
            file_path = project_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            if str(file_path) not in files_created:
                files_created.append(str(file_path))
    
    return {
        "project_name": package_name,
        "project_path": str(project_path),
        "type": product_template,
        "files_created": files_created,
        "next_steps": [
            f"cd {project_path}",
            "cp .env.example .env  # add API keys" if template_key == "agent" else "# Configure project",
            "pip install -e .\\[dev]",
            "largestack doctor",
            "largestack explain",
            "largestack run app/main.py",
            "largestack test",
        ],
    }
