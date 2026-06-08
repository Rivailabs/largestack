#!/usr/bin/env python3
"""LARGESTACK runtime load/soak certification harness.

This is intentionally deterministic by default: it uses TestModel and
FunctionModel so production-runtime behavior can be exercised without live
provider spend, network dependency, or accidental model calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
try:
    import resource  # Unix-only; absent on Windows
except ImportError:  # pragma: no cover - Windows
    resource = None
import sqlite3
import sys
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "release_evidence" / "load_soak"

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|"
    r"Bearer\s+[A-Za-z0-9._-]{12,}|"
    r"(?i:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{10,})"
)


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: str
    runner: Callable[[int], Awaitable[dict[str, Any]]]


@dataclass
class RunEvent:
    index: int
    scenario: str
    kind: str
    status: str
    latency_ms: float
    trace_id: str = ""
    total_cost: float = 0.0
    total_tokens: int = 0
    expected_failure: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    traceback: str = ""


@dataclass
class CertConfig:
    run_id: str
    outdir: Path
    total_runs: int
    concurrency: int
    duration_seconds: float
    per_run_timeout: float
    target_success_rate: float
    max_memory_growth_mb: float
    include_failure_injections: bool
    profile: str
    prewarm: bool = True
    scenario_set: str = "all"


@dataclass
class LoadDeps:
    tenant_id: str
    tickets: dict[str, str]


class Aggregates:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.expected_failures = 0
        self.stuck = 0
        self.latencies_ms: list[float] = []
        self.cost_total = 0.0
        self.tokens_total = 0
        self.by_scenario: dict[str, dict[str, int]] = {}
        self.failures: list[dict[str, Any]] = []
        self.trace_ids: set[str] = set()

    def record(self, event: RunEvent) -> None:
        self.total += 1
        self.latencies_ms.append(event.latency_ms)
        self.cost_total += event.total_cost
        self.tokens_total += event.total_tokens
        if event.trace_id:
            self.trace_ids.add(event.trace_id)
        bucket = self.by_scenario.setdefault(
            event.scenario,
            {"total": 0, "passed": 0, "failed": 0, "expected_failures": 0},
        )
        bucket["total"] += 1
        if event.status == "passed":
            self.passed += 1
            bucket["passed"] += 1
        else:
            self.failed += 1
            bucket["failed"] += 1
            if len(self.failures) < 100:
                self.failures.append(asdict(event))
        if event.expected_failure:
            self.expected_failures += 1
            bucket["expected_failures"] += 1
        if event.error == "timeout":
            self.stuck += 1


def redact_text(value: str) -> str:
    return SECRET_RE.sub("[REDACTED]", value)


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, tuple):
        return [redact_obj(v) for v in value]
    if isinstance(value, dict):
        return {str(k): redact_obj(v) for k, v in value.items()}
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact_obj(payload), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    weight = rank - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def peak_rss_mb() -> float:
    if resource is None:  # Windows: `resource` unavailable
        return 0.0
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


def configure_runtime(outdir: Path) -> Path:
    """Point trace/audit state at this evidence folder before agents start."""
    trace_db = outdir / "traces.db"
    os.environ["LARGESTACK_TRACE_DB"] = str(trace_db)
    os.environ["LARGESTACK_TRACE_DB_PATH"] = str(trace_db)
    os.environ.setdefault("LARGESTACK_ENV", "test")
    os.environ.setdefault("LARGESTACK_DEFAULT_LLM", "deepseek/deepseek-chat")
    if os.environ.get("LARGESTACK_LOAD_SOAK_OTEL", "").lower() not in {"1", "true", "yes"}:
        # This harness validates the dashboard/run trace table directly.
        # Disable OTEL span workers by default so long load runs and pytest
        # invocations exit cleanly. Set LARGESTACK_LOAD_SOAK_OTEL=1 when the
        # span exporter itself is the thing under test.
        os.environ["LARGESTACK_TRACE_ENABLED"] = "false"

    # Reset cached config when this script is imported and run inside pytest.
    try:
        import largestack._core.config as cfg

        cfg._cfg = None
    except Exception:
        pass
    try:
        import largestack._observe.traces_db as traces_db_mod

        traces_db_mod.DEFAULT_TRACE_DB = str(trace_db)
        traces_db_mod._initialized.discard(str(trace_db))
        traces_db_mod._ensure_schema(str(trace_db))
    except Exception:
        pass
    return trace_db


async def scenario_typed_agent_tools(index: int) -> dict[str, Any]:
    from largestack.decorators import Agent, RunContext
    from largestack.testing import TestModel

    # largestack.decorators currently resolves tool annotations through the
    # function module globals. This keeps local harness functions compatible
    # with `from __future__ import annotations`.
    globals()["RunContext"] = RunContext

    agent = Agent[LoadDeps, str](
        "deepseek/deepseek-chat",
        deps_type=LoadDeps,
        instructions="Route tickets safely using typed tools.",
        name=f"typed_ticket_agent_{index}",
        max_retries=1,
        cost_budget=0.05,
    )

    @agent.tool
    async def lookup_ticket(ctx: RunContext[LoadDeps], ticket_id: str) -> str:
        """Look up one tenant-scoped support ticket."""
        return ctx.deps.tickets.get(ticket_id, "missing")

    @agent.tool_plain
    async def normalize_priority(priority: str) -> str:
        """Normalize a priority label."""
        return priority.upper()

    model = TestModel(
        custom_output_text="ticket T123 routed as HIGH",
        custom_tool_args={
            "lookup_ticket": {"ticket_id": "T123"},
            "normalize_priority": {"priority": "high"},
        },
        call_tools=["lookup_ticket", "normalize_priority"],
    )
    deps = LoadDeps(tenant_id=f"tenant-{index % 7}", tickets={"T123": "login outage"})
    with agent.override(model=model):
        result = await agent.run("Route ticket T123", deps=deps)

    assert "HIGH" in result.output
    assert set(model.tool_calls_made) == {"lookup_ticket", "normalize_priority"}
    return {
        "trace_id": result.trace_id,
        "cost": result.cost,
        "tokens": 0,
        "tools": model.tool_calls_made,
        "feature": "typed_agent_tools",
    }


async def scenario_agent_run(index: int) -> dict[str, Any]:
    from largestack import Agent, TestModel

    agent = Agent(
        name=f"lightweight_run_{index}",
        instructions="Return a deterministic lightweight response.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        cost_budget=0.01,
        max_turns=2,
    )
    with agent.override(model=TestModel("lightweight ok", call_tools=[])):
        result = await agent.run("lightweight run")

    assert result.content == "lightweight ok"
    return {
        "trace_id": result.trace_id,
        "cost": result.total_cost,
        "tokens": result.total_tokens,
        "feature": "agent_run",
    }


async def scenario_team_parallel(index: int) -> dict[str, Any]:
    from contextlib import ExitStack

    from largestack import Agent, Team, TestModel

    triage = Agent(
        name=f"triage_{index}",
        instructions="Classify operational risk.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        cost_budget=0.05,
        max_turns=4,
    )
    reviewer = Agent(
        name=f"reviewer_{index}",
        instructions="Review operational risk.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        cost_budget=0.05,
        max_turns=4,
    )
    team = Team([triage, reviewer], strategy="parallel", cost_budget=0.10, on_error="fail")
    with ExitStack() as stack:
        stack.enter_context(triage.override(model=TestModel("triage: low risk", call_tools=[])))
        stack.enter_context(reviewer.override(model=TestModel("review: approved", call_tools=[])))
        result = await team.run("Assess a small deployment change")

    assert "triage: low risk" in result.content
    assert "review: approved" in result.content
    return {
        "trace_id": result.trace_id,
        "cost": result.total_cost,
        "tokens": result.total_tokens,
        "feature": "team_parallel",
    }


async def scenario_workflow_dag(index: int) -> dict[str, Any]:
    from contextlib import ExitStack

    from largestack import Agent, TestModel, Workflow

    extractor = Agent(
        name=f"extract_{index}",
        instructions="Extract fields.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        cost_budget=0.05,
        max_turns=4,
    )
    validator = Agent(
        name=f"validate_{index}",
        instructions="Validate extracted fields.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        cost_budget=0.05,
        max_turns=4,
    )
    wf = Workflow(f"dag_runtime_{index}", cost_budget=0.10)
    wf.add_node("extract", extractor)
    wf.add_node("validate", validator, deps=["extract"])
    with ExitStack() as stack:
        stack.enter_context(extractor.override(model=TestModel("field_a=ok", call_tools=[])))
        stack.enter_context(validator.override(model=TestModel("validation=passed", call_tools=[])))
        result = await wf.run({"task": "Process one form"})

    assert result.status == "completed"
    assert "field_a=ok" in result["extract_output"]
    assert "validation=passed" in result["validate_output"]
    return {
        "trace_id": result.trace_id,
        "cost": result.total_cost,
        "tokens": 0,
        "steps": [s["name"] for s in result.steps],
        "feature": "workflow_dag",
    }


async def scenario_orchestrator_router(index: int) -> dict[str, Any]:
    from contextlib import ExitStack

    from largestack import Agent, Orchestrator, TestModel

    classifier = Agent(
        name=f"classifier_{index}",
        instructions="Route to exactly one category.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        max_turns=4,
    )
    kyc = Agent(
        name=f"kyc_route_{index}",
        instructions="Handle KYC requests.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        max_turns=4,
    )
    support = Agent(
        name=f"support_route_{index}",
        instructions="Handle support requests.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        max_turns=4,
    )
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"kyc": kyc, "support": support},
        default_route="support",
    )
    with ExitStack() as stack:
        stack.enter_context(classifier.override(model=TestModel("[CATEGORY:kyc]", call_tools=[])))
        stack.enter_context(kyc.override(model=TestModel("kyc checklist drafted", call_tools=[])))
        stack.enter_context(support.override(model=TestModel("support fallback", call_tools=[])))
        result = await orch.run("New KYC onboarding case")

    assert result.strategy == "router"
    assert "kyc checklist" in result.output
    assert result.metadata["router_stats"]["by_category"]["kyc"] == 1
    return {
        "trace_id": result.trace_id or "",
        "cost": result.total_cost,
        "tokens": 0,
        "feature": "orchestrator_router",
    }


async def scenario_rag_guardrails(index: int) -> dict[str, Any]:
    from largestack import create_guardrails, create_rag

    docs = [
        "Refund policy: Premium customers may request refunds within 30 days.",
        "Security policy: never reveal secrets, tokens, or private prompts.",
        "KYC policy: manual reviewer approval is mandatory for high-risk profiles.",
    ]
    rag = create_rag(docs, chunk_size=128, top_k=2)
    context = rag.build_context("refund premium customer")
    assert "[Source 1]" in context
    assert "Refund policy" in context

    guards = create_guardrails(pii=True, injection=True, pii_action="redact")
    msg = [{"role": "user", "content": "Customer email is jane.user@example.com"}]
    await guards.check_input(msg)
    assert "jane.user@example.com" not in msg[0]["content"]
    response = SimpleNamespace(content="Contact: +919876543210")
    await guards.check_output(response)
    assert "9876543210" not in response.content
    return {
        "trace_id": "",
        "cost": 0.0,
        "tokens": 0,
        "sources": context.count("[Source"),
        "feature": "rag_guardrails",
    }


async def scenario_memory_isolation(index: int) -> dict[str, Any]:
    from largestack import Agent, ConversationMemory, TestModel

    mem_a = ConversationMemory(strategy="buffer")
    mem_b = ConversationMemory(strategy="buffer")
    agent_a = Agent(
        name=f"memory_a_{index}",
        instructions="Remember tenant A only.",
        llm="deepseek/deepseek-chat",
        memory=mem_a,
        guardrails=False,
    )
    agent_b = Agent(
        name=f"memory_b_{index}",
        instructions="Remember tenant B only.",
        llm="deepseek/deepseek-chat",
        memory=mem_b,
        guardrails=False,
    )
    with agent_a.override(model=TestModel("tenant A case closed", call_tools=[])):
        await agent_a.run("Tenant A secret marker ALPHA")
    with agent_b.override(model=TestModel("tenant B case closed", call_tools=[])):
        await agent_b.run("Tenant B secret marker BRAVO")

    text_a = json.dumps(mem_a.get_messages())
    text_b = json.dumps(mem_b.get_messages())
    assert "ALPHA" in text_a
    assert "BRAVO" not in text_a
    assert "BRAVO" in text_b
    assert "ALPHA" not in text_b
    return {
        "trace_id": "",
        "cost": 0.0,
        "tokens": 0,
        "feature": "memory_isolation",
    }


async def scenario_structured_output(index: int) -> dict[str, Any]:
    from pydantic import BaseModel, Field

    from largestack import Agent, TestModel

    class RiskDecision(BaseModel):
        approved: bool
        score: int = Field(ge=0, le=100)
        reason: str

    agent = Agent(
        name=f"structured_{index}",
        instructions="Return structured risk decisions.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        max_turns=4,
    )
    with agent.override(
        model=TestModel(
            '{"approved": true, "score": 94, "reason": "policy matched"}',
            call_tools=[],
        )
    ):
        result = await agent.run("Assess low-risk case", response_model=RiskDecision)

    assert result.approved is True
    assert result.score == 94
    return {
        "trace_id": "",
        "cost": 0.0,
        "tokens": 0,
        "feature": "structured_output",
    }


async def scenario_tool_error_handled(index: int) -> dict[str, Any]:
    from largestack import Agent, TestModel, tool

    @tool(retries=0, timeout=0.25)
    def risky_write(case_id: str) -> str:
        """Simulate a risky write that fails before any side effect."""
        raise RuntimeError(f"approval required for {case_id}")

    agent = Agent(
        name=f"tool_error_{index}",
        instructions="Never execute risky writes without approval.",
        llm="deepseek/deepseek-chat",
        tools=[risky_write],
        guardrails=False,
        max_turns=4,
    )
    model = TestModel(
        custom_output_text="Risky write blocked and escalated for approval.",
        custom_tool_args={"risky_write": {"case_id": "CASE-9"}},
        call_tools=["risky_write"],
    )
    with agent.override(model=model):
        result = await agent.run("Attempt risky write")

    assert "approval" in result.content.lower()
    assert result.tool_calls_made == ["risky_write"]
    return {
        "trace_id": result.trace_id,
        "cost": result.total_cost,
        "tokens": result.total_tokens,
        "expected_failure": True,
        "feature": "tool_error_handled",
    }


async def scenario_provider_timeout_handled(index: int) -> dict[str, Any]:
    from largestack import Agent, FunctionModel
    from largestack.errors import ProviderTimeoutError

    def timeout_model(messages: list, info: dict) -> dict:
        raise ProviderTimeoutError("deepseek", 0.01)

    agent = Agent(
        name=f"provider_timeout_{index}",
        instructions="Timeout injection.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        retries=0,
    )
    try:
        with agent.override(model=FunctionModel(timeout_model)):
            await agent.run("Timeout please")
    except ProviderTimeoutError:
        return {
            "trace_id": "",
            "cost": 0.0,
            "tokens": 0,
            "expected_failure": True,
            "feature": "provider_timeout",
        }
    raise AssertionError("provider timeout injection was not surfaced")


async def scenario_bad_key_handled(index: int) -> dict[str, Any]:
    from largestack import Agent, FunctionModel
    from largestack.errors import ProviderAuthError

    def bad_key_model(messages: list, info: dict) -> dict:
        raise ProviderAuthError("deepseek")

    agent = Agent(
        name=f"bad_key_{index}",
        instructions="Auth failure injection.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        retries=0,
    )
    try:
        with agent.override(model=FunctionModel(bad_key_model)):
            await agent.run("Auth failure please")
    except ProviderAuthError:
        return {
            "trace_id": "",
            "cost": 0.0,
            "tokens": 0,
            "expected_failure": True,
            "feature": "bad_api_key",
        }
    raise AssertionError("bad API key injection was not surfaced")


async def scenario_rate_limit_handled(index: int) -> dict[str, Any]:
    from largestack import Agent, FunctionModel
    from largestack.errors import ProviderRateLimitError

    def rate_limited_model(messages: list, info: dict) -> dict:
        raise ProviderRateLimitError("simulated DeepSeek rate limit")

    fallback = Agent(
        name=f"rate_limit_fallback_{index}",
        instructions="Fallback answer.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        retries=0,
    )
    primary = Agent(
        name=f"rate_limit_primary_{index}",
        instructions="Rate limit injection.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
        retries=0,
        fallback=fallback,
    )
    with primary.override(model=FunctionModel(rate_limited_model)):
        with fallback.override(model=FunctionModel(lambda messages, info: "fallback recovered")):
            result = await primary.run("Trigger rate limit and recover")
    assert "fallback recovered" in result.content
    return {
        "trace_id": result.trace_id,
        "cost": result.total_cost,
        "tokens": result.total_tokens,
        "expected_failure": True,
        "feature": "rate_limit_fallback",
    }


def build_scenarios(include_failure_injections: bool, scenario_set: str = "all") -> list[Scenario]:
    lightweight = [
        Scenario("agent_run", "lightweight", scenario_agent_run),
    ]
    mixed = [
        Scenario("typed_agent_tools", "mixed", scenario_typed_agent_tools),
        Scenario("team_parallel", "mixed", scenario_team_parallel),
        Scenario("workflow_dag", "mixed", scenario_workflow_dag),
        Scenario("orchestrator_router", "mixed", scenario_orchestrator_router),
        Scenario("rag_guardrails", "mixed", scenario_rag_guardrails),
        Scenario("memory_isolation", "mixed", scenario_memory_isolation),
        Scenario("structured_output", "mixed", scenario_structured_output),
    ]
    if scenario_set == "lightweight":
        return lightweight
    scenarios = lightweight + mixed if scenario_set == "all" else mixed
    if include_failure_injections:
        scenarios.extend(
            [
                Scenario("tool_error_handled", "failure_injection", scenario_tool_error_handled),
                Scenario(
                    "provider_timeout_handled",
                    "failure_injection",
                    scenario_provider_timeout_handled,
                ),
                Scenario("bad_key_handled", "failure_injection", scenario_bad_key_handled),
                Scenario("rate_limit_handled", "failure_injection", scenario_rate_limit_handled),
            ]
        )
    return scenarios


async def run_one(index: int, scenario: Scenario, per_run_timeout: float) -> RunEvent:
    started = time.perf_counter()
    try:
        detail = await asyncio.wait_for(scenario.runner(index), timeout=per_run_timeout)
        latency_ms = (time.perf_counter() - started) * 1000
        expected_failure = bool(detail.pop("expected_failure", False))
        return RunEvent(
            index=index,
            scenario=scenario.name,
            kind=scenario.kind,
            status="passed",
            latency_ms=latency_ms,
            trace_id=str(detail.pop("trace_id", "") or ""),
            total_cost=float(detail.pop("cost", 0.0) or 0.0),
            total_tokens=int(detail.pop("tokens", 0) or 0),
            expected_failure=expected_failure,
            detail=detail,
        )
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - started) * 1000
        return RunEvent(
            index=index,
            scenario=scenario.name,
            kind=scenario.kind,
            status="failed",
            latency_ms=latency_ms,
            error="timeout",
            traceback="",
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return RunEvent(
            index=index,
            scenario=scenario.name,
            kind=scenario.kind,
            status="failed",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(limit=8),
        )


async def prewarm_scenarios(config: CertConfig, scenarios: list[Scenario]) -> dict[str, Any]:
    from largestack.testing import disable_model_requests, enable_model_requests

    results: list[dict[str, Any]] = []
    disable_model_requests()
    try:
        for index, scenario in enumerate(scenarios):
            event = await run_one(-1 - index, scenario, config.per_run_timeout)
            results.append(
                {
                    "scenario": scenario.name,
                    "status": event.status,
                    "latency_ms": round(event.latency_ms, 3),
                    "error": event.error,
                }
            )
            if event.status != "passed":
                raise RuntimeError(f"prewarm failed for {scenario.name}: {event.error}")
    finally:
        enable_model_requests()
    return {"enabled": True, "scenarios": results}


async def execute_load(
    config: CertConfig, scenarios: list[Scenario]
) -> tuple[Aggregates, float, float]:
    from largestack.testing import disable_model_requests, enable_model_requests

    aggregates = Aggregates()
    events_path = config.outdir / "events.jsonl"
    event_lock = asyncio.Lock()
    started = time.perf_counter()

    async def record(event: RunEvent, fp) -> None:
        async with event_lock:
            fp.write(json.dumps(redact_obj(asdict(event)), sort_keys=True, default=str) + "\n")
            aggregates.record(event)

    async def guarded_run(index: int, fp) -> None:
        scenario = scenarios[index % len(scenarios)]
        event = await run_one(index, scenario, config.per_run_timeout)
        await record(event, fp)

    disable_model_requests()
    try:
        with events_path.open("w", encoding="utf-8") as fp:
            if config.duration_seconds > 0:
                deadline = time.perf_counter() + config.duration_seconds
                counter = 0

                async def worker(worker_id: int) -> None:
                    nonlocal counter
                    while time.perf_counter() < deadline:
                        index = counter
                        counter += 1
                        await guarded_run(index, fp)

                await asyncio.gather(*(worker(i) for i in range(config.concurrency)))
            else:
                sem = asyncio.Semaphore(config.concurrency)

                async def bounded(index: int) -> None:
                    async with sem:
                        await guarded_run(index, fp)

                await asyncio.gather(*(bounded(i) for i in range(config.total_runs)))
            fp.flush()
    finally:
        enable_model_requests()

    wall_seconds = time.perf_counter() - started
    return aggregates, wall_seconds, float(len(scenarios))


def inspect_trace_db(trace_db: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if not trace_db.exists():
        return {
            "exists": False,
            "ok": False,
            "rows": 0,
            "integrity": "missing",
            "query_latency_ms": 0.0,
        }
    try:
        with sqlite3.connect(str(trace_db), timeout=2.0) as conn:
            rows = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "exists": True,
            "ok": integrity == "ok",
            "rows": int(rows),
            "integrity": str(integrity),
            "query_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:
        return {
            "exists": True,
            "ok": False,
            "rows": 0,
            "integrity": f"{type(exc).__name__}: {exc}",
            "query_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


def shutdown_observability() -> None:
    """Reset tracing setup state between in-process certification tests."""
    try:
        import largestack._observe.tracer as tracer

        tracer._initialized = False
    except Exception:
        pass


def profile_defaults(profile: str) -> dict[str, Any]:
    profiles = {
        "smoke": {"total_runs": 55, "concurrency": 10, "duration_seconds": 0.0},
        "load100": {"total_runs": 100, "concurrency": 100, "duration_seconds": 0.0},
        "load500": {"total_runs": 500, "concurrency": 500, "duration_seconds": 0.0},
        "load1000": {"total_runs": 1000, "concurrency": 1000, "duration_seconds": 0.0},
        "soak4h": {"total_runs": 0, "concurrency": 100, "duration_seconds": 4 * 60 * 60},
        "soak24h": {"total_runs": 0, "concurrency": 100, "duration_seconds": 24 * 60 * 60},
    }
    return dict(profiles.get(profile, profiles["smoke"]))


def build_summary(
    *,
    config: CertConfig,
    aggregates: Aggregates,
    wall_seconds: float,
    cpu_seconds: float,
    memory_start_mb: float,
    memory_end_mb: float,
    trace_db: Path,
    prewarm: dict[str, Any],
) -> dict[str, Any]:
    success_rate = aggregates.passed / max(aggregates.total, 1)
    memory_growth_mb = max(0.0, memory_end_mb - memory_start_mb)
    trace = inspect_trace_db(trace_db)
    expected_scenarios = [
        s.name for s in build_scenarios(config.include_failure_injections, config.scenario_set)
    ]
    acceptance = {
        "success_rate_ok": success_rate >= config.target_success_rate,
        "no_stuck_runs": aggregates.stuck == 0,
        "trace_db_ok": bool(trace["ok"]),
        "trace_rows_present": int(trace.get("rows", 0) or 0) > 0,
        "memory_growth_ok": (
            config.max_memory_growth_mb <= 0 or memory_growth_mb <= config.max_memory_growth_mb
        ),
        "all_scenarios_exercised": all(
            aggregates.by_scenario.get(name, {}).get("total", 0) > 0 for name in expected_scenarios
        ),
    }
    run_pass = all(acceptance.values())
    throughput = aggregates.total / wall_seconds if wall_seconds > 0 else 0.0
    cpu_pct_one_core = (cpu_seconds / wall_seconds * 100.0) if wall_seconds > 0 else 0.0
    return {
        "run_id": config.run_id,
        "profile": config.profile,
        "decision": "PASS" if run_pass else "HOLD",
        "public_saas_gate": "HOLD",
        "public_saas_gate_reason": (
            "This is one load/soak evidence run. Public SaaS GO still requires "
            "the full matrix: load100, load500, load1000, 4-hour soak, and "
            "24-hour soak before public launch."
        ),
        "requested": {
            "total_runs": config.total_runs,
            "concurrency": config.concurrency,
            "duration_seconds": config.duration_seconds,
            "per_run_timeout": config.per_run_timeout,
            "target_success_rate": config.target_success_rate,
            "max_memory_growth_mb": config.max_memory_growth_mb,
            "include_failure_injections": config.include_failure_injections,
            "prewarm": config.prewarm,
            "scenario_set": config.scenario_set,
        },
        "prewarm": prewarm,
        "metrics": {
            "total": aggregates.total,
            "passed": aggregates.passed,
            "failed": aggregates.failed,
            "expected_failures_handled": aggregates.expected_failures,
            "success_rate": round(success_rate, 6),
            "wall_seconds": round(wall_seconds, 3),
            "throughput_runs_per_second": round(throughput, 3),
            "latency_ms": {
                "p50": round(percentile(aggregates.latencies_ms, 0.50), 3),
                "p95": round(percentile(aggregates.latencies_ms, 0.95), 3),
                "p99": round(percentile(aggregates.latencies_ms, 0.99), 3),
                "max": round(max(aggregates.latencies_ms or [0.0]), 3),
            },
            "cpu_seconds": round(cpu_seconds, 3),
            "cpu_pct_one_core": round(cpu_pct_one_core, 2),
            "memory_start_mb": round(memory_start_mb, 3),
            "memory_peak_end_mb": round(memory_end_mb, 3),
            "memory_growth_mb": round(memory_growth_mb, 3),
            "trace_ids_observed": len(aggregates.trace_ids),
            "cost_total": round(aggregates.cost_total, 8),
            "tokens_total": aggregates.tokens_total,
            "stuck_runs": aggregates.stuck,
        },
        "trace_db": trace,
        "acceptance": acceptance,
        "by_scenario": aggregates.by_scenario,
        "failures": aggregates.failures,
    }


def write_markdown_summary(outdir: Path, summary: dict[str, Any]) -> None:
    metrics = summary["metrics"]
    lines = [
        f"# Load/Soak Certification - {summary['run_id']}",
        "",
        f"Decision: **{summary['decision']}**",
        f"Public SaaS gate: **{summary['public_saas_gate']}**",
        "",
        "## Metrics",
        "",
        f"- Profile: `{summary['profile']}`",
        f"- Runs: `{metrics['passed']}/{metrics['total']}` passed",
        f"- Success rate: `{metrics['success_rate']}`",
        f"- Throughput: `{metrics['throughput_runs_per_second']}` runs/sec",
        f"- Latency p50/p95/p99/max ms: `{metrics['latency_ms']['p50']}` / "
        f"`{metrics['latency_ms']['p95']}` / `{metrics['latency_ms']['p99']}` / "
        f"`{metrics['latency_ms']['max']}`",
        f"- Memory growth MB: `{metrics['memory_growth_mb']}`",
        f"- Expected failure injections handled: `{metrics['expected_failures_handled']}`",
        f"- Trace DB rows/integrity: `{summary['trace_db']['rows']}` / `{summary['trace_db']['integrity']}`",
        f"- Prewarm: `{'on' if summary.get('prewarm', {}).get('enabled') else 'off'}`",
        "",
        "## Scenario Coverage",
        "",
    ]
    for scenario, bucket in sorted(summary["by_scenario"].items()):
        lines.append(
            f"- `{scenario}`: {bucket['passed']}/{bucket['total']} passed, "
            f"{bucket['expected_failures']} expected failure paths"
        )
    lines.extend(
        [
            "",
            "## Remaining Gate",
            "",
            summary["public_saas_gate_reason"],
            "",
        ]
    )
    if summary["failures"]:
        lines.extend(["## Failures", ""])
        for failure in summary["failures"][:20]:
            lines.append(f"- `{failure['scenario']}` #{failure['index']}: {failure['error']}")
        lines.append("")
    (outdir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


async def run_certification(config: CertConfig) -> dict[str, Any]:
    config.outdir.mkdir(parents=True, exist_ok=True)
    trace_db = configure_runtime(config.outdir)
    write_json(config.outdir / "config.json", asdict(config))

    scenarios = build_scenarios(config.include_failure_injections, config.scenario_set)
    prewarm = {"enabled": False, "scenarios": []}
    if config.prewarm:
        prewarm = await prewarm_scenarios(config, scenarios)

    memory_start_mb = peak_rss_mb()
    cpu_start = time.process_time()
    aggregates, wall_seconds, _scenario_count = await execute_load(config, scenarios)
    cpu_seconds = time.process_time() - cpu_start
    memory_end_mb = peak_rss_mb()

    summary = build_summary(
        config=config,
        aggregates=aggregates,
        wall_seconds=wall_seconds,
        cpu_seconds=cpu_seconds,
        memory_start_mb=memory_start_mb,
        memory_end_mb=memory_end_mb,
        trace_db=trace_db,
        prewarm=prewarm,
    )
    write_json(config.outdir / "summary.json", summary)
    write_markdown_summary(config.outdir, summary)
    shutdown_observability()
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d-%H%M%S-load-soak"))
    parser.add_argument(
        "--profile",
        choices=["smoke", "load100", "load500", "load1000", "soak4h", "soak24h"],
        default="smoke",
    )
    parser.add_argument("--outdir", type=Path, default=None)
    parser.add_argument("--total-runs", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--per-run-timeout", type=float, default=30.0)
    parser.add_argument("--target-success-rate", type=float, default=0.99)
    parser.add_argument("--max-memory-growth-mb", type=float, default=256.0)
    parser.add_argument("--no-failure-injections", action="store_true")
    parser.add_argument("--no-prewarm", action="store_true")
    parser.add_argument(
        "--scenario-set",
        choices=["all", "mixed", "lightweight"],
        default="all",
        help="all=mixed+failure coverage, mixed=feature workload only, lightweight=/run-style agent calls",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    defaults = profile_defaults(args.profile)
    total_runs = defaults["total_runs"] if args.total_runs is None else args.total_runs
    concurrency = defaults["concurrency"] if args.concurrency is None else args.concurrency
    duration_seconds = (
        defaults["duration_seconds"] if args.duration_seconds is None else args.duration_seconds
    )
    if total_runs <= 0 and duration_seconds <= 0:
        raise SystemExit("Either --total-runs or --duration-seconds must be positive.")
    if concurrency <= 0:
        raise SystemExit("--concurrency must be positive.")

    outdir = args.outdir or (DEFAULT_EVIDENCE_ROOT / args.run_id)
    config = CertConfig(
        run_id=args.run_id,
        outdir=outdir,
        total_runs=total_runs,
        concurrency=concurrency,
        duration_seconds=duration_seconds,
        per_run_timeout=args.per_run_timeout,
        target_success_rate=args.target_success_rate,
        max_memory_growth_mb=args.max_memory_growth_mb,
        include_failure_injections=not args.no_failure_injections,
        profile=args.profile,
        prewarm=not args.no_prewarm,
        scenario_set=args.scenario_set,
    )
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        summary = loop.run_until_complete(run_certification(config))
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    print(json.dumps(redact_obj(summary), indent=2, sort_keys=True, default=str))
    code = 0 if summary["decision"] == "PASS" else 1
    # Some provider/observability libraries create non-daemon helper threads.
    # The certification artifact has already been flushed, so exit decisively.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
