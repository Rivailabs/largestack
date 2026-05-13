"""Live DeepSeek certification for real LARGESTACK feature projects.

This harness is deliberately stricter than the broad 24-project domain suite.
It still asks DeepSeek, through ``largestack.Agent``, to generate 24 projects,
but every generated project must also include a runnable ``largestack_app.py``
that imports and executes real LARGESTACK APIs: Agent/tools, Team, Workflow,
Orchestrator, RAG, memory, guardrails, typed decorators, and observability.

The generated projects must avoid network side effects during their own tests:
DeepSeek is used for generation/review, while project runtime checks use
LARGESTACK's TestModel/FunctionModel overrides.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from largestack import Agent
from largestack.autonomous_builder import (
    AutonomousProjectBuilder,
    BuilderBudget,
    BuildReport,
    NoOpMemory,
    ProjectSpec,
    redact_sensitive,
    serialize_report,
    summarize_report,
)
from scripts.final_95_plus_certify import (
    make_specs as make_domain_specs,
    project_has_readme,
    scan_project_security,
)

MODEL = "deepseek/deepseek-chat"
PROJECT_MIN_SCORE = 90
SUITE_MIN_AVERAGE = 95.0
B2B_PROJECT_MIN_SCORE = 95
B2B_SUITE_MIN_AVERAGE = 98.0


@dataclass(frozen=True)
class FeatureContract:
    name: str
    calls: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    attrs: tuple[str, ...] = ()
    substrings: tuple[str, ...] = ()
    evidence_keys: tuple[str, ...] = ()
    instructions: str = ""


FEATURES: dict[str, FeatureContract] = {
    "agent_tool_cost": FeatureContract(
        name="agent_tool_cost",
        calls=("Agent", "TestModel"),
        names=("tool",),
        attrs=("override", "run"),
        substrings=("cost_budget=", "lookup_policy"),
        evidence_keys=("agent_tool_calls", "agent_cost_budget"),
        instructions=(
            "Create an @tool async lookup_policy(query: str) and a largestack.Agent with "
            "llm='deepseek/deepseek-chat', tools=[lookup_policy], cost_budget set, max_turns set. "
            "Run it under agent.override(model=TestModel(call_tools=['lookup_policy'], "
            "custom_tool_args={'lookup_policy': {'query': 'refund'}})). "
            "Evidence must include agent_tool_calls and agent_cost_budget. Prefer "
            "agent_tool_calls=result.tool_calls_made; a nonzero count is acceptable only if the "
            "source still shows lookup_policy in the tool registration and TestModel call."
        ),
    ),
    "rag_citations": FeatureContract(
        name="rag_citations",
        calls=("Agent", "TestModel", "create_rag"),
        attrs=("as_tool", "build_context", "override", "run"),
        evidence_keys=("rag_context", "rag_tool_calls"),
        instructions=(
            "Use create_rag(documents=[...], chunk_size=100, top_k=2), call "
            "build_context(query='duplicate payments'), "
            "convert it with as_tool(), attach that tool to an Agent, and run with TestModel "
            "calling search_knowledge. Evidence must include rag_context with '[Source' and "
            "rag_tool_calls."
        ),
    ),
    "memory_isolation": FeatureContract(
        name="memory_isolation",
        calls=("create_memory",),
        attrs=("add_message", "get_messages"),
        evidence_keys=("memory_messages", "cross_user_leak"),
        instructions=(
            "Use create_memory('buffer') or create_memory('sliding_window'). ConversationMemory "
            "has async add_message(message_dict) and sync get_messages() with no arguments. "
            "For isolation, create separate memory objects for separate users/sessions or filter "
            "the returned message dicts yourself. Evidence must include memory_messages >= 2 "
            "and cross_user_leak False."
        ),
    ),
    "workflow_dag": FeatureContract(
        name="workflow_dag",
        calls=("Agent", "Workflow", "TestModel"),
        attrs=("add_agent", "run", "override"),
        evidence_keys=("workflow_status", "workflow_steps"),
        instructions=(
            "Build a Workflow(name, mode='dag', cost_budget=...) with at least two Agent nodes, "
            "wire dependencies with add_agent(..., deps=[...]), override both agents with "
            "TestModel, run the workflow with await workflow.run({'task': '...'}), and report "
            "workflow_status=result.status and workflow_steps=len(result.steps)."
        ),
    ),
    "team_sequential": FeatureContract(
        name="team_sequential",
        calls=("Agent", "Team", "TestModel"),
        substrings=("strategy=",),
        attrs=("override", "run"),
        evidence_keys=("team_strategy", "team_output"),
        instructions=(
            "Create a Team with strategy=\"sequential\" and two Agents overridden with TestModel. "
            "Evidence must include team_strategy='sequential' and non-empty team_output."
        ),
    ),
    "team_parallel": FeatureContract(
        name="team_parallel",
        calls=("Agent", "Team", "TestModel"),
        substrings=("strategy=",),
        attrs=("override", "run"),
        evidence_keys=("team_strategy", "team_output"),
        instructions=(
            "Create a Team with strategy=\"parallel\" and at least two Agents overridden with "
            "TestModel. Team.run returns one AgentResult with combined content, not a tuple/list. "
            "Use result.content for team_output. Evidence must include team_strategy='parallel' "
            "and non-empty team_output."
        ),
    ),
    "orchestrator_router": FeatureContract(
        name="orchestrator_router",
        calls=("Agent", "Orchestrator", "TestModel"),
        substrings=("strategy=",),
        attrs=("override", "run"),
        evidence_keys=("orchestrator_strategy", "route_output"),
        instructions=(
            "Use Orchestrator(strategy=\"router\", classifier=..., routes={...}) with a classifier "
            "and routed specialist Agents overridden with TestModel. Orchestrator.run returns "
            "OrchestratorResult; use result.output for route_output, not result.content. Evidence "
            "must include orchestrator_strategy='router' and route_output."
        ),
    ),
    "orchestrator_map_reduce": FeatureContract(
        name="orchestrator_map_reduce",
        calls=("Agent", "Orchestrator", "TestModel"),
        substrings=("strategy=",),
        attrs=("override", "run"),
        evidence_keys=("orchestrator_strategy", "map_items"),
        instructions=(
            "Use Agent objects for mapper and reducer, then Orchestrator(strategy=\"map_reduce\", "
            "mapper=mapper_agent, reducer=reducer_agent). Override mapper and reducer with "
            "TestModel('mapped') and TestModel('summary'), run at least three items, and report "
            "orchestrator_strategy='map_reduce' and map_items >= 3."
        ),
    ),
    "guardrails_pii": FeatureContract(
        name="guardrails_pii",
        calls=("create_guardrails",),
        attrs=("check_output",),
        evidence_keys=("redacted_text",),
        instructions=(
            "Use create_guardrails(pii=True, injection=True, pii_action='redact'), run "
            "await guardrails.check_output(response) against a types.SimpleNamespace(content=...) "
            "object containing test@example.com. check_output mutates response.content and returns "
            "None. Report redacted_text=response.content without the raw email."
        ),
    ),
    "tool_policy_approval": FeatureContract(
        name="tool_policy_approval",
        calls=("Agent", "TestModel"),
        names=("tool",),
        substrings=("tool_permissions", "dangerous_delete"),
        attrs=("override", "run"),
        evidence_keys=("risky_action_executed", "denied_tools"),
        instructions=(
            "Import tool from largestack. Define @tool-decorated safe_tool and dangerous_delete "
            "functions, create an Agent with "
            "tool_permissions={'deny': ['dangerous_delete']}, run it with TestModel calling only "
            "the safe tool, and report risky_action_executed False plus denied_tools=['dangerous_delete']. "
            "Do not set denied_tools from result.tool_calls_made."
        ),
    ),
    "typed_decorator_api": FeatureContract(
        name="typed_decorator_api",
        calls=("TypedAgent", "TestModel"),
        names=("RunContext", "ModelRetry"),
        attrs=("tool", "tool_plain", "output_validator", "override", "run"),
        evidence_keys=("typed_tools", "typed_output"),
        instructions=(
            "Use from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry. "
            "Create a dataclass dependency, register one context tool with @agent.tool, one plain "
            "tool with @agent.tool_plain, and one output_validator that can raise ModelRetry. "
            "Constructor is TypedAgent[Deps, str]('deepseek/deepseek-chat', deps_type=Deps, "
            "output_type=str, instructions='...', name='typed', max_retries=1, cost_budget=0.1). "
            "It does not accept llm= or max_turns=. Run under TestModel(custom_output_text='typed ok', "
            "call_tools=[]) and report typed_tools=list(agent.tools.keys()) and typed_output=result.output."
        ),
    ),
    "observability_trace": FeatureContract(
        name="observability_trace",
        calls=("Agent", "TestModel"),
        names=("capture_run_messages",),
        attrs=("override", "run"),
        evidence_keys=("trace_id", "captured_messages", "total_cost", "redacted_log"),
        instructions=(
            "Use capture_run_messages around an Agent run with TestModel. Evidence must include "
            "trace_id, captured_messages as an integer count >= 2, total_cost >= 0, and "
            "redacted_log that does not contain any raw real-looking sk- key. Prefer text like "
            "'[REDACTED] no secret keys present'."
        ),
    ),
}


FEATURE_MATRIX: list[tuple[str, ...]] = [
    ("agent_tool_cost", "tool_policy_approval"),
    ("team_sequential", "memory_isolation"),
    ("workflow_dag", "observability_trace"),
    ("rag_citations", "guardrails_pii"),
    ("orchestrator_router", "team_parallel"),
    ("typed_decorator_api", "memory_isolation"),
    ("orchestrator_map_reduce", "agent_tool_cost"),
    ("rag_citations", "memory_isolation"),
    ("workflow_dag", "rag_citations"),
    ("guardrails_pii", "observability_trace"),
    ("team_parallel", "tool_policy_approval"),
    ("typed_decorator_api", "workflow_dag"),
    ("agent_tool_cost", "guardrails_pii"),
    ("orchestrator_router", "memory_isolation"),
    ("orchestrator_map_reduce", "team_sequential"),
    ("rag_citations", "observability_trace"),
    ("workflow_dag", "tool_policy_approval"),
    ("typed_decorator_api", "guardrails_pii"),
    ("team_parallel", "memory_isolation"),
    ("orchestrator_router", "agent_tool_cost"),
    ("rag_citations", "tool_policy_approval"),
    ("workflow_dag", "team_sequential"),
    ("typed_decorator_api", "observability_trace"),
    ("orchestrator_map_reduce", "guardrails_pii"),
    ("workflow_dag", "tool_policy_approval", "guardrails_pii"),
    ("orchestrator_router", "rag_citations", "observability_trace"),
]


@dataclass
class ReviewerOutcome:
    score: int = 0
    passed: bool = False
    json_valid: bool = False
    notes: str = ""
    critical_blocker: str = ""


@dataclass
class FeatureProjectCertification:
    name: str
    features: list[str]
    passed: bool
    score: int
    blocker_type: str
    failed_checks: list[str] = field(default_factory=list)
    project_path: str = ""
    report_path: str = ""
    reviewer: ReviewerOutcome = field(default_factory=ReviewerOutcome)
    generated_files: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    tokens: int = 0
    actual_cost: float = 0.0


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-realfeatures24")


def redact(text: str) -> str:
    text = redact_sensitive(text or "")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "sk-REDACTED", text)
    text = re.sub(r"(LARGESTACK_[A-Z0-9_]*API_KEY=)[^\s]+", r"\1REDACTED", text)
    return text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def progress(message: str) -> None:
    print(f"[realfeatures24] {message}", flush=True)


def ast_acceptance_helpers() -> str:
    return r'''
from pathlib import Path
import ast, asyncio
from largestack.testing import block_model_requests

src = Path("largestack_app.py").read_text()
tree = ast.parse(src)
calls = set()
names = set()
attrs = set()
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        imports.add(node.module or "")
        for alias in node.names:
            names.add(alias.asname or alias.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            imports.add(alias.name)
            names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        attrs.add(node.attr)
    elif isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name):
            calls.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            calls.add(fn.attr)
            attrs.add(fn.attr)
        elif isinstance(fn, ast.Subscript):
            base = fn.value
            if isinstance(base, ast.Name):
                calls.add(base.id)
            elif isinstance(base, ast.Attribute):
                calls.add(base.attr)
                attrs.add(base.attr)

class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
for forbidden_class in {"Agent", "Team", "Workflow", "Orchestrator", "TestModel", "FunctionModel", "Tool"}:
    assert forbidden_class not in class_names, (
        "Do not define local mocks/replacements for LARGESTACK classes",
        forbidden_class,
        class_names,
    )
assert any(m == "largestack" or m.startswith("largestack.") for m in imports), (
    "largestack_app.py must import the real largestack package; "
    "do not create local Agent/TestModel/Tool mocks",
    imports,
)
assert Path("README.md").exists(), "README.md required"
assert Path("largestack_app.py").exists(), "largestack_app.py required"
files = [p for p in Path(".").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
assert len(files) >= 5, f"expected at least 5 project files, got {len(files)}"
assert Path("data").exists() or Path("policies").exists(), "expected data/ or policies/ evidence files"

all_text = "\n".join(p.read_text(errors="ignore") for p in files if p.suffix in {".py", ".md", ".json", ".txt"})
import re
assert not re.search(r"\bsk-[A-Za-z0-9_-]{12,}\b", all_text), "project must not contain real-looking API keys"

from largestack_app import run_largestack_smoke
with block_model_requests():
    out = asyncio.run(run_largestack_smoke())
assert out["status"] == "ok", out
assert isinstance(out.get("evidence"), dict), out
features = set(out.get("features", []))
evidence = out["evidence"]
'''


def make_feature_assertions(feature_names: tuple[str, ...]) -> str:
    lines: list[str] = []
    required_calls: set[str] = set()
    required_names: set[str] = set()
    required_attrs: set[str] = set()
    required_substrings: set[str] = set()
    required_evidence: set[str] = set()
    for name in feature_names:
        contract = FEATURES[name]
        required_calls.update(contract.calls)
        required_names.update(contract.names)
        required_attrs.update(contract.attrs)
        required_substrings.update(contract.substrings)
        required_evidence.update(contract.evidence_keys)
        lines.append(f"assert {name!r} in features, out")
    for item in sorted(required_calls):
        lines.append(f"assert {item!r} in calls, ('missing call', {item!r}, calls)")
    for item in sorted(required_names):
        lines.append(f"assert {item!r} in names, ('missing name', {item!r}, names)")
    for item in sorted(required_attrs):
        lines.append(f"assert {item!r} in attrs, ('missing attr', {item!r}, attrs)")
    for item in sorted(required_substrings):
        lines.append(f"assert {item!r} in src, ('missing substring', {item!r})")
    for item in sorted(required_evidence):
        lines.append(f"assert {item!r} in evidence, ('missing evidence', {item!r}, evidence)")

    if "agent_tool_cost" in feature_names:
        lines.extend(
            [
                'agent_calls = evidence["agent_tool_calls"]',
                'assert (isinstance(agent_calls, int) and agent_calls > 0) or (not isinstance(agent_calls, int) and "lookup_policy" in agent_calls), evidence',
                'assert float(evidence["agent_cost_budget"]) > 0, evidence',
            ]
        )
    if "rag_citations" in feature_names:
        lines.extend(
            [
                'rag_context_text = "\\n".join(evidence["rag_context"]) if isinstance(evidence["rag_context"], list) else str(evidence["rag_context"])',
                'assert "[Source" in rag_context_text, evidence',
                'rag_calls = evidence["rag_tool_calls"]',
                'assert (isinstance(rag_calls, int) and rag_calls > 0) or (not isinstance(rag_calls, int) and "search_knowledge" in rag_calls), evidence',
            ]
        )
    if "memory_isolation" in feature_names:
        lines.extend(
            [
                'assert int(evidence["memory_messages"]) >= 2, evidence',
                'assert evidence["cross_user_leak"] is False, evidence',
            ]
        )
    if "workflow_dag" in feature_names:
        lines.extend(
            [
                'assert evidence["workflow_status"] == "completed", evidence',
                'assert int(evidence["workflow_steps"]) >= 2, evidence',
            ]
        )
    if "team_sequential" in feature_names:
        lines.extend(
            [
                'assert evidence["team_strategy"] == "sequential", evidence',
                'assert len(str(evidence["team_output"])) > 0, evidence',
            ]
        )
    if "team_parallel" in feature_names:
        lines.extend(
            [
                'assert evidence["team_strategy"] == "parallel", evidence',
                'assert len(str(evidence["team_output"])) > 0, evidence',
            ]
        )
    if "orchestrator_router" in feature_names:
        lines.extend(
            [
                'assert evidence["orchestrator_strategy"] == "router", evidence',
                'assert len(str(evidence["route_output"])) > 0, evidence',
            ]
        )
    if "orchestrator_map_reduce" in feature_names:
        lines.extend(
            [
                'assert evidence["orchestrator_strategy"] == "map_reduce", evidence',
                'assert int(evidence["map_items"]) >= 3, evidence',
            ]
        )
    if "guardrails_pii" in feature_names:
        lines.append('assert "test@example.com" not in evidence["redacted_text"], evidence')
    if "tool_policy_approval" in feature_names:
        lines.extend(
            [
                'assert evidence["risky_action_executed"] is False, evidence',
                'assert "dangerous_delete" in evidence["denied_tools"], evidence',
            ]
        )
    if "typed_decorator_api" in feature_names:
        lines.extend(
            [
                'assert len(set(evidence["typed_tools"])) >= 2, evidence',
                'assert len(str(evidence["typed_output"])) > 0, evidence',
            ]
        )
    if "observability_trace" in feature_names:
        lines.extend(
            [
                'assert evidence["trace_id"], evidence',
                'captured_value = evidence["captured_messages"]',
                'captured_count = len(captured_value) if hasattr(captured_value, "__len__") and not isinstance(captured_value, (str, bytes, int, float)) else int(captured_value)',
                'assert captured_count >= 2, evidence',
                'assert float(evidence["total_cost"]) >= 0, evidence',
                'assert not re.search(r"\\bsk-[A-Za-z0-9_-]{12,}\\b", evidence["redacted_log"]), evidence',
            ]
        )
    return "\n".join(lines) + "\n"


def feature_requirements(feature_names: tuple[str, ...]) -> str:
    selected = [FEATURES[name] for name in feature_names]
    instructions = "\n".join(f"- {item.name}: {item.instructions}" for item in selected)
    evidence_keys = sorted({key for item in selected for key in item.evidence_keys})
    return f"""

Real LARGESTACK feature requirement:
- Create largestack_app.py with async def run_largestack_smoke() -> dict.
- The function must execute the selected LARGESTACK features, not only mention them.
- Use llm='deepseek/deepseek-chat' on Agents, but wrap generated project tests and smoke
  checks with TestModel/FunctionModel overrides so the generated project has no network
  side effects.
- Never define local mock/replacement classes named Agent, Team, Workflow, Orchestrator,
  TestModel, FunctionModel, or Tool. Import real APIs from largestack, largestack.testing,
  and largestack.decorators.
- Use Agent.override as a context manager: with agent.override(model=TestModel(...)):
  result = await agent.run(...). Calling agent.override(...) without a with block is invalid.
- The hidden gate wraps run_largestack_smoke() in block_model_requests(), so any accidental
  real provider/network call inside the generated project fails.
- Agent.run is async. Always call result = await agent.run(...), never result = agent.run(...).
- Agent.run returns an AgentResult object, not a dict. Use result.content, result.tool_calls_made,
  result.total_cost, result.trace_id. Do not use result.get(...).
- Valid core imports look like:
  from largestack import Agent, Team, Workflow, Orchestrator, tool, create_rag, create_guardrails
  from largestack.memory import create_memory
  from largestack.testing import TestModel, FunctionModel, capture_run_messages
- Correct Agent/TestModel pattern:
  agent = Agent(name="x", llm="deepseek/deepseek-chat", tools=[some_tool], cost_budget=0.1, max_turns=3)
  with agent.override(model=TestModel(call_tools=["some_tool"], custom_tool_args={{"some_tool": {{"query": "refund"}}}})):
      result = await agent.run("prompt")
  calls = result.tool_calls_made
- Correct map-reduce pattern:
  mapper = Agent(name="mapper", llm="deepseek/deepseek-chat", max_turns=1)
  reducer = Agent(name="reducer", llm="deepseek/deepseek-chat", max_turns=1)
  orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer)
  with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
      result = await orch.run({{"items": ["a", "b", "c"]}})
- Correct router pattern:
  classifier = Agent(name="classifier", llm="deepseek/deepseek-chat")
  specialist = Agent(name="billing", llm="deepseek/deepseek-chat")
  orch = Orchestrator(strategy="router", classifier=classifier, routes={{"billing": specialist}}, default_route="billing")
  with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
      route_result = await orch.run("route this")
  route_output = route_result.output
- Correct Team pattern:
  team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
  with agent_a.override(model=TestModel("a")), agent_b.override(model=TestModel("b")):
      team_result = await team.run("task")
  team_output = team_result.content
- Correct typed decorator pattern:
  from dataclasses import dataclass
  from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
  @dataclass
  class Deps:
      value: str = "demo"
  typed_agent = TypedAgent[Deps, str]("deepseek/deepseek-chat", deps_type=Deps, output_type=str, instructions="demo", name="typed", max_retries=1, cost_budget=0.1)
  # Then register @typed_agent.tool, @typed_agent.tool_plain, and @typed_agent.output_validator.
  with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
      typed_result = await typed_agent.run("prompt", deps=Deps())
  typed_tools = list(typed_agent.tools.keys())
  typed_output = typed_result.output
- Memory reference:
  memory = create_memory("buffer")
  await memory.add_message({{"role": "user", "content": "hello user1"}})
  messages = memory.get_messages()
- Workflow reference:
  wf = Workflow(name="pipe", mode="dag", cost_budget=0.2)
  wf.add_agent(agent_a)
  wf.add_agent(agent_b, deps=["agent_a"])
  result = await wf.run({{"task": "go"}})
  workflow_steps = len(result.steps)
- Guardrails reference:
  from types import SimpleNamespace
  guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
  response = SimpleNamespace(content="Email test@example.com")
  await guardrails.check_output(response)
  redacted_text = response.content
- Return exactly this shape: {{"status": "ok", "features": [...], "evidence": {{...}}}}.
- Include each selected feature name in the returned features list.
- Evidence keys that must be present: {", ".join(evidence_keys)}.
- Include at least one realistic fixture file under data/ or policy file under policies/.
- Include tests/test_largestack_features.py that runs run_largestack_smoke().
- No real API keys, no network imports, no destructive actions.

Selected feature contracts:
{instructions}
"""


def make_real_feature_specs() -> list[ProjectSpec]:
    base_specs = make_domain_specs()
    extra_requirements = {
        "mini_rag_assistant_api": (
            "\nMini-RAG answer contract: answer(query) must not require the full query string to "
            "appear verbatim in a document. Implement case-insensitive token/keyword overlap "
            "search, ignoring punctuation and weak question words such as what, why, how, does, "
            "the, a, an, is, are, before. Require at least two meaningful query-token overlaps; "
            "a single generic overlap such as policy is insufficient evidence. The query "
            "'duplicate payments require what?' must match the document 'Duplicate payments "
            "require approval before refund.' and return an answer containing approval plus "
            "citations containing refund_policy.md. Unsupported queries such as 'equity refresh "
            "policy', even when a document says only 'Some other policy.', must return "
            "Insufficient evidence. answer(query) must always return a dict with exactly the "
            "public fields answer: str and citations: list[str]; do not return a plain string, "
            "do not replace citations with status, and do not add a status-only contract. For "
            "insufficient evidence return {'answer': 'Insufficient evidence', 'citations': []}. "
            "Generated tests should clear the in-memory document store between independent "
            "cases. README.md is mandatory and must explain run/test usage.\n"
        ),
        "code_reviewer_fixer": (
            "\nCode-review safety contract: use safe placeholder samples, not real-looking "
            "passwords, tokens, or API keys. Detect hardcoded_secret for any ALL_CAPS variable "
            "assigned a quoted literal, and detect sql_string_formatting for SQL built with "
            "f-strings, %-formatting, .format(), or string concatenation. suggest_patch should "
            "move hardcoded values to os.environ. find_issues(source) must make direct membership "
            "checks work, for example 'hardcoded_secret' in find_issues(source), or return a list "
            "of issue dicts with a 'type' field. Generated tests and README must use only safe "
            "placeholder names like CONFIG_VALUE and demo_insecure_value; do not include strings "
            "matching sk-..., API_KEY, PASSWORD, TOKEN, or SECRET. README.md must be meaningful, "
            "at least 100 characters, and explain the offline security checks. For f-string SQL, "
            "walk every ast.JoinedStr node directly; do not only check ast.Expr, because real "
            "assignments parse as ast.Assign(value=ast.JoinedStr(...)).\n"
        ),
        "esign_document_approval_workflow": (
            "\nE-sign safety contract: send_decision(envelope_id) must never actually send or mark "
            "the envelope sent in this offline project. It must return executed False and preserve "
            "an audit trail entry showing approval is required.\n"
        ),
    }
    specs: list[ProjectSpec] = []
    for index, base in enumerate(base_specs):
        features = FEATURE_MATRIX[index]
        base_requirements = base.requirements
        base_acceptance = base.acceptance
        if base.name == "mini_rag_assistant_api":
            base_requirements = (
                "Create rag_assistant.py with add_document(filename, content) and answer(query). "
                "Answers must include citations and return Insufficient evidence when no document "
                "supports the answer. Implement token/keyword overlap search, not exact whole-query "
                "substring matching. Ignore punctuation and weak question words, and require at "
                "least two meaningful query-token overlaps; one generic token such as policy is "
                "not enough evidence. answer(query) must always return a dict with public fields "
                "'answer' and 'citations'. For insufficient evidence return "
                "{'answer': 'Insufficient evidence', 'citations': []}. Do not return a plain "
                "string and do not replace citations with a status field. If you keep an in-memory "
                "_documents store, tests must clear it between independent cases. Include README.md "
                "with at least 100 characters and run/test instructions."
            )
            base_acceptance = (
                "from rag_assistant import add_document, answer\n"
                "import rag_assistant\n"
                "if hasattr(rag_assistant, '_documents'):\n"
                "    rag_assistant._documents.clear()\n"
                "add_document('refund_policy.md','Duplicate payments require approval before refund.')\n"
                "r=answer('duplicate payments require what?')\n"
                "assert 'approval' in r['answer'].lower() and 'refund_policy.md' in r['citations']\n"
                "add_document('other_policy.md','Some other policy.')\n"
                "assert 'insufficient evidence' in answer('equity refresh policy')['answer'].lower()\n"
            )
        if base.name == "code_reviewer_fixer":
            base_requirements = (
                "Create code_reviewer.py with find_issues(source) and suggest_patch(source). "
                "Detect hardcoded_secret for ALL_CAPS quoted literals and sql_string_formatting "
                "for SQL built by f-string, %-formatting, .format(), or string concatenation. "
                "suggest_patch(source) must replace hardcoded literals with os.environ lookups. "
                "The easiest accepted find_issues return shape is dict[str, list[int]] or "
                "set/list[str] where membership checks for 'hardcoded_secret' and "
                "'sql_string_formatting' work directly. If returning list[dict], each dict must "
                "have type=<issue id>. Do not include real-looking API key/password/token/secret "
                "strings in any generated source, tests, README, or fixtures. For SQL f-strings, "
                "detect ast.JoinedStr anywhere in ast.walk(tree), including assignment values; "
                "do not limit f-string detection to ast.Expr. Include README.md with at least "
                "100 characters."
            )
            base_acceptance = (
                "from code_reviewer import find_issues, suggest_patch\n"
                "src=\"CONFIG_VALUE = 'demo_insecure_value'\\nquery = f\\\"select * from users where id={user_id}\\\"\"\n"
                "issues=find_issues(src)\n"
                "def _has_issue(items, name):\n"
                "    if isinstance(items, dict):\n"
                "        return name in items\n"
                "    if name in items:\n"
                "        return True\n"
                "    return any(isinstance(item, dict) and item.get('type') == name for item in items)\n"
                "assert _has_issue(issues, 'hardcoded_secret'), issues\n"
                "assert _has_issue(issues, 'sql_string_formatting'), issues\n"
                "assert 'os.environ' in suggest_patch(\"CONFIG_VALUE = 'demo_insecure_value'\")\n"
            )
        acceptance = (
            base_acceptance
            + "\n"
            + ast_acceptance_helpers()
            + make_feature_assertions(features)
        )
        specs.append(
            ProjectSpec(
                name=base.name,
                requirements=base_requirements + extra_requirements.get(base.name, "") + feature_requirements(features),
                acceptance=acceptance,
                required_files=["README.md", "largestack_app.py"],
                forbidden_actions=base.forbidden_actions,
                evidence_required=list(features),
                classification="DEEPSEEK-BUILT-LARGESTACK-FEATURE-PROJECT",
            )
        )
    bfsi_projects: list[tuple[str, str, str, tuple[str, ...]]] = [
        (
            "bfsi_loan_origination_maker_checker",
            (
                "Create loan_origination.py with assess_application(applicant) and "
                "create_approval_plan(applicant, assessment). assess_application must validate "
                "applicant_id, annual_income, monthly_debt, credit_score, kyc_status, and "
                "requested_amount. Compute debt_to_income = monthly_debt * 12 / annual_income. "
                "Return decision='eligible' only when kyc_status is verified, credit_score >= 700, "
                "debt_to_income <= 0.45, requested_amount <= annual_income * 4, and dpd_days is 0. "
                "Otherwise return decision='manual_review' with concrete reasons. "
                "create_approval_plan must never disburse funds; it returns executed False, "
                "approval_required True for manual_review or requested_amount >= 1000000, and "
                "maker_checker=['maker','checker']. Include README.md, pytest tests, and a "
                "policies/credit_policy.md fixture. Use stdlib only and no network calls."
            ),
            (
                "from loan_origination import assess_application, create_approval_plan\n"
                "app={'applicant_id':'A1','annual_income':900000,'monthly_debt':20000,"
                "'credit_score':735,'kyc_status':'verified','requested_amount':1800000,'dpd_days':0}\n"
                "assessment=assess_application(app)\n"
                "assert assessment['decision']=='eligible', assessment\n"
                "assert assessment['risk_band'] in {'low','medium'}, assessment\n"
                "plan=create_approval_plan({**app,'requested_amount':1500000}, assessment)\n"
                "assert plan['approval_required'] is True and plan['executed'] is False, plan\n"
                "assert plan['maker_checker']==['maker','checker'], plan\n"
                "bad=assess_application({**app,'kyc_status':'pending','credit_score':620})\n"
                "assert bad['decision']=='manual_review' and bad['reasons'], bad\n"
            ),
            ("workflow_dag", "tool_policy_approval", "guardrails_pii"),
        ),
        (
            "bfsi_aml_transaction_monitoring",
            (
                "Create aml_monitoring.py with screen_transaction(txn, customer, watchlist), "
                "draft_sar(txn, screening), and policy_answer(query, documents). "
                "screen_transaction must flag high risk for sanctions countries, amount spikes "
                "above 5x average monthly volume, high-risk keywords, or high-risk KYC profile. "
                "It must accept watchlist either as a dict with blocked_countries and "
                "high_risk_keywords lists, or as a list of strings/dicts. It must accept the "
                "transaction country from txn['country'] or txn['counterparty_country'], and "
                "the customer average volume from customer['average_monthly_volume'] or "
                "customer['avg_monthly_volume']. It must return keys risk_level, risk, "
                "requires_review, and reasons. "
                "draft_sar must never file externally; it returns filed False and approval_required "
                "True for high-risk screening and include requires_review True for high risk. "
                "policy_answer must accept documents as either a dict of filename->text or a list "
                "of document strings. It must return citations as a list of strings. When documents "
                "is a dict, citations must contain the exact filename string such as "
                "['aml_policy.md'], not dict objects. Use meaningful token-overlap retrieval with "
                "stopword filtering and return "
                "{'answer':'Insufficient evidence to answer.','citations':[]} for unrelated "
                "questions such as equity refresh policy. Include README.md, pytest tests, "
                "synthetic data CSV fixtures, and policies/aml_policy.md. Use stdlib "
                "only and no network/external filing calls."
            ),
            (
                "from aml_monitoring import screen_transaction, draft_sar, policy_answer\n"
                "watchlist={'blocked_countries':['IR','KP'],'high_risk_keywords':['crypto mixer','cash structuring']}\n"
                "txn={'txn_id':'T1','amount':1200000,'country':'IR','description':'crypto mixer payout','customer_id':'C1'}\n"
                "customer={'kyc_risk':'high','average_monthly_volume':100000}\n"
                "screen=screen_transaction(txn, customer, watchlist)\n"
                "assert screen['risk_level']=='high' and screen['requires_review'] is True, screen\n"
                "sar=draft_sar(txn, screen)\n"
                "assert sar['approval_required'] is True and sar['filed'] is False, sar\n"
                "docs={'aml_policy.md':'High risk sanctions or structuring cases require MLRO review before filing SAR.'}\n"
                "ans=policy_answer('when file sar for sanctions?', docs)\n"
                "assert 'MLRO' in ans['answer'] and 'aml_policy.md' in ans['citations'], ans\n"
                "assert 'insufficient evidence' in policy_answer('equity refresh policy?', docs)['answer'].lower()\n"
            ),
            ("orchestrator_router", "rag_citations", "observability_trace"),
        ),
    ]
    for name, requirements, acceptance, features in bfsi_projects:
        specs.append(
            ProjectSpec(
                name=name,
                requirements=requirements + feature_requirements(features),
                acceptance=acceptance + "\n" + ast_acceptance_helpers() + make_feature_assertions(features),
                required_files=["README.md", "largestack_app.py"],
                forbidden_actions=["send_email", "refund_payment", "delete_file", "publish_social", "write_production", "disburse_funds", "file_sar"],
                evidence_required=list(features),
                classification="DEEPSEEK-BUILT-LARGESTACK-BFSI-FEATURE-PROJECT",
            )
        )
    return specs


def make_b2b_agentic_specs() -> list[ProjectSpec]:
    """Return market-focused B2B agentic product specs.

    These are intentionally separate from the original 24/26 feature suite.
    The domain contract proves each generated product has useful local business
    logic, while the appended feature contract proves it also executes real
    LARGESTACK agent/team/workflow/RAG/memory/guardrail/observability APIs.
    """

    common_forbidden = [
        "send_email",
        "refund_payment",
        "delete_file",
        "publish_social",
        "write_production",
        "charge_card",
        "wire_transfer",
        "submit_regulatory_filing",
        "external_api_call",
    ]

    def spec(name: str, requirements: str, acceptance: str, features: tuple[str, ...], *, extra_forbidden: list[str] | None = None) -> ProjectSpec:
        contract = (
            "\nPublic usage contract that the generated project must pass exactly:\n"
            "```python\n"
            f"{acceptance.strip()}\n"
            "```\n"
        )
        return ProjectSpec(
            name=name,
            requirements=(
                requirements
                + contract
                + "\nBuild a real, runnable B2B agentic product slice: deterministic business "
                "logic module, pytest tests, README.md with run/test instructions, and at least "
                "one realistic fixture under data/ or policy file under policies/. Use Python "
                "standard library only for product logic. Do not include secrets, network calls, "
                "external side effects, fake production writes, payments, or real notifications. "
                "Risky actions must return approval_required True and executed False."
                + feature_requirements(features)
            ),
            acceptance=acceptance + "\n" + ast_acceptance_helpers() + make_feature_assertions(features),
            required_files=["README.md", "largestack_app.py"],
            forbidden_actions=common_forbidden + list(extra_forbidden or []),
            evidence_required=list(features),
            classification="DEEPSEEK-BUILT-LARGESTACK-B2B-AGENTIC-PROJECT",
        )

    projects: list[tuple[str, str, str, list[str] | None]] = [
        (
            "b2b_sales_forecast_copilot",
            "Create sales_forecast.py with add_opportunity, forecast_quarter, and explain_pipeline_risk. Store opportunities in memory, compute weighted pipeline by amount * probability, track commit pipeline, coverage_ratio against target, and return concrete risks when coverage is below 3x target.",
            "from sales_forecast import add_opportunity, forecast_quarter, explain_pipeline_risk\n"
            "add_opportunity('O1', amount=100000, stage='proposal', probability=0.5, close_quarter='2026Q2', owner='A')\n"
            "add_opportunity('O2', amount=50000, stage='commit', probability=0.9, close_quarter='2026Q2', owner='A')\n"
            "forecast=forecast_quarter('2026Q2', target=100000)\n"
            "assert abs(forecast['weighted_pipeline'] - 95000) < 0.01, forecast\n"
            "assert forecast['commit_pipeline'] == 50000, forecast\n"
            "risk=explain_pipeline_risk(forecast)\n"
            "assert isinstance(risk['risks'], list) and 'coverage_ratio' in risk, risk\n",
            None,
        ),
        (
            "b2b_revenue_ops_pipeline_agent",
            "Create revops_pipeline.py with normalize_lead, route_account, and build_sla_plan. Normalize domains and company names, route enterprise leads to account executive, SMB leads to inbound, and stale high-value leads to escalation.",
            "from revops_pipeline import normalize_lead, route_account, build_sla_plan\n"
            "lead=normalize_lead({'email':'Buyer@ACME.COM','company':'  Acme Inc. ','employees':1500,'source':'web','last_touch_days':5})\n"
            "assert lead['domain']=='acme.com' and lead['company']=='Acme Inc.', lead\n"
            "route=route_account(lead)\n"
            "assert route['queue']=='enterprise_ae' and route['priority'] in {'high','urgent'}, route\n"
            "sla=build_sla_plan({**lead,'last_touch_days':10})\n"
            "assert sla['escalate'] is True and sla['due_hours'] <= 24, sla\n",
            None,
        ),
        (
            "b2b_customer_success_health_monitor",
            "Create customer_health.py with compute_health_score and generate_playbook. Combine usage, support tickets, NPS, renewal days, and executive sponsor presence into a 0-100 score and actionable playbook. Use deterministic scoring that subtracts risk penalties from 100: low usage, P1 tickets, low NPS, near renewal, and missing executive sponsor must lower the score. Risk levels should be high below 60, medium from 60 to 84, and low at 85+. Generated tests must not expect a perfect 100 score for an account with imperfect signals such as NPS below 9, usage below 90, or missing sponsor. generate_playbook must add owner actions that explicitly mention the signal names when relevant: NPS for low nps, usage for low usage, P1/support tickets for open_p1_tickets, renewal for near renewal, and executive sponsor for missing sponsor.",
            "from customer_health import compute_health_score, generate_playbook\n"
            "account={'usage_percent':35,'open_p1_tickets':2,'nps':4,'renewal_days':45,'executive_sponsor':False}\n"
            "health=compute_health_score(account)\n"
            "assert 0 <= health['score'] <= 100 and health['risk_level']=='high', health\n"
            "plan=generate_playbook(account, health)\n"
            "assert plan['owner_actions'] and plan['approval_required'] is False, plan\n",
            None,
        ),
        (
            "b2b_vendor_risk_assessment_agent",
            "Create vendor_risk.py with assess_vendor, approval_requirements, and policy_answer. Score security, financial, privacy, country, and criticality risk. Policy answers must cite supporting docs and return insufficient evidence when unsupported.",
            "from vendor_risk import assess_vendor, approval_requirements, policy_answer\n"
            "vendor={'name':'DataCo','soc2':False,'dpdp_ready':False,'country':'US','criticality':'high','financial_score':45}\n"
            "risk=assess_vendor(vendor)\n"
            "assert risk['risk_level']=='high' and len(risk['reasons']) >= 2, risk\n"
            "approval=approval_requirements(risk)\n"
            "assert approval['approval_required'] is True and approval['executed'] is False, approval\n"
            "docs={'vendor_policy.md':'High criticality vendors without SOC2 require security committee approval.'}\n"
            "ans=policy_answer('when security committee approval vendor?', docs)\n"
            "assert 'security committee' in ans['answer'].lower() and 'vendor_policy.md' in ans['citations'], ans\n"
            "assert 'insufficient evidence' in policy_answer('office snacks policy', docs)['answer'].lower()\n",
            ["approve_vendor"],
        ),
        (
            "b2b_procurement_contract_triage",
            "Create procurement_triage.py with extract_obligations, flag_contract_risks, and approval_route. Detect auto-renewal, liability cap absence, DPA absence, payment terms, and non-standard governing law from contract text. Negative phrases such as 'No liability cap is stated', 'without liability cap', 'liability cap absent', and 'DPA not attached' must be treated as missing controls, not as evidence that the controls exist.",
            "from procurement_triage import extract_obligations, flag_contract_risks, approval_route\n"
            "text='Agreement auto-renews annually. Payment terms Net 15. No liability cap is stated. DPA not attached. Governing law Mars.'\n"
            "ob=extract_obligations(text)\n"
            "assert ob['payment_terms']=='Net 15' and ob['auto_renewal'] is True, ob\n"
            "risks=flag_contract_risks(text)\n"
            "assert 'missing_liability_cap' in risks and 'missing_dpa' in risks, risks\n"
            "route=approval_route(risks)\n"
            "assert route['approval_required'] is True and route['executed'] is False, route\n",
            ["sign_contract"],
        ),
        (
            "b2b_invoice_reconciliation_agent",
            "Create invoice_reconciliation.py with reconcile_invoice and payment_decision. Match invoice lines against PO and receipts, calculate variance, flag missing receipt and overbilling, and never release payment without approval.",
            "from invoice_reconciliation import reconcile_invoice, payment_decision\n"
            "po={'po_id':'PO1','lines':[{'sku':'A','qty':10,'unit_price':100}]}\n"
            "invoice={'invoice_id':'I1','po_id':'PO1','lines':[{'sku':'A','qty':12,'unit_price':100}]}\n"
            "receipts=[{'sku':'A','qty':10}]\n"
            "rec=reconcile_invoice(po, invoice, receipts)\n"
            "assert rec['status']=='mismatch' and 'quantity_variance' in rec['issues'], rec\n"
            "decision=payment_decision(rec)\n"
            "assert decision['approval_required'] is True and decision['executed'] is False, decision\n",
            ["release_payment"],
        ),
        (
            "b2b_accounts_receivable_collections_agent",
            "Create ar_collections.py with prioritize_accounts and draft_collection_plan. Rank overdue invoices by days past due, amount, strategic tier, dispute status, and customer risk. Draft plans must not send messages.",
            "from ar_collections import prioritize_accounts, draft_collection_plan\n"
            "accounts=[{'account':'A','amount_due':50000,'days_past_due':45,'tier':'strategic','disputed':False},{'account':'B','amount_due':5000,'days_past_due':5,'tier':'standard','disputed':False}]\n"
            "ranked=prioritize_accounts(accounts)\n"
            "assert ranked[0]['account']=='A' and ranked[0]['priority_score'] > ranked[1]['priority_score'], ranked\n"
            "plan=draft_collection_plan(ranked[0])\n"
            "assert plan['send_executed'] is False and plan['approval_required'] is True, plan\n",
            ["send_collection_email"],
        ),
        (
            "b2b_compliance_evidence_mapper",
            "Create compliance_mapper.py with map_control_to_evidence and gap_report. Map controls to evidence files by keywords, mark missing evidence, and produce remediation actions with owners.",
            "from compliance_mapper import map_control_to_evidence, gap_report\n"
            "controls=[{'id':'AC-1','text':'Access reviews must be quarterly'},{'id':'IR-1','text':'Incident response tabletop annually'}]\n"
            "evidence={'access_review_q1.pdf':'Quarterly access review completed','backup.txt':'Backups tested'}\n"
            "mapping=map_control_to_evidence(controls, evidence)\n"
            "assert mapping['AC-1']['status']=='mapped' and mapping['IR-1']['status']=='missing', mapping\n"
            "gap=gap_report(mapping)\n"
            "assert gap['missing_count']==1 and gap['actions'][0]['control_id']=='IR-1', gap\n",
            None,
        ),
        (
            "b2b_incident_response_war_room",
            "Create incident_war_room.py with triage_incident, response_plan, and approval_gate. Classify severity from data exposure, service impact, and customer count; create timed response steps and maker-checker approval for external notices.",
            "from incident_war_room import triage_incident, response_plan, approval_gate\n"
            "incident={'data_exposed':True,'customers_affected':1200,'service_down_minutes':30,'source':'prod alert'}\n"
            "triage=triage_incident(incident)\n"
            "assert triage['severity'] in {'sev1','critical'} and triage['privacy_review_required'] is True, triage\n"
            "plan=response_plan(triage)\n"
            "assert len(plan['steps']) >= 3 and plan['minutes_to_first_update'] <= 60, plan\n"
            "gate=approval_gate('customer_notice', triage)\n"
            "assert gate['approval_required'] is True and gate['executed'] is False, gate\n",
            ["send_customer_notice"],
        ),
        (
            "b2b_enterprise_knowledge_support_copilot",
            "Create support_copilot.py with add_article, answer_question, and escalation_decision. Use citation-backed retrieval, insufficient evidence fallback, and escalate security/payment requests. Do not preload product knowledge at import time; answer_question must only use articles added through add_article in the current process. Implement token overlap retrieval with weak-word filtering and require at least two meaningful overlapping terms, so unrelated queries like 'billing tax id?' return Insufficient evidence when only an SSO article was added. Tests must clear any in-memory article store between cases.",
            "from support_copilot import add_article, answer_question, escalation_decision\n"
            "add_article('sso.md','SAML SSO setup requires metadata upload and admin approval.')\n"
            "ans=answer_question('how setup saml sso metadata?')\n"
            "assert 'metadata' in ans['answer'].lower() and 'sso.md' in ans['citations'], ans\n"
            "assert 'insufficient evidence' in answer_question('billing tax id?')['answer'].lower()\n"
            "esc=escalation_decision('delete all data now')\n"
            "assert esc['approval_required'] is True and esc['reason'], esc\n",
            ["delete_customer_data"],
        ),
        (
            "b2b_field_service_dispatch_optimizer",
            "Create field_dispatch.py with schedule_jobs and explain_assignment. Assign technicians by skill, region, priority, and available hours; avoid overbooking and explain skipped jobs.",
            "from field_dispatch import schedule_jobs, explain_assignment\n"
            "techs=[{'id':'T1','skills':['hvac'],'region':'north','available_hours':4},{'id':'T2','skills':['network'],'region':'south','available_hours':2}]\n"
            "jobs=[{'id':'J1','skill':'hvac','region':'north','duration_hours':3,'priority':'high'},{'id':'J2','skill':'hvac','region':'north','duration_hours':3,'priority':'low'}]\n"
            "schedule=schedule_jobs(techs, jobs)\n"
            "assert schedule['assignments'][0]['job_id']=='J1' and schedule['unassigned'], schedule\n"
            "explain=explain_assignment(schedule)\n"
            "assert 'capacity' in explain.lower() or 'available' in explain.lower(), explain\n",
            None,
        ),
        (
            "b2b_qa_regression_planner_agent",
            "Create qa_regression_planner.py with build_test_plan and risk_matrix. Convert changed files and incidents into test areas, smoke/regression priority, and owners.",
            "from qa_regression_planner import build_test_plan, risk_matrix\n"
            "changes=['billing/payments.py','auth/sso.py']\n"
            "incidents=[{'area':'billing','severity':'high'}]\n"
            "plan=build_test_plan(changes, incidents)\n"
            "assert 'billing' in plan['areas'] and plan['priority']=='high', plan\n"
            "matrix=risk_matrix(plan)\n"
            "assert matrix['billing']['risk'] in {'high','critical'}, matrix\n",
            None,
        ),
        (
            "b2b_cloud_cost_anomaly_assistant",
            "Create cloud_cost.py with detect_anomalies and remediation_plan. Detect spend spikes against baseline, explain service drivers, and require approval before shutdown/resizing actions.",
            "from cloud_cost import detect_anomalies, remediation_plan\n"
            "usage=[{'service':'compute','daily_cost':100,'baseline':40},{'service':'storage','daily_cost':20,'baseline':22}]\n"
            "anoms=detect_anomalies(usage, threshold=2.0)\n"
            "assert anoms[0]['service']=='compute' and anoms[0]['ratio'] >= 2.5, anoms\n"
            "plan=remediation_plan(anoms)\n"
            "assert plan['approval_required'] is True and plan['executed'] is False, plan\n",
            ["shutdown_instance", "resize_cluster"],
        ),
        (
            "b2b_sales_call_coaching_agent",
            "Create sales_call_coach.py with score_call and coaching_plan. Score discovery, objection handling, pricing risk, next step clarity, and compliance disclaimer usage. Use a transparent 100-point rubric: subtract 20 each for missing discovery, missing objection handling, risky guarantee/pricing promise, missing next step, and missing compliance disclaimer. Treat phrases like 'next step', 'follow up', 'schedule', 'send proposal', or 'meeting booked' as next-step evidence only when they are not negated. Phrases such as 'no next step', 'without next step', or 'missing next step' must count as missing next step even though they contain the words next step. Treat discovery as present only when the rep asks or records discovery questions/needs such as 'what are your needs', 'pain point', 'business goal', or 'success criteria'; a bare sentence like 'Customer needs SOC2' is not enough by itself. Empty transcripts should trigger all five risks. When there are no risk flags, coaching_plan must start with a positive 'Great job' action; when risk_flags is non-empty, coaching_plan must produce targeted improvement actions and must not be tested as perfect. Generated tests must use unambiguous transcripts only: a perfect transcript must explicitly include discovery question, objection handling, safe non-guarantee pricing language, a concrete next step, and compliance disclaimer; a risky transcript should assert relative conditions such as total_score < 80 and presence of risk flags, not brittle exact scores unless every risk is explicitly controlled.",
            "from sales_call_coach import score_call, coaching_plan\n"
            "transcript='Customer needs SOC2. Rep discussed timeline but no next step and promised guaranteed ROI.'\n"
            "score=score_call(transcript)\n"
            "assert score['risk_flags'] and score['total_score'] < 80, score\n"
            "plan=coaching_plan(score)\n"
            "assert 'next step' in ' '.join(plan['actions']).lower(), plan\n",
            None,
        ),
        (
            "b2b_renewal_churn_forecaster",
            "Create renewal_risk.py with assess_renewal_risk and save_playbook. Score risk from usage decline, tickets, champion loss, renewal date, and contract value.",
            "from renewal_risk import assess_renewal_risk, save_playbook\n"
            "acct={'usage_trend':-45,'open_tickets':8,'champion_left':True,'renewal_days':30,'arr':250000}\n"
            "risk=assess_renewal_risk(acct)\n"
            "assert risk['risk_level']=='high' and risk['score'] >= 70, risk\n"
            "play=save_playbook(acct, risk)\n"
            "assert play['executed'] is False and len(play['actions']) >= 3, play\n",
            ["auto_discount"],
        ),
        (
            "b2b_partner_onboarding_approval",
            "Create partner_onboarding.py with evaluate_partner and approval_packet. Validate compliance attestations, region, revenue tier, support readiness, and conflicts. Approval packet must be maker-checker gated.",
            "from partner_onboarding import evaluate_partner, approval_packet\n"
            "partner={'name':'NorthStar','region':'EU','dpdp_ready':True,'conflict':False,'support_certified':False,'revenue_tier':'gold'}\n"
            "eval=evaluate_partner(partner)\n"
            "assert eval['status'] in {'conditional','manual_review'} and eval['gaps'], eval\n"
            "packet=approval_packet(partner, eval)\n"
            "assert packet['approval_required'] is True and packet['executed'] is False and packet['maker_checker'], packet\n",
            ["activate_partner"],
        ),
        (
            "b2b_supply_chain_delay_predictor",
            "Create supply_chain_delay.py with predict_delay and mitigation_plan. Estimate delay risk from supplier reliability, port congestion, inventory cover, demand spike, and criticality.",
            "from supply_chain_delay import predict_delay, mitigation_plan\n"
            "shipment={'supplier_score':55,'port_congestion':'high','inventory_days':5,'demand_spike':True,'criticality':'high'}\n"
            "risk=predict_delay(shipment)\n"
            "assert risk['risk_level']=='high' and risk['delay_days_estimate'] >= 7, risk\n"
            "plan=mitigation_plan(shipment, risk)\n"
            "assert plan['actions'] and plan['approval_required'] is True, plan\n",
            ["place_emergency_order"],
        ),
        (
            "b2b_data_privacy_dsr_automation",
            "Create dsr_automation.py with classify_request, fulfillment_plan, and redaction_check. Handle access/export/delete requests, verify identity, require approval for deletion, and redact PII in logs.",
            "from dsr_automation import classify_request, fulfillment_plan, redaction_check\n"
            "req={'text':'Please delete my profile and export invoices','identity_verified':False,'email':'person@example.com'}\n"
            "cls=classify_request(req)\n"
            "assert set(cls['request_types']) == {'delete','export'}, cls\n"
            "plan=fulfillment_plan(req, cls)\n"
            "assert plan['approval_required'] is True and plan['executed'] is False, plan\n"
            "assert 'person@example.com' not in redaction_check('email person@example.com'), 'PII not redacted'\n",
            ["delete_profile"],
        ),
        (
            "b2b_audit_control_testing_assistant",
            "Create audit_testing.py with sample_transactions and evaluate_control. Deterministically sample by risk, test control evidence, and summarize exceptions.",
            "from audit_testing import sample_transactions, evaluate_control\n"
            "txns=[{'id':'1','amount':1000,'approved':True},{'id':'2','amount':90000,'approved':False},{'id':'3','amount':50000,'approved':True}]\n"
            "sample=sample_transactions(txns, limit=2)\n"
            "assert sample[0]['id']=='2', sample\n"
            "result=evaluate_control(sample, rule='large_transactions_require_approval')\n"
            "assert result['exceptions'] and result['status']=='fail', result\n",
            None,
        ),
        (
            "b2b_enterprise_rfp_response_builder",
            "Create rfp_response.py with ingest_qa, draft_response, and compliance_gap. Draft answers must be citation-backed and return insufficient evidence for unsupported claims.",
            "from rfp_response import ingest_qa, draft_response, compliance_gap\n"
            "ingest_qa('security.md','We support SSO, audit logs, and data export. SOC2 report available under NDA.')\n"
            "resp=draft_response('Do you support audit logs and SSO?')\n"
            "assert 'audit logs' in resp['answer'].lower() and resp['citations'], resp\n"
            "missing=draft_response('Do you support on-prem airgap?')\n"
            "assert 'insufficient evidence' in missing['answer'].lower(), missing\n"
            "gap=compliance_gap(['SOC2','HIPAA'], available=['SOC2'])\n"
            "assert gap['missing']==['HIPAA'], gap\n",
            None,
        ),
        (
            "b2b_product_feedback_intelligence",
            "Create feedback_intelligence.py with cluster_feedback and roadmap_signals. Cluster feedback by themes, count revenue impact, sentiment, and produce evidence-backed roadmap signals.",
            "from feedback_intelligence import cluster_feedback, roadmap_signals\n"
            "items=[{'text':'Need SSO for enterprise deal','arr':100000},{'text':'SSO setup is confusing','arr':50000},{'text':'Dark mode please','arr':1000}]\n"
            "clusters=cluster_feedback(items)\n"
            "assert clusters['sso']['count']==2 and clusters['sso']['arr'] == 150000, clusters\n"
            "signals=roadmap_signals(clusters)\n"
            "assert signals[0]['theme']=='sso' and signals[0]['priority'] in {'high','critical'}, signals\n",
            None,
        ),
        (
            "b2b_workforce_capacity_planner",
            "Create workforce_capacity.py with capacity_plan and hiring_recommendation. Compare demand hours to available capacity by role, flag overload, and recommend staffing without protected-class logic.",
            "from workforce_capacity import capacity_plan, hiring_recommendation\n"
            "demand=[{'role':'support','hours':220},{'role':'engineering','hours':120}]\n"
            "capacity=[{'role':'support','fte':1,'hours_per_fte':160},{'role':'engineering','fte':1,'hours_per_fte':160}]\n"
            "plan=capacity_plan(demand, capacity)\n"
            "assert plan['support']['gap_hours']==60 and plan['support']['status']=='overloaded', plan\n"
            "rec=hiring_recommendation(plan)\n"
            "assert rec['roles'][0]['role']=='support' and 'protected' not in str(rec).lower(), rec\n",
            None,
        ),
        (
            "b2b_contract_obligation_tracker",
            "Create obligation_tracker.py with extract_obligations, due_soon, and escalation_plan. Track obligation owner, due date, renewal date, audit evidence, and escalation for overdue/high-risk obligations.",
            "from obligation_tracker import extract_obligations, due_soon, escalation_plan\n"
            "text='Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'\n"
            "items=extract_obligations(text)\n"
            "assert any(i['type']=='soc2_report' for i in items), items\n"
            "soon=due_soon(items, today='2026-05-12', days=10)\n"
            "assert soon and soon[0]['owner']=='security', soon\n"
            "esc=escalation_plan(soon)\n"
            "assert esc['approval_required'] is False and esc['actions'], esc\n",
            None,
        ),
        (
            "b2b_msp_ticket_router_sla_agent",
            "Create msp_ticket_router.py with route_ticket, sla_breach_risk, and handoff_plan. Route by customer tier, severity, system, and region; calculate SLA breach risk; produce safe handoff without external notification.",
            "from msp_ticket_router import route_ticket, sla_breach_risk, handoff_plan\n"
            "ticket={'customer_tier':'platinum','severity':'p1','system':'payments','region':'apac','age_minutes':50}\n"
            "route=route_ticket(ticket)\n"
            "assert route['queue']=='payments_p1' and route['priority']=='urgent', route\n"
            "risk=sla_breach_risk(ticket, sla_minutes=60)\n"
            "assert risk['breach_risk'] in {'high','critical'} and risk['minutes_remaining']==10, risk\n"
            "handoff=handoff_plan(ticket, route, risk)\n"
            "assert handoff['notify_executed'] is False and handoff['approval_required'] is True, handoff\n",
            ["send_pagerduty"],
        ),
    ]

    specs: list[ProjectSpec] = []
    for index, (name, requirements, acceptance, forbidden) in enumerate(projects):
        features = FEATURE_MATRIX[index % 24]
        specs.append(spec(name, requirements, acceptance, features, extra_forbidden=forbidden))
    return specs


def select_specs_for_suite(suite: str) -> tuple[list[ProjectSpec], int, float, str]:
    if suite == "features":
        return make_real_feature_specs(), PROJECT_MIN_SCORE, SUITE_MIN_AVERAGE, "real-feature"
    if suite == "b2b":
        return make_b2b_agentic_specs(), B2B_PROJECT_MIN_SCORE, B2B_SUITE_MIN_AVERAGE, "b2b-agentic"
    if suite == "all":
        return (
            make_real_feature_specs() + make_b2b_agentic_specs(),
            B2B_PROJECT_MIN_SCORE,
            B2B_SUITE_MIN_AVERAGE,
            "combined-real-feature-and-b2b-agentic",
        )
    raise ValueError(f"unknown suite: {suite}")


def parse_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    for candidate in (text, match.group(0) if match else ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def source_feature_check(project_path: Path, features: tuple[str, ...]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    app = project_path / "largestack_app.py"
    if not app.exists():
        return False, ["missing largestack_app.py"]
    src = app.read_text(encoding="utf-8", errors="ignore")
    try:
        import ast

        tree = ast.parse(src)
        calls: set[str] = set()
        names: set[str] = set()
        attrs: set[str] = set()
        imports: set[str] = set()
        class_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_names.add(node.name)
            if isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
                for alias in node.names:
                    names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                attrs.add(node.attr)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
                    attrs.add(node.func.attr)
                elif isinstance(node.func, ast.Subscript):
                    base = node.func.value
                    if isinstance(base, ast.Name):
                        calls.add(base.id)
                    elif isinstance(base, ast.Attribute):
                        calls.add(base.attr)
                        attrs.add(base.attr)
    except SyntaxError as exc:
        return False, [f"largestack_app.py syntax error: {exc}"]
    for forbidden in {"Agent", "Team", "Workflow", "Orchestrator", "TestModel", "FunctionModel", "Tool"}:
        if forbidden in class_names:
            missing.append(f"local mock/replacement class is forbidden: {forbidden}")
    if not any(m == "largestack" or m.startswith("largestack.") for m in imports):
        missing.append("missing largestack import")
    for feature in features:
        contract = FEATURES[feature]
        for call in contract.calls:
            if call not in calls:
                missing.append(f"{feature}: missing call {call}")
        for name in contract.names:
            if name not in names:
                missing.append(f"{feature}: missing name {name}")
        for attr in contract.attrs:
            if attr not in attrs:
                missing.append(f"{feature}: missing attr {attr}")
        for substring in contract.substrings:
            if substring not in src:
                missing.append(f"{feature}: missing substring {substring}")
    return not missing, missing


async def live_deepseek_smoke(outdir: Path) -> bool:
    progress("live DeepSeek smoke start")
    agent = Agent(
        name="real-feature-live-smoke",
        instructions="Reply with exactly LARGESTACK_FEATURE_LIVE_OK and no extra words.",
        llm=MODEL,
        memory=NoOpMemory(),
        cost_budget=0.05,
        max_turns=2,
    )
    try:
        result = await agent.run("health check")
        content = str(getattr(result, "content", ""))
        data = {
            "passed": "LARGESTACK_FEATURE_LIVE_OK" in content,
            "content": content[:200],
            "trace_id": getattr(result, "trace_id", ""),
            "tokens": getattr(result, "total_tokens", 0),
            "cost": getattr(result, "total_cost", 0.0),
        }
    except Exception as exc:
        data = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    write_json(outdir / "live_deepseek_smoke.json", data)
    progress(f"live DeepSeek smoke done passed={data['passed']}")
    return bool(data["passed"])


async def review_project(
    reviewer: Agent,
    spec: ProjectSpec,
    report: BuildReport,
    features: tuple[str, ...],
    deterministic_passed: bool,
) -> ReviewerOutcome:
    project_path = Path(report.project_path)
    snapshot_parts: list[str] = []
    for file in sorted(project_path.rglob("*"))[:60]:
        if file.is_file() and "__pycache__" not in file.parts and file.stat().st_size < 30_000:
            try:
                snapshot_parts.append(f"--- {file.relative_to(project_path)} ---\n{file.read_text()[:5000]}")
            except UnicodeDecodeError:
                continue
    prompt = f"""
Strictly review this DeepSeek-generated LARGESTACK feature project.

Project: {spec.name}
Required LARGESTACK features: {", ".join(features)}

Validation evidence:
- compile={report.validation.compile_passed}
- pytest={report.validation.pytest_passed}
- hidden_acceptance={report.validation.acceptance_passed}
- deterministic_passed={deterministic_passed}
- failed_checks={report.validation.failed_checks}
- generated_files={report.generated_files}

Important:
- DeepSeek was used to generate this project through LARGESTACK.
- The generated project itself must avoid network side effects, so TestModel/FunctionModel
  overrides are the correct way to run internal Largestack feature smoke tests.
- Do not punish use of TestModel inside generated project tests.

Files:
{chr(10).join(snapshot_parts)[:26000]}

Return ONLY JSON:
{{"score": 0-100, "pass": true/false, "notes": "short", "critical_blocker": ""}}

Rules:
- If compile, pytest, hidden acceptance, or deterministic_passed is false, pass=false.
- If hidden acceptance is false, score must be below 80.
- If the project does not actually import/use Largestack APIs, pass=false.
- If all checks pass and feature usage is real, score should be 90-100.
"""
    try:
        result = await reviewer.run(prompt, timeout=120, temperature=0.0, max_tokens=700)
    except Exception as exc:
        return ReviewerOutcome(notes=f"reviewer error: {type(exc).__name__}: {exc}")
    data = parse_json_object(str(getattr(result, "content", "")))
    if not data:
        return ReviewerOutcome(notes="reviewer did not return valid JSON")
    score = int(max(0, min(100, data.get("score", 0))))
    blocker = str(data.get("critical_blocker", ""))[:500]
    passed = bool(data.get("pass", False)) and not blocker and score >= PROJECT_MIN_SCORE
    return ReviewerOutcome(
        score=score,
        passed=passed,
        json_valid=True,
        notes=redact(str(data.get("notes", ""))[:1000]),
        critical_blocker=redact(blocker),
    )


def score_project(
    report: BuildReport,
    *,
    security_ok: bool,
    readme_ok: bool,
    source_ok: bool,
    fixture_ok: bool,
    reviewer: ReviewerOutcome,
) -> int:
    score = 0
    score += 20 if report.validation.acceptance_passed else 0
    score += 20 if report.validation.pytest_passed else 0
    score += 15 if source_ok else 0
    score += 15 if security_ok else 0
    score += 10 if report.validation.compile_passed else 0
    score += 10 if readme_ok else 0
    score += 5 if fixture_ok else 0
    score += 5 if report.trace_ids and report.tokens > 0 and not report.budget_exceeded else 0
    if reviewer.json_valid:
        score = round((score * 0.85) + (reviewer.score * 0.15))
    if not report.validation.acceptance_passed:
        score = min(score, 79)
    if not report.validation.pytest_passed:
        score = min(score, 69)
    return int(score)


async def run_suite(
    outdir: Path,
    project_limit: int | None,
    project_start: int,
    *,
    specs: list[ProjectSpec] | None = None,
    project_min_score: int = PROJECT_MIN_SCORE,
) -> list[FeatureProjectCertification]:
    specs = list(specs) if specs is not None else make_real_feature_specs()
    if project_start > 1:
        specs = specs[project_start - 1 :]
    if project_limit:
        specs = specs[:project_limit]
    projects_dir = outdir / "projects"
    builder_agent = Agent(
        name="real-feature-builder",
        instructions=(
            "Generate correct, runnable, concise Python projects. The hidden acceptance contract "
            "is authoritative. Return valid JSON only."
        ),
        llm=MODEL,
        memory=NoOpMemory(),
        cost_budget=float(os.environ.get("LARGESTACK_REAL_FEATURE_BUILDER_BUDGET", "30")),
        max_turns=8,
    )
    reviewer_agent = Agent(
        name="real-feature-reviewer",
        instructions="Strictly review generated LARGESTACK projects. Return JSON only.",
        llm=MODEL,
        memory=NoOpMemory(),
        cost_budget=float(os.environ.get("LARGESTACK_REAL_FEATURE_REVIEWER_BUDGET", "12")),
        max_turns=3,
    )
    builder = AutonomousProjectBuilder(
        builder_agent,
        BuilderBudget(
            max_attempts=int(os.environ.get("LARGESTACK_REAL_FEATURE_MAX_ATTEMPTS", "5")),
            max_tokens=int(os.environ.get("LARGESTACK_REAL_FEATURE_MAX_TOKENS_PER_PROJECT", "450000")),
            max_seconds=float(os.environ.get("LARGESTACK_REAL_FEATURE_MAX_SECONDS_PER_PROJECT", "1200")),
            cost_budget=float(os.environ.get("LARGESTACK_REAL_FEATURE_PROJECT_BUDGET", "3")),
        ),
    )

    results: list[FeatureProjectCertification] = []
    for absolute_index, spec in enumerate(specs, start=project_start):
        features = tuple(spec.evidence_required)
        slug = f"{absolute_index:02d}_{spec.name}"
        project_path = projects_dir / slug
        progress(f"project start: {slug} features={','.join(features)}")
        report = await builder.build(spec, project_path)
        security_ok, security_issues = scan_project_security(project_path)
        readme_ok = project_has_readme(project_path)
        source_ok, source_issues = source_feature_check(project_path, features)
        fixture_ok = (project_path / "data").exists() or (project_path / "policies").exists()
        deterministic_passed = report.passed and security_ok and readme_ok and source_ok and fixture_ok
        reviewer = await review_project(reviewer_agent, spec, report, features, deterministic_passed)
        final_score = score_project(
            report,
            security_ok=security_ok,
            readme_ok=readme_ok,
            source_ok=source_ok,
            fixture_ok=fixture_ok,
            reviewer=reviewer,
        )
        failed_checks = list(report.validation.failed_checks)
        failed_checks.extend(security_issues)
        failed_checks.extend(source_issues)
        if not readme_ok:
            failed_checks.append("missing_or_thin_readme")
        if not fixture_ok:
            failed_checks.append("missing_data_or_policy_fixture")
        if not reviewer.json_valid:
            failed_checks.append("reviewer_json_invalid")
        elif not reviewer.passed:
            failed_checks.append("reviewer_not_passed")
        if final_score < project_min_score:
            failed_checks.append(f"score_below_{project_min_score}")
        passed = deterministic_passed and reviewer.passed and final_score >= project_min_score and not failed_checks
        blocker_type = "PASS" if passed else ("SECURITY BLOCKER" if security_issues else "BUG")
        report_path = outdir / "project_reports" / f"{slug}.json"
        write_json(
            report_path,
            {
                "spec": spec.model_dump(),
                "features": features,
                "report": serialize_report(report),
                "security_ok": security_ok,
                "security_issues": security_issues,
                "readme_ok": readme_ok,
                "source_ok": source_ok,
                "source_issues": source_issues,
                "fixture_ok": fixture_ok,
                "reviewer": asdict(reviewer),
                "score": final_score,
                "passed": passed,
            },
        )
        write_text(outdir / "project_reports" / f"{slug}.md", summarize_report(report))
        certification = FeatureProjectCertification(
            name=spec.name,
            features=list(features),
            passed=passed,
            score=final_score,
            blocker_type=blocker_type,
            failed_checks=failed_checks,
            project_path=str(project_path),
            report_path=str(report_path),
            reviewer=reviewer,
            generated_files=report.generated_files,
            trace_ids=report.trace_ids,
            tokens=report.tokens,
            actual_cost=report.actual_cost,
        )
        results.append(certification)
        progress(f"project done: {slug} passed={passed} score={final_score} failed={failed_checks}")
    return results


def write_summary(
    outdir: Path,
    run_id: str,
    live_ok: bool,
    projects: list[FeatureProjectCertification],
    *,
    expected_total: int | None = None,
    project_min_score: int = PROJECT_MIN_SCORE,
    suite_min_average: float = SUITE_MIN_AVERAGE,
    suite_label: str = "real-feature",
) -> int:
    avg = sum(p.score for p in projects) / max(len(projects), 1)
    expected_total = expected_total or len(make_real_feature_specs())
    all_projects_passed = all(p.passed for p in projects)
    full_suite_project_count_met = len(projects) == expected_total
    scope_decision = "GO" if live_ok and all_projects_passed and avg >= suite_min_average else "HOLD"
    final_decision = "GO" if scope_decision == "GO" and full_suite_project_count_met else "HOLD"
    summary = {
        "run_id": run_id,
        "suite": suite_label,
        "outdir": str(outdir),
        "live_deepseek_smoke_passed": live_ok,
        "project_count": len(projects),
        "expected_project_count": expected_total,
        "project_min_score": project_min_score,
        "suite_min_average": suite_min_average,
        "suite_average": avg,
        "all_projects_passed": all_projects_passed,
        "full_suite_project_count_met": full_suite_project_count_met,
        "scope_decision": scope_decision,
        "final_decision": final_decision,
        "projects": [asdict(p) for p in projects],
    }
    write_json(outdir / "summary.json", summary)
    with (outdir / "projects.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["name", "features", "passed", "score", "failed_checks", "tokens", "actual_cost", "project_path"],
        )
        writer.writeheader()
        for project in projects:
            writer.writerow(
                {
                    "name": project.name,
                    "features": ",".join(project.features),
                    "passed": project.passed,
                    "score": project.score,
                    "failed_checks": ";".join(project.failed_checks),
                    "tokens": project.tokens,
                    "actual_cost": project.actual_cost,
                    "project_path": project.project_path,
                }
            )
    lines = [
        f"# LARGESTACK {suite_label} {expected_total}-Project Certification",
        "",
        f"- Decision: `{final_decision}`",
        f"- Scope decision: `{scope_decision}`",
        f"- Live DeepSeek smoke: `{live_ok}`",
        f"- Projects: `{len(projects)}/{expected_total}`",
        f"- Project minimum score: `{project_min_score}`",
        f"- Suite minimum average: `{suite_min_average}`",
        f"- Suite average: `{avg:.1f}`",
        "",
        "## Project Results",
        "",
        "| # | Project | Features | Pass | Score | Failed Checks |",
        "|---:|---|---|---:|---:|---|",
    ]
    for idx, project in enumerate(projects, start=1):
        lines.append(
            f"| {idx} | {project.name} | {', '.join(project.features)} | "
            f"{project.passed} | {project.score} | {', '.join(project.failed_checks)} |"
        )
    blockers = [p for p in projects if not p.passed]
    if blockers or not live_ok:
        lines.extend(["", "## Blockers", ""])
        if not live_ok:
            lines.append("- `ENV BLOCKER` live_deepseek_smoke: DeepSeek API/network/key did not pass the live smoke gate.")
        for project in blockers:
            lines.append(
                f"- `{project.blocker_type}` {project.name}: {', '.join(project.failed_checks)}. "
                f"Open `{project.report_path}` and repair/rerun."
            )
    elif not full_suite_project_count_met:
        lines.extend(
            [
                "",
                "## Scope",
                "",
                "- This was a project slice. Scope decision is GO for the selected projects, "
                "while final_decision remains HOLD for the full-suite release gate.",
            ]
        )
    write_text(outdir / "SUMMARY.md", "\n".join(lines) + "\n")
    return 0 if scope_decision == "GO" else 1


async def async_main(args: argparse.Namespace) -> int:
    if not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
        print("LARGESTACK_DEEPSEEK_API_KEY is required; load it from .env or CI secrets.", file=sys.stderr)
        return 2
    specs, project_min_score, suite_min_average, suite_label = select_specs_for_suite(args.suite)
    run_id = args.run_id or now_id()
    outdir = ROOT / "release_evidence" / "final_95_plus" / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    progress(f"run start: {run_id}")
    progress(f"suite: {suite_label} projects={len(specs)} min_score={project_min_score} suite_average={suite_min_average}")
    progress(f"evidence dir: {outdir}")
    live_ok = await live_deepseek_smoke(outdir)
    projects = await run_suite(
        outdir,
        args.project_limit or None,
        max(1, args.project_start),
        specs=specs,
        project_min_score=project_min_score,
    )
    rc = write_summary(
        outdir,
        run_id,
        live_ok,
        projects,
        expected_total=len(specs),
        project_min_score=project_min_score,
        suite_min_average=suite_min_average,
        suite_label=suite_label,
    )
    progress(f"run done: scope_decision={'GO' if rc == 0 else 'HOLD'} evidence={outdir}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Largestack feature/B2B live certification.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--project-limit", type=int, default=0)
    parser.add_argument("--project-start", type=int, default=1)
    parser.add_argument("--suite", choices=["features", "b2b", "all"], default="features")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
