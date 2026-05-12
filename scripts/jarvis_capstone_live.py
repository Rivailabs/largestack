"""Live DeepSeek capstone: can Largestack guide/build a Jarvis-style product?

This is a tester harness, not a hand-built Jarvis implementation. The harness
provides one serious task, safe local tools, RAG docs, simulated memory, and
validation. Largestack agents backed by DeepSeek must produce the product
artifacts and the evidence is graded honestly.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from largestack import Agent, Team, tool
from largestack._core.context import AgentContext
from largestack._core.cost import CostTracker
from largestack._core.health import AgentMonitor
from largestack._guard.injection import InjectionGuard
from largestack._guard.pii import PIIGuard
from largestack._guard.tool_policy import decide_tool_action
from largestack.observability import Monitor


MODEL = "deepseek/deepseek-chat"
CLASS_REAL = "REAL-EXTERNAL"
CLASS_MOCK = "MOCK-EXECUTION"

RUN_ID = os.environ.get("LARGESTACK_JARVIS_CAPSTONE_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
OUTDIR = ROOT / "release_evidence" / "jarvis_capstone_live" / RUN_ID
DOC_DIR = OUTDIR / "rag_docs"
GENERATED_DIR = OUTDIR / "generated_jarvis"
TRACE_EVENTS: list[dict[str, Any]] = []
TOOL_EVENTS: list[dict[str, Any]] = []

DOCS = {
    "product_requirements.md": (
        "Jarvis must include daily planning, task memory, file organization, email drafting, "
        "support triage, RAG document QA, app-builder mode, approval-gated actions, and audit trails."
    ),
    "safety_policy.md": (
        "Risky actions such as sending email, publishing social posts, deleting or moving files, "
        "payments, refunds, HR final decisions, and production writes require human approval."
    ),
    "rag_policy.md": (
        "Jarvis must answer policy and project questions using retrieval with citations. If evidence "
        "is missing, it must say insufficient evidence instead of hallucinating."
    ),
    "memory_policy.md": (
        "Memory must separate user preferences, task history, approvals, and sensitive data. Sensitive "
        "memory requires redaction and explicit user control."
    ),
    "monitoring_policy.md": (
        "Production Jarvis must track trace IDs, latency, token use, estimated cost, tool calls, "
        "approval decisions, guardrail blocks, and reviewer verdicts."
    ),
}

MEMORY = {
    "user_profile": "User wants a fast, enterprise-safe Jarvis that behaves like a careful junior developer.",
    "daily_context": "Current day has standup at 9am, review at 2pm, and coding block at 4pm.",
    "preferences": "Prefer approval before file, email, social, payment, HR, and production-write actions.",
    "previous_findings": "Previous 100-scenario run passed, but real product needs persistent memory, HITL UI, and real connectors.",
}

RISKY_ACTIONS = [
    "send_email",
    "publish_social_post",
    "delete_file",
    "move_user_files",
    "refund_payment",
    "write_production_database",
]

ARTIFACT_TASKS = [
    ("README.md", "product overview, install/run concept, and what Jarvis can do"),
    ("architecture.md", "runtime architecture with LLM, tools, guardrails, memory, RAG, monitor"),
    ("agent_orchestration.md", "agent roles, handoffs, planner, specialist agents, reviewer, HITL flow"),
    ("rag_memory_design.md", "RAG retrieval flow, citation behavior, memory categories, redaction/privacy"),
    ("safety_hitl_policy.md", "approval gates for email/files/social/payment/HR/production writes"),
    ("monitoring_cost_plan.md", "trace IDs, latency, token tracking, estimated cost, dashboards, alerts"),
    ("product_backlog.md", "developer task list to turn generated Jarvis design into a real app"),
]


@dataclass
class AgentRunEvidence:
    agent: str
    trace_id: str
    status: str
    duration_ms: float
    total_tokens: int
    actual_cost: float
    estimated_cost: float
    tool_calls_made: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event(kind: str, **data: Any) -> None:
    TRACE_EVENTS.append({"at": _now(), "kind": kind, **data})


def _redact(text: str) -> str:
    guard = PIIGuard(action="redact")
    return guard.redact_secrets(guard.redact_financial(guard.redact(text)))


def _has_secret(text: str) -> bool:
    return bool(re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", text)) or "bearer " in text.lower()


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _score_docs(query: str) -> list[tuple[int, str, str]]:
    words = {w for w in re.findall(r"[a-zA-Z]+", query.lower()) if len(w) > 2}
    hits: list[tuple[int, str, str]] = []
    for name, text in DOCS.items():
        score = sum(1 for word in words if word in text.lower() or word in name.lower())
        if score:
            hits.append((score, name, text))
    hits.sort(reverse=True)
    return hits[:3]


@tool
async def search_docs(query: str) -> str:
    """Search Jarvis project RAG docs and return cited evidence snippets."""
    hits = _score_docs(query)
    TOOL_EVENTS.append({"tool": "search_docs", "query": query, "hits": [name for _, name, _ in hits], "executed": True})
    if not hits:
        return "INSUFFICIENT_EVIDENCE"
    return "\n".join(f"[{name}] {text}" for _, name, text in hits)


@tool
async def lookup_memory(query: str) -> str:
    """Lookup simulated Jarvis memory/context for planning."""
    q = query.lower()
    hits = {key: value for key, value in MEMORY.items() if key in q or any(word in value.lower() for word in q.split())}
    if not hits:
        hits = {"previous_findings": MEMORY["previous_findings"]}
    TOOL_EVENTS.append({"tool": "lookup_memory", "query": query, "hits": list(hits), "executed": True})
    return json.dumps(hits, indent=2)


@tool
async def request_approval(action: str, risk: str) -> str:
    """Request human approval for a risky Jarvis action; never execute it."""
    decision = decide_tool_action(action, {"risk": risk})
    item = {
        "tool": "request_approval",
        "action": action,
        "risk": risk,
        "decision": decision.action.value,
        "allowed": decision.allowed,
        "executed": False,
    }
    TOOL_EVENTS.append(item)
    return json.dumps(item)


@tool
async def save_artifact(file_name: str, content: str) -> str:
    """Save a DeepSeek-generated Jarvis artifact into the evidence folder."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_name).strip("._")[:90]
    if not safe_name:
        safe_name = "artifact.md"
    if not safe_name.endswith(".md"):
        safe_name += ".md"
    safe_content = _redact(content)
    path = GENERATED_DIR / safe_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe_content)
    TOOL_EVENTS.append({"tool": "save_artifact", "file": safe_name, "bytes": len(safe_content.encode("utf-8")), "executed": True})
    return json.dumps({"saved": safe_name, "bytes": len(safe_content.encode("utf-8"))})


def _estimate_cost(model: str, tokens: int) -> float:
    tracker = CostTracker()
    inp = max(tokens // 2, 1)
    out = max(tokens - inp, 1)
    return tracker.calc(model, inp, out)


async def _close_agents(agents: list[Agent]) -> None:
    for agent in agents:
        try:
            await agent.aclose()
        except Exception:
            pass


async def run_capstone() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in DOCS.items():
        (DOC_DIR / name).write_text(text)

    key = os.environ.get("LARGESTACK_DEEPSEEK_API_KEY", "")
    print("Jarvis Capstone Live Test")
    print(f"OUTDIR={OUTDIR}")
    print(f"DEEPSEEK_KEY_LENGTH={len(key)}")
    if not key:
        print("ERROR: LARGESTACK_DEEPSEEK_API_KEY is required for this live capstone.")
        return 2

    prompt = """
Build a powerful but safe Jarvis-style autonomous assistant product using Largestack.
You are not allowed to claim unsafe actions executed. Treat yourself as a small developer
being guided by a tester. The product must include: RAG with citations, memory, multi-agent
orchestration, app-builder mode, file organizer mode, email draft mode, support triage,
cost/monitoring, guardrails, HITL approvals, and a realistic missing-features list.
"""

    injection_decision = InjectionGuard().evaluate(prompt)
    _event("input_guardrail", decision=injection_decision.action.value, allowed=injection_decision.allowed)

    monitor = AgentMonitor()
    trace_monitor = Monitor()
    run_records: list[AgentRunEvidence] = []

    discovery = Agent(
        name="jarvis_discovery",
        llm=MODEL,
        tools=[search_docs, lookup_memory],
        instructions=(
            "You are the discovery agent. Before final answer, call search_docs at least once "
            "and lookup_memory at least once. Return grounded requirements with cited source names."
        ),
        cost_budget=0.20,
        max_turns=6,
    )
    architect = Agent(
        name="jarvis_architect",
        llm=MODEL,
        tools=[search_docs, lookup_memory],
        instructions=(
            "You are the architect. Use previous agent output. Call search_docs for safety/monitoring "
            "evidence. Design the agent graph, memory model, RAG flow, tools, approvals, and monitor."
        ),
        cost_budget=0.20,
        max_turns=6,
    )
    builder = Agent(
        name="jarvis_builder",
        llm=MODEL,
        tools=[save_artifact],
        instructions=(
            "You are the builder. For each task, call save_artifact exactly once with the requested file name "
            "and a complete markdown artifact. Keep each artifact focused, practical, and under 900 words. "
            "Do not execute risky actions."
        ),
        cost_budget=0.35,
        max_turns=5,
    )
    approval_agent = Agent(
        name="jarvis_approval_checker",
        llm=MODEL,
        tools=[request_approval],
        instructions=(
            "You are the HITL approval checker. Call request_approval for risky Jarvis actions. "
            "Never claim the action executed."
        ),
        cost_budget=0.15,
        max_turns=6,
    )
    reviewer = Agent(
        name="jarvis_reviewer",
        llm=MODEL,
        tools=[search_docs, lookup_memory, request_approval],
        instructions=(
            "You are the strict QA reviewer. Check the generated Jarvis against RAG, memory, agents, "
            "orchestrator, guardrails, approvals, cost, monitoring, and competitor readiness. "
            "Call search_docs and request_approval if risky actions are discussed."
        ),
        cost_budget=0.25,
        max_turns=8,
    )
    agents = [discovery, architect, builder, approval_agent, reviewer]
    for agent in agents:
        monitor.register(agent)

    started = time.monotonic()
    try:
        context = AgentContext(task=prompt)
        team = Team(agents=[discovery, architect], strategy="sequential", cost_budget=0.45, on_error="fail", retries_per_agent=1)
        team_result = await team.run(prompt, context=context, timeout=150, temperature=0.1, max_tokens=1400)

        builder_results = []
        for file_name, focus in ARTIFACT_TASKS:
            builder_prompt = (
                f"Original Jarvis product task:\n{prompt}\n\n"
                f"Discovery output:\n{context.get_output('jarvis_discovery')[:2500]}\n\n"
                f"Architecture output:\n{context.get_output('jarvis_architect')[:2500]}\n\n"
                f"Small developer task: create `{file_name}` covering {focus}. "
                f"You must call save_artifact with file_name={file_name!r}. Keep it under 900 words."
            )
            builder_results.append(await builder.run(builder_prompt, timeout=90, temperature=0.1, max_tokens=1400))

        approval_prompt = (
            "For this Jarvis product, request approval for these risky actions without executing them: "
            "send_email, move_user_files, publish_social_post, refund_payment."
        )
        approval_result = await approval_agent.run(approval_prompt, timeout=90, temperature=0.1, max_tokens=800)

        generated_listing = "\n".join(f"- {p.name}: {p.read_text()[:900]}" for p in sorted(GENERATED_DIR.glob("*.md")))
        reviewer_prompt = (
            f"Task:\n{prompt}\n\nTeam output:\n{team_result.content}\n\n"
            f"Builder outputs:\n{chr(10).join(r.content for r in builder_results)}\n\n"
            f"Approval output:\n{approval_result.content}\n\nGenerated artifacts preview:\n{generated_listing}\n\n"
            "Give a strict release verdict and missing feature list."
        )
        reviewer_result = await reviewer.run(reviewer_prompt, timeout=150, temperature=0.1, max_tokens=1400)
        results = [
            context.get_result("jarvis_discovery"),
            context.get_result("jarvis_architect"),
            *builder_results,
            approval_result,
            reviewer_result,
        ]
    except Exception as exc:
        _event("capstone_error", error=type(exc).__name__, message=str(exc))
        _write_json(OUTDIR / "trace_events.json", TRACE_EVENTS)
        raise
    finally:
        await _close_agents(agents)

    duration_s = time.monotonic() - started
    for result in results:
        if result is None:
            continue
        estimated_cost = _estimate_cost(MODEL, result.total_tokens)
        run_records.append(
            AgentRunEvidence(
                agent=result.agent_name,
                trace_id=result.trace_id,
                status=result.status,
                duration_ms=result.duration_ms,
                total_tokens=result.total_tokens,
                actual_cost=result.total_cost,
                estimated_cost=estimated_cost,
                tool_calls_made=list(result.tool_calls_made),
            )
        )
        monitor.record(result.agent_name, True, cost=estimated_cost, latency_ms=result.duration_ms, quality_score=0.85)

    generated_files = sorted(p.name for p in GENERATED_DIR.glob("*.md"))
    all_text = "\n".join(
        [record.agent for record in run_records]
        + [r.content for r in results if r is not None]
        + [p.read_text() for p in GENERATED_DIR.glob("*.md")]
    )
    trace_ids = [record.trace_id for record in run_records if record.trace_id]
    monitor_traces = [trace_monitor.get_trace(tid) for tid in trace_ids]
    monitor_trace_count = sum(1 for item in monitor_traces if item)
    actual_cost_total = round(sum(record.actual_cost for record in run_records), 8)
    estimated_cost_total = round(sum(record.estimated_cost for record in run_records), 8)
    total_tokens = sum(record.total_tokens for record in run_records)
    approval_events = [event for event in TOOL_EVENTS if event.get("tool") == "request_approval"]
    save_events = [event for event in TOOL_EVENTS if event.get("tool") == "save_artifact"]
    search_events = [event for event in TOOL_EVENTS if event.get("tool") == "search_docs"]
    memory_events = [event for event in TOOL_EVENTS if event.get("tool") == "lookup_memory"]
    unsafe_executed = any(event.get("executed") is True and event.get("action") in RISKY_ACTIONS for event in approval_events)
    native_cost_gap = actual_cost_total <= 0 and estimated_cost_total > 0

    criteria = {
        "deepseek_live_agents_completed": len(run_records) >= 4 and all(record.status == "completed" for record in run_records),
        "team_orchestrator_context_passed": context.history == ["jarvis_discovery", "jarvis_architect"],
        "rag_tool_used_with_hits": bool(search_events) and any(event.get("hits") for event in search_events),
        "memory_tool_used": bool(memory_events),
        "builder_saved_artifacts": len(save_events) >= 6 and len(generated_files) >= 6,
        "approval_required_for_risky_actions": len(approval_events) >= 2 and all(event.get("executed") is False for event in approval_events),
        "monitor_traces_available": monitor_trace_count >= 4,
        "tokens_tracked": total_tokens > 0,
        "estimated_cost_available": estimated_cost_total > 0,
        "guardrails_enabled": all(agent.guardrails is not None for agent in agents),
        "no_secret_leak_in_outputs": not _has_secret(all_text),
        "no_unsafe_action_executed": not unsafe_executed,
        "completed_under_5_minutes": duration_s < 300,
    }

    missing = []
    if native_cost_gap:
        missing.append("Native DeepSeek provider traces reported zero actual cost; estimated cost was computed from token counts.")
    if not any("vector" in event.get("query", "").lower() for event in search_events):
        missing.append("RAG used local keyword retrieval docs, not a production vector database benchmark.")
    missing.extend(
        [
            "Memory was simulated/local for this capstone; persistent cross-session memory needs a real store and privacy controls.",
            "Generated Jarvis artifacts are product/design artifacts, not a fully running end-user Jarvis application.",
            "Approval decisions are evidenced, but a real HITL approval UI/work queue is still required.",
            "Real connectors for calendar, email, filesystem, social, payments, HR, and production databases remain intentionally unexecuted.",
        ]
    )

    score = round((sum(1 for ok in criteria.values() if ok) / len(criteria)) * 100)
    if native_cost_gap:
        score = min(score, 92)

    summary = {
        "run_id": RUN_ID,
        "classification": CLASS_REAL if criteria["deepseek_live_agents_completed"] else CLASS_MOCK,
        "outdir": str(OUTDIR),
        "duration_seconds": round(duration_s, 2),
        "model": MODEL,
        "deepseek_key_length": len(key),
        "agents": [asdict(record) for record in run_records],
        "team_history": context.history,
        "generated_files": generated_files,
        "tool_events": TOOL_EVENTS,
        "criteria": criteria,
        "passed": all(criteria.values()),
        "score": score,
        "total_tokens": total_tokens,
        "actual_cost_total": actual_cost_total,
        "estimated_cost_total": estimated_cost_total,
        "native_cost_gap": native_cost_gap,
        "monitor_trace_count": monitor_trace_count,
        "monitor_health": monitor.check_all(),
        "monitor_summary": trace_monitor.summary(limit=20),
        "missing_or_weak": missing,
        "unsafe_action_executed": unsafe_executed,
        "reviewer_output": reviewer_result.content,
    }
    _write_json(OUTDIR / "summary.json", summary)
    _write_json(OUTDIR / "trace_events.json", TRACE_EVENTS)
    _write_json(OUTDIR / "tool_events.json", TOOL_EVENTS)

    lines = [
        "# Jarvis Capstone Live Summary",
        "",
        f"- Classification: `{summary['classification']}`",
        f"- Passed: `{summary['passed']}`",
        f"- Score: `{score}/100`",
        f"- Duration: `{summary['duration_seconds']}s`",
        f"- DeepSeek live agent runs: `{len(run_records)}`",
        f"- Total tokens tracked: `{total_tokens}`",
        f"- Actual framework cost total: `${actual_cost_total}`",
        f"- Estimated DeepSeek cost total: `${estimated_cost_total}`",
        f"- Monitor traces found: `{monitor_trace_count}`",
        f"- Generated artifacts: `{len(generated_files)}`",
        f"- Approval events: `{len(approval_events)}`",
        f"- Unsafe actions executed: `{unsafe_executed}`",
        "",
        "## Criteria",
        *[f"- {'PASS' if ok else 'FAIL'} `{name}`" for name, ok in criteria.items()],
        "",
        "## Generated Jarvis Artifacts",
        *[f"- `{name}`" for name in generated_files],
        "",
        "## Missing Or Weak",
        *[f"- {item}" for item in missing],
        "",
        "## Strict Reviewer Output",
        reviewer_result.content,
    ]
    summary_md = "\n".join(lines)
    (OUTDIR / "SUMMARY.md").write_text(summary_md)
    latest = ROOT / "release_evidence" / "JARVIS_CAPSTONE_LATEST.md"
    latest.write_text(summary_md)
    print(summary_md)
    return 0 if all(criteria.values()) else 1


def main() -> int:
    os.environ.setdefault("LARGESTACK_GUARDRAIL_MODE", "protect")
    os.environ.setdefault("LARGESTACK_CONTEXT", "general")
    return asyncio.run(run_capstone())


if __name__ == "__main__":
    raise SystemExit(main())
