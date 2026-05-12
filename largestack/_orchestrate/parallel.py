"""Parallel fan-out/fan-in orchestration: run agents simultaneously, combine outputs."""
from __future__ import annotations
import asyncio, logging
from typing import Any, Callable
from largestack.types import AgentResult

log = logging.getLogger("largestack.parallel")


class ParallelFanOut:
    """Run all agents on same task in parallel, combine outputs.
    
    Combining strategies:
      - concat: Join all responses with separator
      - best: Longest response (proxy for most detail)
      - vote: Majority vote (for classification tasks)
      - first: Return first to complete
      - custom: User-provided combiner function
    
    Error strategies:
      - fail: Any failure aborts
      - skip: Drop failed agents
      - partial: Include errors in output
    
        fan = ParallelFanOut(
            agents=[gpt, claude, gemini],
            combiner="vote",              # or "concat", "best", "first"
            on_error="skip",
            timeout=30.0,
        )
        result = await fan.run("Is this spam?")
    """
    COMBINERS = ("concat", "best", "vote", "first", "custom")
    
    def __init__(self, agents: list, combiner: str = "concat",
                 separator: str = "\n\n---\n\n",
                 on_error: str = "fail",
                 timeout: float = None,
                 custom_combiner: Callable = None):
        if not agents:
            raise ValueError("ParallelFanOut requires at least one agent")
        if combiner not in self.COMBINERS:
            raise ValueError(f"combiner must be one of {self.COMBINERS}")
        if on_error not in ("fail", "skip", "partial"):
            raise ValueError("on_error must be 'fail', 'skip', or 'partial'")
        
        self.agents = agents
        self.combiner = combiner
        self.separator = separator
        self.on_error = on_error
        self.timeout = timeout
        self.custom_combiner = custom_combiner
    
    async def _run_one(self, agent, task: str, **kw):
        """Run single agent with optional timeout."""
        try:
            if self.timeout:
                return await asyncio.wait_for(agent.run(task, **kw), timeout=self.timeout)
            return await agent.run(task, **kw)
        except Exception as e:
            log.warning(f"Parallel: agent {getattr(agent, 'name', 'unknown')} failed: {e}")
            return e  # Return exception to handle later
    
    async def run(self, task: str, **kw) -> AgentResult:
        """Execute all agents in parallel and combine results."""
        if self.combiner == "first":
            # Return first to complete successfully
            return await self._run_first(task, **kw)
        
        # Run all in parallel
        results = await asyncio.gather(
            *[self._run_one(a, task, **kw) for a in self.agents],
            return_exceptions=False
        )
        
        # Handle errors per strategy
        valid_results = []
        errors = []
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                errors.append((getattr(agent, 'name', 'unknown'), str(result)))
                if self.on_error == "fail":
                    raise RuntimeError(f"Parallel: {errors[-1][0]} failed: {result}") from result
            else:
                valid_results.append(result)
        
        if not valid_results:
            raise RuntimeError(f"Parallel: all {len(self.agents)} agents failed")
        
        # Combine
        content = self._combine(valid_results, errors)
        
        return AgentResult(
            agent_name="parallel",
            content=content,
            total_cost=sum(r.total_cost for r in valid_results),
            total_tokens=sum(r.total_tokens for r in valid_results),
            turns=max((r.turns for r in valid_results), default=1),
            tool_calls_made=[tc for r in valid_results for tc in r.tool_calls_made],
            trace_id="parallel",
        )
    
    async def _run_first(self, task: str, **kw) -> AgentResult:
        """Return first successfully-completing agent's result."""
        tasks = [asyncio.create_task(self._run_one(a, task, **kw)) for a in self.agents]
        try:
            for completed in asyncio.as_completed(tasks):
                result = await completed
                if not isinstance(result, Exception):
                    # Cancel remaining
                    for t in tasks:
                        if not t.done(): t.cancel()
                    return result
        finally:
            for t in tasks:
                if not t.done(): t.cancel()
        
        raise RuntimeError("Parallel 'first': all agents failed")
    
    def _combine(self, results: list, errors: list) -> str:
        """Combine multiple agent outputs per strategy."""
        if not results:
            return ""
        
        if self.combiner == "custom":
            if not self.custom_combiner:
                raise ValueError("combiner='custom' requires custom_combiner function")
            return self.custom_combiner(results)
        
        if self.combiner == "concat":
            parts = [f"[{getattr(r, 'agent_name', f'agent_{i}')}]\n{r.content}" 
                     for i, r in enumerate(results)]
            if self.on_error == "partial" and errors:
                parts.append("\n[Errors]\n" + "\n".join(f"- {name}: {err}" for name, err in errors))
            return self.separator.join(parts)
        
        if self.combiner == "best":
            # Longest response as proxy for most detail/quality
            return max(results, key=lambda r: len(r.content or "")).content
        
        if self.combiner == "vote":
            # Majority vote based on response content (normalized)
            from collections import Counter
            votes = Counter()
            for r in results:
                # Normalize (lowercase, strip, take first 100 chars)
                key = (r.content or "").strip().lower()[:100]
                votes[key] += 1
            most_common = votes.most_common(1)[0][0] if votes else ""
            # Return the first full response matching the winning vote
            for r in results:
                if (r.content or "").strip().lower()[:100] == most_common:
                    return r.content
            return results[0].content
        
        return self.separator.join(r.content for r in results)
