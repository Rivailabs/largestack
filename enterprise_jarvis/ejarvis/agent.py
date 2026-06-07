"""The enterprise agent: typed decorator API + RBAC-gated, audited tools,
guardrails, multi-tenant scoping, cost/trace observability, and typed outputs.
"""

from __future__ import annotations

import ast
import operator

from pydantic import BaseModel

from largestack import Guardrails, InjectionGuard, PIIGuard
from largestack.decorators import Agent, RunContext

from . import knowledge, rbac, store
from .config import COST_BUDGET, MODEL
from .context import Principal
from .schemas import TicketTriage

SYSTEM = """You are an enterprise assistant for a company's employees.

Rules:
- Use your tools to take real actions (search the knowledge base, remember/recall
  facts, calculate, raise tickets). Do not guess facts you can look up.
- When you answer from the knowledge base, cite the source file in brackets.
- For anything risky or irreversible (deleting/sending/paying/publishing/deploying,
  or HR/security decisions), call submit_approval and tell the user it is pending —
  never claim you performed such an action.
- If a tool replies 'PERMISSION DENIED', tell the user they lack the required role.
Keep answers concise and professional."""


# ---- Bounded calculator (no DoS) -------------------------------------------

_MAX_LEN, _MAX_DEPTH, _MAX_MAG, _MAX_POW = 120, 25, 10**12, 100


def _guarded_pow(base, exp):
    if abs(exp) > _MAX_POW or abs(base) > _MAX_MAG:
        raise ValueError("number too large")
    return operator.pow(base, exp)


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _guarded_pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval(node, depth: int = 0):
    if depth > _MAX_DEPTH:
        raise ValueError("expression too deeply nested")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if abs(node.value) > _MAX_MAG:
            raise ValueError("number too large")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left, depth + 1), _eval(node.right, depth + 1))
    raise ValueError("only basic arithmetic is allowed")


def safe_calc(expression: str) -> str:
    if len(expression) > _MAX_LEN:
        return "Error: expression too long"
    try:
        result = _eval(ast.parse(expression, mode="eval"))
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"
    if isinstance(result, (int, float)) and abs(result) > _MAX_MAG:
        return "Error: result too large"
    return str(result)


# ---- Reply model -----------------------------------------------------------


class EnterpriseReply(BaseModel):
    reply: str
    cost: float = 0.0
    trace_id: str | None = None


def _guardrails() -> Guardrails:
    return Guardrails(guards=[PIIGuard(action="warn"), InjectionGuard()])


def _gate(ctx: RunContext[Principal], action: str) -> str | None:
    """Return a denial string (and audit it) if the role can't do `action`."""
    p = ctx.deps
    if not rbac.can(p.role, action):
        store.audit(p.tenant, p.user, p.role, "permission_denied", action)
        return f"PERMISSION DENIED: role '{p.role}' may not '{action}'."
    return None


def build_agent() -> Agent:
    """Build the enterprise agent with RBAC-gated, audited, typed tools."""
    agent = Agent[Principal, str](
        MODEL,
        deps_type=Principal,
        instructions=SYSTEM,
        cost_budget=COST_BUDGET,
        guardrails=_guardrails(),
        retries=1,
    )

    @agent.tool
    async def kb_search(ctx: RunContext[Principal], query: str) -> str:
        """Search the company knowledge base; returns cited snippets or INSUFFICIENT_EVIDENCE."""
        if d := _gate(ctx, "kb_search"):
            return d
        hits = knowledge.search(query)
        store.audit(ctx.deps.tenant, ctx.deps.user, ctx.deps.role, "kb_search", query)
        if not hits:
            return "INSUFFICIENT_EVIDENCE: nothing relevant in the knowledge base."
        return "\n".join(f"[{src}] {snip}" for src, snip in hits)

    @agent.tool
    async def remember(ctx: RunContext[Principal], key: str, value: str) -> str:
        """Remember a fact for this tenant (e.g. a deadline or preference)."""
        if d := _gate(ctx, "remember"):
            return d
        store.set_fact(ctx.deps.tenant, key, value)
        store.audit(ctx.deps.tenant, ctx.deps.user, ctx.deps.role, "remember", f"{key}={value}")
        return f"Remembered: {key} = {value}"

    @agent.tool
    async def recall(ctx: RunContext[Principal], key: str) -> str:
        """Recall a previously remembered fact for this tenant."""
        if d := _gate(ctx, "recall"):
            return d
        val = store.get_fact(ctx.deps.tenant, key)
        return val if val is not None else f"No fact remembered for '{key}'."

    @agent.tool
    async def calculate(ctx: RunContext[Principal], expression: str) -> str:
        """Evaluate a bounded arithmetic expression (safe against huge inputs)."""
        if d := _gate(ctx, "calculate"):
            return d
        return safe_calc(expression)

    @agent.tool
    async def submit_approval(ctx: RunContext[Principal], action: str, details: str = "") -> str:
        """Record a risky action as a PENDING approval (never executes it)."""
        if d := _gate(ctx, "submit_approval"):
            return d
        rid = store.add_approval(ctx.deps.tenant, ctx.deps.user, action, details)
        store.audit(ctx.deps.tenant, ctx.deps.user, ctx.deps.role, "submit_approval", action)
        return f"Approval #{rid} recorded as PENDING — not executed. A human must approve it."

    @agent.tool
    async def list_approvals(ctx: RunContext[Principal]) -> str:
        """List pending approvals for this tenant."""
        if d := _gate(ctx, "list_approvals"):
            return d
        items = [a for a in store.get_approvals(ctx.deps.tenant) if a["status"] == "pending"]
        if not items:
            return "No pending approvals."
        return "\n".join(f"#{a['id']} {a['action']} (by {a['user']})" for a in items)

    @agent.tool
    async def raise_ticket(ctx: RunContext[Principal], subject: str, body: str) -> str:
        """Open a support ticket for this tenant."""
        if d := _gate(ctx, "raise_ticket"):
            return d
        tid = store.add_ticket(ctx.deps.tenant, ctx.deps.user, subject, body)
        store.audit(ctx.deps.tenant, ctx.deps.user, ctx.deps.role, "raise_ticket", subject)
        return f"Opened ticket {tid}: {subject}"

    @agent.tool
    async def read_audit(ctx: RunContext[Principal]) -> str:
        """Read the recent audit log (admin only)."""
        if d := _gate(ctx, "read_audit"):
            return d
        rows = store.read_audit(ctx.deps.tenant, limit=10)
        return (
            "\n".join(f"{r['at']} {r['user']}/{r['role']} {r['event']} {r['detail']}" for r in rows)
            or "(empty)"
        )

    return agent


def build_triage_agent() -> Agent:
    """A typed-output agent that returns a validated TicketTriage (no raw text)."""
    return Agent[Principal, TicketTriage](
        MODEL,
        deps_type=Principal,
        output_type=TicketTriage,
        instructions="Classify the employee request into the TicketTriage schema.",
        cost_budget=COST_BUDGET,
        guardrails=_guardrails(),
    )


class EnterpriseJarvis:
    """Per-session orchestrator bound to a signed-in Principal."""

    def __init__(self, principal: Principal) -> None:
        self.principal = principal
        self.agent = build_agent()
        self._triage = build_triage_agent()
        self.total_cost = 0.0

    async def ask(self, message: str) -> EnterpriseReply:
        result = await self.agent.run(message, deps=self.principal)
        cost = float(getattr(result, "cost", 0.0) or 0.0)
        self.total_cost += cost
        # Observability: audit the run itself.
        store.audit(
            self.principal.tenant,
            self.principal.user,
            self.principal.role,
            "agent_run",
            message[:120],
        )
        return EnterpriseReply(
            reply=str(result.output),
            cost=cost,
            trace_id=getattr(result, "trace_id", None),
        )

    async def triage(self, request: str) -> TicketTriage:
        """Return a validated TicketTriage for a request."""
        result = await self._triage.run(request, deps=self.principal)
        return result.output
