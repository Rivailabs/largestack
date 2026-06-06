"""Debate orchestration — multi-agent critique and consensus.

Pattern from "Improving Factuality and Reasoning in Language Models through
Multiagent Debate" (Du et al., 2023). Agents argue, critique, and converge.
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
from largestack.types import AgentResult

log = logging.getLogger("largestack.debate")

class DebateRound:
    def __init__(self, round_num: int, responses: dict[str, str],
                 cost: float = 0.0, tokens: int = 0):
        self.round = round_num
        self.responses = responses  # agent_name → response
        self.cost = cost            # summed per-agent cost for this round
        self.tokens = tokens
    
    def format_for_critique(self, exclude: str = None) -> str:
        """Format responses for other agents to critique."""
        lines = []
        for name, resp in self.responses.items():
            if name != exclude:
                lines.append(f"[Agent {name}'s view]: {resp}")
        return "\n\n".join(lines)


class Debate:
    """Multi-agent debate with configurable rounds and consensus check.
    
    Strategies:
    - 'rounds': N rounds of critique-and-revise
    - 'consensus': debate until agents agree (bounded)
    - 'judge': final agent evaluates and picks winner
    
        agents = [optimist, pessimist, pragmatist]
        debate = Debate(agents, rounds=3, strategy="judge", judge=moderator)
        result = await debate.run("Should we invest in AI?")
    """
    def __init__(self, agents: list, rounds: int = 3, strategy: str = "rounds",
                 judge=None, consensus_threshold: float = 0.8):
        if len(agents) < 2:
            raise ValueError("Debate requires at least 2 agents")
        self.agents = agents
        self.rounds = rounds
        self.strategy = strategy
        self.judge = judge
        self.consensus_threshold = consensus_threshold
        self.history: list[DebateRound] = []
    
    async def _run_round(self, round_num: int, task: str) -> DebateRound:
        """Run one debate round — all agents respond in parallel."""
        if round_num == 0:
            # Initial round — each agent answers independently
            tasks = [a.run(task) for a in self.agents]
        else:
            # Subsequent rounds — include previous round's other agents' responses
            prev = self.history[-1]
            tasks = []
            for a in self.agents:
                critique_prompt = (
                    f"Original question: {task}\n\n"
                    f"Other agents' views in the previous round:\n"
                    f"{prev.format_for_critique(exclude=a.name)}\n\n"
                    f"Critique the other views and refine your own answer."
                )
                tasks.append(a.run(critique_prompt))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        responses = {}
        round_cost = 0.0; round_tokens = 0
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                log.error(f"Debate: {agent.name} failed in round {round_num}: {result}")
                responses[agent.name] = f"[ERROR: {result}]"
            else:
                responses[agent.name] = result.content
                # v1.1.1: accumulate per-agent cost/tokens — these were discarded,
                # so a multi-agent multi-round debate reported ~0 cost.
                round_cost += float(getattr(result, "total_cost", 0.0) or 0.0)
                round_tokens += int(getattr(result, "total_tokens", 0) or 0)

        return DebateRound(round_num, responses, cost=round_cost, tokens=round_tokens)
    
    def _check_consensus(self, round: DebateRound) -> bool:
        """Simple consensus check — look for agreement keywords."""
        responses = list(round.responses.values())
        if not responses: return False
        
        agree_words = ["agree", "concur", "same", "aligned", "correct"]
        disagree_words = ["disagree", "however", "but", "contrary"]
        
        scores = []
        for r in responses:
            text = r.lower()
            agree_count = sum(1 for w in agree_words if w in text)
            disagree_count = sum(1 for w in disagree_words if w in text)
            scores.append(agree_count - disagree_count)
        
        # Most agents show agreement
        return sum(s > 0 for s in scores) / len(scores) >= self.consensus_threshold
    
    async def run(self, task: str) -> AgentResult:
        total_cost = 0.0
        total_tokens = 0
        
        # Run all rounds
        for r in range(self.rounds):
            round = await self._run_round(r, task)
            self.history.append(round)
            total_cost += getattr(round, "cost", 0.0)
            total_tokens += getattr(round, "tokens", 0)

            if self.strategy == "consensus" and self._check_consensus(round):
                log.info(f"Debate: consensus reached at round {r}")
                break
        
        # Synthesize final answer
        if self.strategy == "judge" and self.judge:
            last_round = self.history[-1]
            judge_prompt = (
                f"Question: {task}\n\n"
                f"Agents debated. Here are their final positions:\n"
                f"{last_round.format_for_critique()}\n\n"
                f"Synthesize the best answer by evaluating each view critically."
            )
            final = await self.judge.run(judge_prompt)
            total_cost += float(getattr(final, "total_cost", 0.0) or 0.0)
            total_tokens += int(getattr(final, "total_tokens", 0) or 0)
            final_content = final.content
        else:
            # Concatenate final positions
            last = self.history[-1]
            final_content = "\n\n".join(
                f"[{name}]: {resp}" for name, resp in last.responses.items())
        
        return AgentResult(
            agent_name="debate",
            content=final_content,
            total_cost=total_cost,
            total_tokens=total_tokens,
            turns=len(self.history),
            tool_calls_made=[],
            trace_id="debate",
        )
