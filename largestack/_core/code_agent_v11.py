"""CodeAgent v0.11.0 — production code-generating agent.

Closes the gap with HuggingFace's Smolagents (which claims ~30% fewer
LLM calls on GAIA benchmark). Builds on the v0.9.0 ``CodeInterpreter``
sandbox.

Architecture::

    User task
        ↓
    LLM generates Python code that calls tools (as Python functions)
        ↓
    CodeInterpreter executes in subprocess sandbox
        ↓
    stdout / stderr / errors fed back to LLM
        ↓
    LLM decides: done? more code? give up?
        ↓
    repeat up to max_steps

This is a separate module from the legacy ``code_agent`` to avoid
breaking existing imports. Use ``CodeAgentV11`` for new code.
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from largestack._core.citation_sandbox import CodeInterpreter, CodeExecResult

log = logging.getLogger("largestack.code_agent_v11")


SYSTEM_PROMPT = """You are an AI assistant that solves tasks by writing \
Python code. You have access to these tools as Python functions:

{tool_signatures}

Process:
1. Think about the task in plain text inside <thought>...</thought>.
2. Write Python code inside <code>```python\\n...```</code>. The code \
runs in a sandbox; you see its stdout in your next turn.
3. Use `print(...)` to expose intermediate results.
4. When you have the final answer, output <final>...your answer...</final>.

Rules:
- Only use the tools listed above. Allowed modules: {allowed_modules}.
- One <code> block per turn.
- Be concise — code only, no extra explanation outside thought.
"""


@dataclass
class CodeStep:
    """One step of CodeAgent execution."""
    step_number: int
    thought: str = ""
    code: str = ""
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    final_answer: str | None = None


@dataclass
class CodeAgentResult:
    """Full result of CodeAgentV11.run."""
    final_answer: str = ""
    steps: list[CodeStep] = field(default_factory=list)
    total_llm_calls: int = 0
    succeeded: bool = False
    failure_reason: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)


THOUGHT_RE = re.compile(
    r"<thought>(.*?)</thought>", re.DOTALL | re.IGNORECASE,
)
CODE_RE = re.compile(
    r"<code>\s*```(?:python)?\s*\n?(.*?)```\s*</code>",
    re.DOTALL | re.IGNORECASE,
)
CODE_FALLBACK_RE = re.compile(
    r"```(?:python)?\s*\n(.*?)```", re.DOTALL,
)
FINAL_RE = re.compile(
    r"<final>(.*?)</final>", re.DOTALL | re.IGNORECASE,
)


def _parse_response(content: str) -> tuple[str, str, str | None]:
    """Extract (thought, code, final_answer) from LLM output."""
    thought = ""
    m = THOUGHT_RE.search(content)
    if m:
        thought = m.group(1).strip()

    final = None
    m = FINAL_RE.search(content)
    if m:
        final = m.group(1).strip()

    code = ""
    m = CODE_RE.search(content)
    if m:
        code = m.group(1).strip()
    else:
        m = CODE_FALLBACK_RE.search(content)
        if m:
            code = m.group(1).strip()

    return thought, code, final


def _build_tool_signature(tool: Callable) -> str:
    """Build a Python-style signature line for a tool function."""
    schema = getattr(tool, "_tool_schema", {}) or {}
    name = schema.get("name", getattr(tool, "__name__", "tool"))
    description = schema.get("description", "")
    return f"- {name}(...): {description[:120]}"


class CodeAgentV11:
    """Smolagents-style code-generating agent (v0.11.0).

    Args:
        llm_agent: LARGESTACK Agent (or any object with async ``.run(prompt) → result.content``).
        tools: list of tool functions decorated with ``@tool``.
        sandbox: optional ``CodeInterpreter``; default creates one with allowlist.
        max_steps: cap on iterations (default 8).
        allowed_modules: which Python modules code can import.
    """

    def __init__(
        self,
        *,
        llm_agent,
        tools: list[Callable] | None = None,
        sandbox: CodeInterpreter | None = None,
        max_steps: int = 8,
        allowed_modules: list[str] | None = None,
    ):
        self.llm_agent = llm_agent
        self.tools = list(tools or [])
        self.tool_map: dict[str, Callable] = {
            (getattr(t, "_tool_schema", {}) or {}).get(
                "name", getattr(t, "__name__", f"tool{i}"),
            ): t
            for i, t in enumerate(self.tools)
        }
        self.allowed_modules = allowed_modules or [
            "math", "json", "re", "datetime", "collections", "itertools",
            "functools", "statistics",
        ]
        self.sandbox = sandbox or CodeInterpreter(
            timeout_seconds=15,
            allowed_modules=self.allowed_modules,
        )
        self.max_steps = max_steps

    def _system_prompt(self) -> str:
        sigs = "\n".join(_build_tool_signature(t) for t in self.tools)
        return SYSTEM_PROMPT.format(
            tool_signatures=sigs or "(no tools available)",
            allowed_modules=", ".join(self.allowed_modules),
        )

    def _build_user_prompt(self, task: str, history: list[CodeStep]) -> str:
        parts = [f"Task: {task}\n"]
        if history:
            parts.append("\nPrevious steps:")
            for step in history:
                parts.append(f"\n--- Step {step.step_number} ---")
                if step.thought:
                    parts.append(f"Thought: {step.thought}")
                if step.code:
                    parts.append(f"Code:\n{step.code}")
                if step.stdout:
                    parts.append(f"stdout: {step.stdout[:1000]}")
                if step.stderr:
                    parts.append(f"stderr: {step.stderr[:500]}")
                if step.error:
                    parts.append(f"error: {step.error}")
        parts.append(
            "\nNext step: produce <thought>, then either "
            "<code>```python\\n...```</code> or <final>...</final>."
        )
        return "\n".join(parts)

    async def run(self, task: str) -> CodeAgentResult:
        """Run the code-generating loop."""
        history: list[CodeStep] = []
        result = CodeAgentResult()
        system = self._system_prompt()

        for step_num in range(1, self.max_steps + 1):
            user_prompt = self._build_user_prompt(task, history)
            full_prompt = f"{system}\n\n{user_prompt}"

            try:
                resp = await self.llm_agent.run(full_prompt)
                content = (getattr(resp, "content", "") or "").strip()
                result.total_llm_calls += 1
            except Exception as e:
                step = CodeStep(
                    step_number=step_num,
                    error=f"LLM call failed: {e}",
                )
                history.append(step)
                result.failure_reason = f"LLM error: {e}"
                break

            thought, code, final_answer = _parse_response(content)

            step = CodeStep(
                step_number=step_num,
                thought=thought,
                code=code,
                final_answer=final_answer,
            )

            if final_answer is not None:
                history.append(step)
                result.final_answer = final_answer
                result.succeeded = True
                break

            if not code:
                step.error = "no code or final answer produced"
                history.append(step)
                result.failure_reason = step.error
                break

            try:
                exec_result: CodeExecResult = await self.sandbox.execute(code)
                step.stdout = exec_result.stdout
                step.stderr = exec_result.stderr
                if exec_result.timed_out:
                    step.error = "code timed out"
                elif exec_result.returncode != 0:
                    step.error = f"exit code {exec_result.returncode}"
            except Exception as e:
                step.error = f"sandbox error: {e}"

            history.append(step)

        else:
            result.failure_reason = f"hit max_steps ({self.max_steps})"

        result.steps = history
        return result
