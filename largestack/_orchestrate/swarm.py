"""Swarm orchestration — dynamic agent handoff with routing rules.

Based on OpenAI Swarm pattern: agents can transfer to specialists via
handoff functions. Routing decisions are made by the current agent.
"""
from __future__ import annotations
import asyncio, logging
from typing import Any, Callable
from largestack.types import AgentResult

log = logging.getLogger("largestack.swarm")

class Handoff:
    """A handoff instruction — 'transfer this conversation to agent X'."""
    def __init__(self, target_agent: str, reason: str = "", context: dict = None):
        self.target_agent = target_agent
        self.reason = reason
        self.context = context or {}


class Swarm:
    """Dynamic agent swarm with handoff-based routing.
    
    Agents can transfer control to specialists based on conversation context.
    Each agent has handoff_to list specifying which agents it can route to.
    
        triage = Agent(name="triage", handoff_to=["billing", "tech"])
        billing = Agent(name="billing", handoff_to=["triage"])
        tech = Agent(name="tech", handoff_to=["triage"])
        
        swarm = Swarm(agents=[triage, billing, tech], start="triage")
        result = await swarm.run("I need a refund")
    """
    def __init__(self, agents: list, start: str = None, max_handoffs: int = 10):
        self.agents = {a.name: a for a in agents}
        self.start = start or agents[0].name
        self.max_handoffs = max_handoffs
        self.history: list[dict] = []
    
    def _detect_handoff(self, content: str) -> str | None:
        """Parse agent output for handoff markers.
        Format: [HANDOFF:agent_name] or [TRANSFER_TO:agent_name]
        """
        import re
        patterns = [
            r"\[HANDOFF:(\w+)\]",
            r"\[TRANSFER_TO:(\w+)\]",
            r"transfer(?:ring)? to (\w+)",
            r"routing to (\w+) specialist",
        ]
        for p in patterns:
            m = re.search(p, content, re.IGNORECASE)
            if m:
                target = m.group(1).lower()
                if target in self.agents:
                    return target
        return None
    
    async def run(self, task: str, session_id: str = None) -> AgentResult:
        current = self.start
        handoffs = 0
        total_cost = 0.0
        total_tokens = 0
        tool_calls = []
        
        while handoffs < self.max_handoffs:
            agent = self.agents.get(current)
            if not agent:
                log.error(f"Swarm: unknown agent '{current}'")
                break
            
            log.info(f"Swarm: running {current} (handoff #{handoffs})")
            
            # Inject swarm context
            swarm_task = task
            if handoffs > 0:
                # Not first agent — include handoff history
                swarm_task = (f"[Context: previous agent routed to you. "
                              f"Previous conversation:\n{self._format_history()}]\n\n{task}")
            
            result = await agent.run(swarm_task)
            total_cost += result.total_cost
            total_tokens += result.total_tokens
            tool_calls.extend(result.tool_calls_made)
            self.history.append({
                "agent": current,
                "content": result.content,
                "cost": result.total_cost,
            })
            
            # Check for handoff
            target = self._detect_handoff(result.content)
            if target and target != current and target in self.agents:
                # Check if current agent is allowed to hand off to target
                allowed = getattr(agent, 'handoff_to', None)
                if allowed is None or target in allowed:
                    log.info(f"Swarm: {current} → {target}")
                    current = target
                    handoffs += 1
                    continue
                else:
                    log.warning(f"Swarm: {current} tried to handoff to {target} but not in allowlist")
            
            # No handoff — return final result
            return AgentResult(
                agent_name="swarm",
                content=result.content,
                total_cost=total_cost,
                total_tokens=total_tokens,
                turns=handoffs + 1,
                tool_calls_made=tool_calls,
                trace_id=result.trace_id,
            )
        
        log.warning(f"Swarm: hit max_handoffs={self.max_handoffs}")
        return AgentResult(
            agent_name="swarm",
            content=self.history[-1]["content"] if self.history else "Max handoffs exceeded",
            total_cost=total_cost,
            total_tokens=total_tokens,
            turns=handoffs,
            tool_calls_made=tool_calls,
            trace_id="swarm",
        )
    
    def _format_history(self) -> str:
        return "\n".join(f"[{h['agent']}]: {h['content'][:200]}" for h in self.history[-3:])
