"""Agent reasoning patterns (v0.8.0).

Production-tested reasoning patterns layered on top of regular Agents.
None of these change the underlying Agent — they're orchestrators that
call agent.run() with structured prompts.

Patterns:
- ``ChainOfThought`` — prompt agent to reason step by step before answer
- ``SelfAsk`` — decompose into sub-questions, answer each, synthesize
- ``PlanAndExecute`` — planner produces a plan, executor runs each step
- ``Reflexion`` — agent attempts → critic critiques → agent revises (loop)
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.reasoning")


# -------------------- Chain-of-Thought --------------------

COT_PROMPT_PREFIX = """Think step by step. Reason through the problem \
before giving your final answer. Use this format:

Reasoning:
<your step-by-step reasoning>

Final Answer:
<your concise answer>

Question: """


class ChainOfThought:
    """Wrap an agent so every run gets explicit step-by-step reasoning.

    Usage:
        cot = ChainOfThought(agent)
        result = await cot.run("What is 17 * 23?")
        # result.content has both reasoning and final answer
        # result.final_answer has just the answer
    """

    def __init__(self, agent):
        self.agent = agent

    async def run(self, task: str, **kw):
        prompt = COT_PROMPT_PREFIX + task
        result = await self.agent.run(prompt, **kw)
        # Extract just the final answer if format was followed
        text = getattr(result, "content", "") or ""
        m = re.search(r"Final Answer:\s*(.+?)(?:\Z|\n\n)", text, re.DOTALL)
        final = m.group(1).strip() if m else text.strip()
        # Attach as attribute on the result
        try:
            setattr(result, "final_answer", final)
            setattr(result, "reasoning", text[: m.start()].strip() if m else "")
        except Exception:
            pass  # AgentResult may be frozen; not critical
        return result


# -------------------- Self-Ask --------------------

SELF_ASK_PROMPT = """You are answering a complex question by decomposing \
it into simpler sub-questions, answering each, then combining.

For the question below:
1. List 2-4 sub-questions needed to answer it.
2. Answer each sub-question briefly.
3. Synthesize the final answer from the sub-answers.

Format your response EXACTLY as:

Sub-questions:
- Q1: ...
- Q2: ...
...

Sub-answers:
- A1: ...
- A2: ...
...

Final Answer:
<combined answer>

Question: {question}"""


@dataclass
class SelfAskResult:
    """Result of a Self-Ask run."""
    sub_questions: list[str] = field(default_factory=list)
    sub_answers: list[str] = field(default_factory=list)
    final_answer: str = ""
    raw: str = ""


class SelfAsk:
    """Self-Ask reasoning: decompose → answer parts → synthesize.

    Useful for compound questions like "Who was president when X happened?"
    where the LLM needs to first determine when X happened.
    """

    def __init__(self, agent):
        self.agent = agent

    async def run(self, question: str, **kw) -> SelfAskResult:
        prompt = SELF_ASK_PROMPT.format(question=question)
        result = await self.agent.run(prompt, **kw)
        text = getattr(result, "content", "") or ""

        sq = self._extract_section(text, "Sub-questions:", "Sub-answers:")
        sa = self._extract_section(text, "Sub-answers:", "Final Answer:")
        fa_match = re.search(r"Final Answer:\s*(.+)$", text, re.DOTALL)
        final = fa_match.group(1).strip() if fa_match else text.strip()

        return SelfAskResult(
            sub_questions=self._parse_bullets(sq),
            sub_answers=self._parse_bullets(sa),
            final_answer=final,
            raw=text,
        )

    @staticmethod
    def _extract_section(text: str, start: str, end: str) -> str:
        s_idx = text.find(start)
        if s_idx < 0:
            return ""
        e_idx = text.find(end, s_idx + len(start))
        if e_idx < 0:
            return text[s_idx + len(start):]
        return text[s_idx + len(start): e_idx]

    @staticmethod
    def _parse_bullets(section: str) -> list[str]:
        items = []
        for line in section.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^[-*+]\s*(?:Q\d+:|A\d+:)?\s*(.+)$", line)
            if m:
                items.append(m.group(1).strip())
        return items


# -------------------- Plan-and-Execute --------------------

PLANNER_PROMPT = """You are a planner. Decompose the goal into 3-7 \
concrete sequential steps. Each step should be small and verifiable.

Goal: {goal}

Output ONLY a numbered list of steps. No preamble, no explanation."""

EXECUTOR_PROMPT = """You are executing step {step_num} of a plan.

Plan so far:
{plan_context}

Outputs from previous steps:
{prior_outputs}

Current step: {current_step}

Execute this step and output ONLY the result. Do not announce what \
you're doing — just produce the deliverable for this step."""


@dataclass
class PlanStep:
    """One step in a plan with its execution result."""
    number: int
    description: str
    result: str = ""


@dataclass
class PlanAndExecuteResult:
    """Result of a Plan-and-Execute run."""
    plan: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    final_answer: str = ""


class PlanAndExecute:
    """Plan-and-Execute pattern: planner agent → executor agent → synthesize.

    Args:
        planner: Agent used to decompose the goal.
        executor: Agent that runs each plan step (can be same as planner).
        max_steps: cap on plan length to prevent runaway.
    """

    def __init__(self, planner, executor=None, *, max_steps: int = 10):
        self.planner = planner
        self.executor = executor or planner
        self.max_steps = max_steps

    async def run(self, goal: str, **kw) -> PlanAndExecuteResult:
        # 1. Generate plan
        plan_result = await self.planner.run(
            PLANNER_PROMPT.format(goal=goal), **kw
        )
        plan_text = getattr(plan_result, "content", "") or ""
        steps_raw = self._parse_plan(plan_text)[: self.max_steps]
        if not steps_raw:
            return PlanAndExecuteResult(
                plan=[], steps=[],
                final_answer="planner produced no usable steps",
            )

        # 2. Execute each step sequentially, threading outputs forward
        executed: list[PlanStep] = []
        for i, step_desc in enumerate(steps_raw, 1):
            prior = "\n".join(
                f"Step {s.number} ({s.description}): {s.result[:300]}"
                for s in executed
            ) or "(no prior steps)"
            plan_context = "\n".join(
                f"{j+1}. {s}" for j, s in enumerate(steps_raw)
            )
            exec_prompt = EXECUTOR_PROMPT.format(
                step_num=i,
                plan_context=plan_context,
                prior_outputs=prior,
                current_step=step_desc,
            )
            try:
                er = await self.executor.run(exec_prompt, **kw)
                output = getattr(er, "content", "") or ""
            except Exception as e:
                log.warning(f"PlanAndExecute step {i} failed: {e}")
                output = f"[step failed: {e}]"
            executed.append(PlanStep(number=i, description=step_desc, result=output))

        final = executed[-1].result if executed else ""
        return PlanAndExecuteResult(
            plan=steps_raw, steps=executed, final_answer=final,
        )

    @staticmethod
    def _parse_plan(text: str) -> list[str]:
        steps = []
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"^\d+[.)]\s*(.+)$", line)
            if m:
                steps.append(m.group(1).strip())
        # If no numbered list found, try bullets
        if not steps:
            for line in text.splitlines():
                line = line.strip()
                m = re.match(r"^[-*+]\s+(.+)$", line)
                if m:
                    steps.append(m.group(1).strip())
        return steps


# -------------------- Reflexion --------------------

REFLEXION_CRITIC_PROMPT = """You are critiquing the answer below for \
correctness, completeness, and clarity. List specific problems and \
suggest concrete improvements.

If the answer is good enough, output exactly: "APPROVED"

Question: {question}

Answer:
{answer}

Critique:"""

REFLEXION_REVISE_PROMPT = """Revise your previous answer based on the \
critique. Address each point raised.

Question: {question}

Your previous answer:
{previous_answer}

Critique:
{critique}

Revised answer:"""


@dataclass
class ReflexionResult:
    """Result of a Reflexion loop."""
    iterations: int = 0
    final_answer: str = ""
    history: list[dict] = field(default_factory=list)


class Reflexion:
    """Reflexion: agent → critic → revise → critic → ... (with limit).

    Stops when the critic outputs "APPROVED" or after ``max_iterations``.

    Args:
        agent: the agent producing answers.
        critic: the agent critiquing them (often the same).
        max_iterations: cap on revision rounds.
    """

    def __init__(self, agent, critic=None, *, max_iterations: int = 3):
        self.agent = agent
        self.critic = critic or agent
        self.max_iterations = max_iterations

    async def run(self, question: str, **kw) -> ReflexionResult:
        # Initial attempt
        first = await self.agent.run(question, **kw)
        answer = getattr(first, "content", "") or ""

        history: list[dict] = [{"role": "answer", "iteration": 0, "content": answer}]

        for iteration in range(1, self.max_iterations + 1):
            # Critic
            critique_result = await self.critic.run(
                REFLEXION_CRITIC_PROMPT.format(
                    question=question, answer=answer
                ),
                **kw,
            )
            critique = getattr(critique_result, "content", "") or ""
            history.append({"role": "critique", "iteration": iteration, "content": critique})

            if "APPROVED" in critique.upper().split():  # word-bounded match
                break
            # word-bounded check that doesn't false-match "APPROVEDLY"
            if re.search(r"\bAPPROVED\b", critique):
                break

            # Revise
            revise_result = await self.agent.run(
                REFLEXION_REVISE_PROMPT.format(
                    question=question,
                    previous_answer=answer,
                    critique=critique,
                ),
                **kw,
            )
            answer = getattr(revise_result, "content", "") or answer
            history.append({"role": "answer", "iteration": iteration, "content": answer})

        return ReflexionResult(
            iterations=iteration if 'iteration' in dir() else 0,
            final_answer=answer,
            history=history,
        )
