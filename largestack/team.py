"""Multi-agent Team — sequential, parallel, with structured context, error recovery, and cost budget."""
from __future__ import annotations
import asyncio, logging, time, uuid
from typing import Any
from largestack._core.context import AgentContext
from largestack.types import AgentResult
from largestack.errors import BudgetExceededError

log = logging.getLogger("largestack.team")

class Team:
    """Coordinate multiple agents with structured context passing.

    Features over basic Team:
    - Structured AgentContext (not string-only)
    - Per-agent error recovery (skip / retry / fallback)
    - Workflow-level cost budget
    - Callbacks on complete/error

    Usage:
        team = Team(
            agents=[researcher, writer, reviewer],
            strategy="sequential",
            cost_budget=2.00,
            on_error="skip",
            retries_per_agent=2,
        )
        result = await team.run("Write a market analysis")
    """
    def __init__(self, agents: list, strategy: str = "sequential", cost_budget: float = 0,
                 on_error: str = "fail", retries_per_agent: int = 1,
                 fallback_map: dict[str, Any] = None, on_complete: Any = None,
                 on_agent_error: Any = None, **kw):
        self.agents = agents
        self.strategy = strategy
        self.cost_budget = cost_budget
        self.on_error = on_error  # "fail" | "skip" | "retry"
        self.retries = retries_per_agent
        self.fallbacks = fallback_map or {}
        self._on_complete = on_complete
        self._on_error = on_agent_error

    async def run(self, task: str, context: AgentContext | None = None, **kw) -> AgentResult:
        ctx = context or AgentContext(task=task, workflow_id=str(uuid.uuid4()))
        if not ctx.task: ctx.task = task

        if self.strategy == "parallel":
            result = await self._parallel(ctx, **kw)
        else:
            result = await self._sequential(ctx, **kw)

        if self._on_complete and result:
            try:
                if asyncio.iscoroutinefunction(self._on_complete): await self._on_complete(result)
                else: self._on_complete(result)
            except Exception as _e: log.warning(f"callback failed: {_e}")
        return result

    async def _sequential(self, ctx: AgentContext, **kw) -> AgentResult:
        last = None
        for agent in self.agents:
            # Cost budget check
            if self.cost_budget > 0 and ctx.total_cost >= self.cost_budget:
                log.warning(f"Workflow cost ${ctx.total_cost:.4f} hit budget ${self.cost_budget:.2f} — stopping")
                break

            ctx.current_agent = agent.name
            prompt = ctx.build_prompt(agent.name) if ctx.history else ctx.task

            result = await self._run_with_recovery(agent, prompt, **kw)
            if result:
                ctx.add_result(agent.name, result)
                last = result
            elif self.on_error == "fail":
                break

        if last:
            last.total_cost = ctx.total_cost
            last.agent_name = f"team({','.join(ctx.history)})"
        return last or AgentResult(content="All agents failed or were skipped.", agent_name="team",
                                    total_cost=ctx.total_cost, status="failed")

    async def _parallel(self, ctx: AgentContext, **kw) -> AgentResult:
        tasks = [self._run_with_recovery(a, ctx.task, **kw) for a in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        contents = []; total_cost = 0; tools = []
        for agent, r in zip(self.agents, results):
            if isinstance(r, Exception):
                contents.append(f"[{agent.name} FAILED: {r}]")
            elif r:
                contents.append(f"--- {agent.name} ---\n{r.content}")
                total_cost += r.total_cost
                tools.extend(r.tool_calls_made)
                ctx.add_result(agent.name, r)

        return AgentResult(content="\n\n".join(contents), agent_name="team_parallel",
            total_cost=total_cost, turns=max((r.turns for r in results if isinstance(r, AgentResult)), default=0),
            tool_calls_made=tools)

    async def _run_with_recovery(self, agent, prompt: str, **kw) -> AgentResult | None:
        """Run agent with retry, fallback, and error handling."""
        last_error = None
        # Ensure at least 1 attempt even if retries=0
        attempts = max(1, self.retries)
        for attempt in range(attempts):
            try:
                return await agent.run(prompt, **kw)
            except Exception as e:
                last_error = e
                log.warning(f"Agent '{agent.name}' attempt {attempt+1}/{attempts} failed: {e}")
                if self._on_error:
                    try:
                        if asyncio.iscoroutinefunction(self._on_error): await self._on_error(agent.name, e)
                        else: self._on_error(agent.name, e)
                    except Exception as cb_err:
                        log.warning(f"on_error callback failed: {cb_err}")

        # Try fallback
        fallback = self.fallbacks.get(agent.name)
        if fallback:
            try:
                log.info(f"Using fallback for '{agent.name}'")
                return await fallback.run(prompt, **kw)
            except Exception as e:
                log.error(f"Fallback for '{agent.name}' also failed: {e}")

        if self.on_error == "skip":
            log.warning(f"Skipping failed agent '{agent.name}'")
            return None
        elif self.on_error == "fail":
            if last_error is None:
                raise RuntimeError(f"Agent '{agent.name}' failed without recoverable error")
            raise last_error
        return None
