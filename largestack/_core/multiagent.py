"""Multi-agent patterns (v0.9.0).

Two production multi-agent orchestration patterns:

- ``Supervisor`` — central orchestrator routes tasks to specialized agents
  by name (LangGraph-style hierarchical multi-agent).
- ``Swarm`` — agents hand off to each other via tool-calling without a
  central supervisor (OpenAI Swarm-inspired).

Both are async, stateless, and integrate with LARGESTACK Agent objects.
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("largestack.multiagent")


# -------------------- Supervisor --------------------

SUPERVISOR_PROMPT = """You are a supervisor coordinating specialized agents.

Available agents:
{agent_descriptions}

For the task below, choose the SINGLE most appropriate agent and route
the task to them. Respond with ONLY the agent name on the first line,
followed by an optional task summary on the next line. If no agent
fits, respond with: FINAL_ANSWER

Format:
<agent_name>
<task summary>

Task: {task}"""

FINISHED_TOKEN = "FINAL_ANSWER"


@dataclass
class SupervisorStep:
    """One step in a supervisor's routing trace."""

    iteration: int
    agent_name: str
    task_summary: str
    result: str = ""


@dataclass
class SupervisorResult:
    """Result of a Supervisor.run() call."""

    final_answer: str
    steps: list[SupervisorStep] = field(default_factory=list)
    iterations: int = 0
    finished_naturally: bool = True


class Supervisor:
    """Hierarchical multi-agent: supervisor routes to specialists.

    Args:
        supervisor_agent: the agent that decides routing.
        agents: dict of {name: agent} — specialists.
        agent_descriptions: dict of {name: description} for the supervisor's prompt.
        max_iterations: cap on routing rounds.

    Usage:
        supervisor = Supervisor(
            supervisor_agent=router,
            agents={"researcher": research_agent, "writer": writer_agent},
            agent_descriptions={
                "researcher": "Gathers facts and citations",
                "writer": "Composes prose from research",
            },
        )
        result = await supervisor.run("Write a brief on AI agents")
    """

    def __init__(
        self,
        supervisor_agent,
        agents: dict[str, Any],
        agent_descriptions: dict[str, str] | None = None,
        *,
        max_iterations: int = 10,
    ):
        if not agents:
            raise ValueError("agents dict cannot be empty")
        self.supervisor = supervisor_agent
        self.agents = agents
        self.descriptions = agent_descriptions or {n: f"the {n} agent" for n in agents}
        self.max_iterations = max_iterations

    def _format_agent_list(self) -> str:
        return "\n".join(f"- {name}: {self.descriptions.get(name, '')}" for name in self.agents)

    async def run(self, task: str, **kw) -> SupervisorResult:
        steps: list[SupervisorStep] = []
        current_context = task
        last_result = ""
        finished_naturally = True

        for iteration in range(1, self.max_iterations + 1):
            prompt = SUPERVISOR_PROMPT.format(
                agent_descriptions=self._format_agent_list(),
                task=current_context,
            )
            try:
                routing_resp = await self.supervisor.run(prompt, **kw)
            except Exception as e:
                last_result = f"supervisor failed: {e}"
                finished_naturally = False
                break
            text = (getattr(routing_resp, "content", "") or "").strip()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines:
                last_result = "supervisor produced empty routing decision"
                finished_naturally = False
                break

            agent_name = lines[0].strip().rstrip(":,")
            task_summary = lines[1] if len(lines) > 1 else current_context

            if FINISHED_TOKEN in agent_name.upper() or agent_name.upper() == FINISHED_TOKEN:
                # Supervisor declares done
                break

            if agent_name not in self.agents:
                last_result = f"supervisor chose unknown agent: {agent_name!r}"
                steps.append(
                    SupervisorStep(
                        iteration=iteration,
                        agent_name=agent_name,
                        task_summary=task_summary,
                        result=last_result,
                    )
                )
                # Try one more time with hint
                current_context = (
                    f"{task}\n\n"
                    f"Note: previous attempt chose unknown agent {agent_name!r}. "
                    f"Choose one of: {list(self.agents.keys())} or {FINISHED_TOKEN}."
                )
                continue

            # Run specialist
            try:
                specialist_resp = await self.agents[agent_name].run(task_summary, **kw)
                last_result = getattr(specialist_resp, "content", "") or ""
            except Exception as e:
                last_result = f"specialist {agent_name} failed: {e}"

            steps.append(
                SupervisorStep(
                    iteration=iteration,
                    agent_name=agent_name,
                    task_summary=task_summary,
                    result=last_result,
                )
            )

            # Update context for next routing decision
            current_context = (
                f"Original task: {task}\n\n"
                f"Latest result from {agent_name}:\n{last_result}\n\n"
                f"Decide if the task is complete (respond {FINISHED_TOKEN}) "
                f"or if more work is needed (route to another agent)."
            )

        return SupervisorResult(
            final_answer=last_result,
            steps=steps,
            iterations=len(steps),
            finished_naturally=finished_naturally,
        )


# -------------------- Swarm --------------------

SWARM_PROMPT = """You are agent {self_name}.

{instructions}

You can hand off to another agent by including in your response:
HANDOFF: <agent_name>
along with any context they need.

Available agents to hand off to: {peers}

If you can complete the task, just answer it. Otherwise hand off."""


HANDOFF_PATTERN = re.compile(r"HANDOFF:\s*(\w+)", re.IGNORECASE)


@dataclass
class SwarmStep:
    """One step in a swarm execution."""

    iteration: int
    from_agent: str
    to_agent: str = ""
    content: str = ""
    handed_off: bool = False


@dataclass
class SwarmResult:
    """Result of a Swarm.run() call."""

    final_answer: str
    final_agent: str
    steps: list[SwarmStep] = field(default_factory=list)
    iterations: int = 0


class Swarm:
    """OpenAI Swarm-style: agents hand off to each other.

    No central supervisor — each agent is wrapped with a "you can hand
    off" preamble and decides for itself if it should pass to a peer.

    Args:
        agents: dict of {name: agent}.
        instructions: dict of {name: instruction prompt} per agent.
        starting_agent: name of agent that handles the initial task.
        max_iterations: cap on handoff chain.
    """

    def __init__(
        self,
        agents: dict[str, Any],
        instructions: dict[str, str] | None = None,
        *,
        starting_agent: str | None = None,
        max_iterations: int = 8,
    ):
        if not agents:
            raise ValueError("agents dict cannot be empty")
        self.agents = agents
        self.instructions = instructions or {n: "" for n in agents}
        self.starting_agent = starting_agent or next(iter(agents))
        self.max_iterations = max_iterations
        if self.starting_agent not in agents:
            raise ValueError(f"starting_agent {starting_agent!r} not in agents")

    def _wrap_prompt(self, agent_name: str, task: str) -> str:
        peers = [n for n in self.agents if n != agent_name]
        return (
            SWARM_PROMPT.format(
                self_name=agent_name,
                instructions=self.instructions.get(agent_name, ""),
                peers=", ".join(peers) or "(none)",
            )
            + f"\n\nTask: {task}"
        )

    async def run(self, task: str, **kw) -> SwarmResult:
        current_agent = self.starting_agent
        current_task = task
        steps: list[SwarmStep] = []
        last_content = ""

        for iteration in range(1, self.max_iterations + 1):
            wrapped = self._wrap_prompt(current_agent, current_task)
            try:
                resp = await self.agents[current_agent].run(wrapped, **kw)
                content = getattr(resp, "content", "") or ""
            except Exception as e:
                content = f"agent {current_agent} failed: {e}"

            handoff_match = HANDOFF_PATTERN.search(content)
            if handoff_match:
                target = handoff_match.group(1)
                # Validate target
                if target == current_agent or target not in self.agents:
                    # Invalid handoff — treat as final answer
                    steps.append(
                        SwarmStep(
                            iteration=iteration,
                            from_agent=current_agent,
                            content=content,
                            handed_off=False,
                        )
                    )
                    last_content = content
                    break
                # Strip the HANDOFF line; pass rest as context
                context_for_next = HANDOFF_PATTERN.sub("", content).strip()
                steps.append(
                    SwarmStep(
                        iteration=iteration,
                        from_agent=current_agent,
                        to_agent=target,
                        content=content,
                        handed_off=True,
                    )
                )
                current_task = (
                    f"You're picking up work from {current_agent}.\n"
                    f"Original task: {task}\n"
                    f"Their context: {context_for_next or '(none)'}"
                )
                current_agent = target
                last_content = context_for_next or content
            else:
                # Final answer (no handoff)
                steps.append(
                    SwarmStep(
                        iteration=iteration,
                        from_agent=current_agent,
                        content=content,
                        handed_off=False,
                    )
                )
                last_content = content
                break

        return SwarmResult(
            final_answer=last_content,
            final_agent=current_agent,
            steps=steps,
            iterations=len(steps),
        )


# -------------------- Structured Chat Agent --------------------

STRUCTURED_CHAT_PROMPT = """You are an agent that takes structured actions.

Available tools:
{tools}

To use a tool, respond ONLY with JSON in this format:
{{"action": "tool_name", "action_input": {{"arg": "value"}}}}

To finish, respond with:
{{"action": "Final Answer", "action_input": "your final response"}}

Question: {input}"""


@dataclass
class StructuredChatResult:
    """Result of a StructuredChatAgent.run() call."""

    final_answer: str
    steps: list[dict] = field(default_factory=list)
    iterations: int = 0


class StructuredChatAgent:
    """Agent that strictly uses JSON-formatted tool calls.

    Useful for non-function-calling LLMs (open source models) where you
    can't rely on the native tool-calling API. The agent prompts the
    LLM to output structured JSON, parses it, runs the tool, feeds the
    result back, and loops until ``Final Answer``.

    Args:
        agent: underlying LARGESTACK Agent (its tools are exposed).
        max_iterations: cap on tool-call rounds.
    """

    def __init__(self, agent, *, max_iterations: int = 8):
        self.agent = agent
        self.max_iterations = max_iterations

    def _format_tools(self) -> str:
        tools = getattr(self.agent, "tools", None) or []
        lines = []
        for t in tools:
            sch = getattr(t, "_tool_schema", None) or {}
            name = sch.get("name", getattr(t, "__name__", "tool"))
            desc = sch.get("description", "")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines) if lines else "(no tools)"

    async def run(self, task: str, **kw) -> StructuredChatResult:
        import json as _json

        steps: list[dict] = []
        # Build tool registry for execution
        tool_map: dict = {}
        for t in getattr(self.agent, "tools", None) or []:
            sch = getattr(t, "_tool_schema", None) or {}
            name = sch.get("name") or getattr(t, "__name__", "")
            if name:
                tool_map[name] = t

        prompt = STRUCTURED_CHAT_PROMPT.format(
            tools=self._format_tools(),
            input=task,
        )
        scratchpad = ""

        for iteration in range(1, self.max_iterations + 1):
            full_input = prompt + scratchpad
            try:
                resp = await self.agent.run(full_input, **kw)
                content = (getattr(resp, "content", "") or "").strip()
            except Exception as e:
                return StructuredChatResult(
                    final_answer=f"agent run failed: {e}",
                    steps=steps,
                    iterations=iteration,
                )

            # Extract JSON from response (LLMs sometimes wrap in code fences)
            content_clean = content
            for fence in ["```json", "```"]:
                content_clean = content_clean.replace(fence, "")
            content_clean = content_clean.strip()

            try:
                parsed = _json.loads(content_clean)
            except _json.JSONDecodeError:
                # LLM didn't follow format
                return StructuredChatResult(
                    final_answer=content,
                    steps=steps,
                    iterations=iteration,
                )

            action = parsed.get("action", "")
            action_input = parsed.get("action_input", "")

            if action == "Final Answer":
                return StructuredChatResult(
                    final_answer=str(action_input),
                    steps=steps,
                    iterations=iteration,
                )

            if action not in tool_map:
                step = {
                    "iteration": iteration,
                    "action": action,
                    "error": f"unknown tool: {action}",
                }
                steps.append(step)
                scratchpad += f"\n\nTool {action!r} not found. Available: {list(tool_map.keys())}"
                continue

            # Execute tool
            try:
                tool_fn = tool_map[action]
                if isinstance(action_input, dict):
                    result = await tool_fn(**action_input)
                else:
                    result = await tool_fn(action_input)
                step = {
                    "iteration": iteration,
                    "action": action,
                    "action_input": action_input,
                    "result": str(result)[:1000],
                }
                steps.append(step)
                scratchpad += (
                    f"\n\nObservation from {action}: {str(result)[:1500]}"
                    f"\n\nThought: now I have new info; respond with next action JSON."
                )
            except Exception as e:
                steps.append(
                    {
                        "iteration": iteration,
                        "action": action,
                        "error": str(e),
                    }
                )
                scratchpad += f"\n\nTool {action} raised: {e}"

        return StructuredChatResult(
            final_answer="max iterations reached without Final Answer",
            steps=steps,
            iterations=self.max_iterations,
        )
