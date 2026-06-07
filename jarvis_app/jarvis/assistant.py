"""The Jarvis assistant — a DEMO bundle built on Largestack's stable Agent API.

This is an example/starter, not a production product: it wires a Largestack Agent
with tools, PII + injection guardrails, persistent memory, per-request cost
budgeting and retries, and a safety-first system prompt. For a production build,
migrate to the typed decorator API (`largestack.decorators.Agent`) per AGENTS.md.
"""

from __future__ import annotations

from pydantic import BaseModel

from largestack import Agent, Guardrails, InjectionGuard, PIIGuard

from .config import COST_BUDGET, MAX_TURNS, MODEL
from .tools import ALL_TOOLS


class JarvisReply(BaseModel):
    """Typed result of one Jarvis turn (no raw dicts)."""

    reply: str
    tools_used: list[str] = []
    tools_failed: list[str] = []
    turn_cost: float = 0.0
    total_cost: float = 0.0
    trace_id: str | None = None


INSTRUCTIONS = """You are Jarvis, a careful and friendly personal assistant.

Use your tools to take REAL actions instead of guessing:
- take_note / list_notes for the user's notebook
- remember_fact / recall_fact for facts to keep (deadlines, preferences, etc.)
- calculate for arithmetic
- list_directory to look at files (read-only)
- search_knowledge to answer "what can you do / how do you work" type questions

Safety rules (never break these):
- For ANY risky or irreversible action — deleting or moving files, sending email
  or messages, payments, publishing, or production/deploy changes — you MUST call
  request_approval and tell the user it is waiting for their approval. Never claim
  you performed such an action.
- Never invent the contents of notes or remembered facts; read them with the tools.
- When you use information from search_knowledge, mention the source file.

Keep answers concise, practical, and friendly.
"""


def build_agent() -> Agent:
    """Construct the configured Jarvis agent."""
    guardrails = Guardrails(guards=[PIIGuard(action="warn"), InjectionGuard()])
    return Agent(
        name="jarvis",
        llm=MODEL,
        instructions=INSTRUCTIONS,
        tools=ALL_TOOLS,
        guardrails=guardrails,
        cost_budget=COST_BUDGET,
        max_turns=MAX_TURNS,
        retries=2,
    )


class Jarvis:
    """Thin wrapper that runs the agent and tracks cumulative cost."""

    def __init__(self) -> None:
        self.agent = build_agent()
        self.total_cost = 0.0

    async def ask(self, message: str, timeout: int = 120) -> JarvisReply:
        result = await self.agent.run(message, timeout=timeout)
        turn_cost = float(getattr(result, "total_cost", 0.0) or 0.0)
        self.total_cost += turn_cost
        return JarvisReply(
            reply=result.content,
            tools_used=list(getattr(result, "tool_calls_made", [])),
            tools_failed=list(getattr(result, "tool_calls_failed", [])),
            turn_cost=turn_cost,
            total_cost=self.total_cost,
            trace_id=getattr(result, "trace_id", None),
        )

    async def close(self) -> None:
        try:
            await self.agent.aclose()
        except Exception:  # noqa: BLE001
            pass
