"""Public orchestration facade for LARGESTACK.

The lower-level package ships Team, Workflow, Router, Supervisor, Swarm,
parallel, sequential, DAG, state-machine, debate, and map-reduce patterns.
This facade gives developers one stable entry point for the most common
production automation shapes without forcing them to import internal modules.

Use this when you want a clean application-level API:

    from largestack import Agent, Orchestrator

    orch = Orchestrator(strategy="dag", agents=[extractor, validator], flow=[("extractor", "validator")])
    result = await orch.run({"task": "extract and validate"})

For highly customized orchestration, the underlying modules remain available.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass
class OrchestratorResult:
    """Normalized result returned by :class:`Orchestrator`.

    Attributes:
        output: The final user-facing output.
        strategy: Strategy used for the run.
        trace_id: Trace identifier if the underlying runtime returned one.
        total_cost: Aggregated LLM/tool cost when available.
        steps: Normalized step list for supervisor/swarm/workflow-like runs.
        metadata: Strategy-specific details such as router stats.
        raw: The original lower-level result object.
    """

    output: Any
    strategy: str
    trace_id: str | None = None
    total_cost: float = 0.0
    steps: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class Orchestrator:
    """Run many agents through one public orchestration API.

    Stable public strategies:

    - ``sequential``: run agents one after another with :class:`largestack.Team`.
    - ``parallel``: run agents concurrently with :class:`largestack.Team`.
    - ``dag``: dependency-based workflow with :class:`largestack.Workflow`.
    - ``state_machine``: state-machine workflow with :class:`largestack.Workflow`.
    - ``router``: classify then dispatch to a specialist route.
    - ``supervisor``: central supervisor agent routes work to specialists.
    - ``map_reduce``: process many items with a mapper, then synthesize with a reducer.

    This class intentionally keeps the public contract small. Advanced swarm,
    debate, saga, and custom graph primitives remain available under their
    dedicated modules while their API shapes evolve.
    """

    PUBLIC_STRATEGIES = {
        "sequential",
        "parallel",
        "dag",
        "state_machine",
        "router",
        "supervisor",
        "map_reduce",
    }

    def __init__(
        self,
        *,
        name: str = "orchestrator",
        strategy: str = "sequential",
        agents: Iterable[Any] | Mapping[str, Any] | None = None,
        flow: list[tuple[str, str]] | None = None,
        routes: Mapping[str, Any] | None = None,
        classifier: Any | None = None,
        supervisor_agent: Any | None = None,
        mapper: Any | None = None,
        reducer: Any | None = None,
        default_route: str | None = None,
        cost_budget: float = 0.0,
        on_error: str = "fail",
        retries_per_agent: int = 1,
        max_iterations: int = 10,
        max_concurrency: int = 10,
        durable: bool = False,
        thread_id: str | None = None,
        checkpoint_db_path: str | None = None,
        resume_completed: bool = False,
    ):
        strategy = strategy.lower().replace("-", "_")
        if strategy not in self.PUBLIC_STRATEGIES:
            raise ValueError(
                f"Unsupported public orchestration strategy: {strategy!r}. "
                f"Supported strategies: {', '.join(sorted(self.PUBLIC_STRATEGIES))}."
            )

        self.name = name
        self.strategy = strategy
        self.agent_map: dict[str, Any] = {}
        if isinstance(agents, Mapping):
            self.agent_map = dict(agents)
            self.agents = list(self.agent_map.values())
        else:
            self.agents = list(agents or [])
            self.agent_map = {
                getattr(agent, "name", str(i)): agent for i, agent in enumerate(self.agents)
            }

        self.flow = flow or []
        self.routes = dict(routes or {})
        self.classifier = classifier
        self.supervisor_agent = supervisor_agent
        self.mapper = mapper
        self.reducer = reducer
        self.default_route = default_route
        self.cost_budget = cost_budget
        self.on_error = on_error
        self.retries_per_agent = retries_per_agent
        self.max_iterations = max_iterations
        self.max_concurrency = max_concurrency
        self.durable = durable
        self.thread_id = thread_id or name
        self.checkpoint_db_path = checkpoint_db_path
        self.resume_completed = resume_completed

    @classmethod
    def supported_strategies(cls) -> tuple[str, ...]:
        """Return the stable public orchestration strategies."""
        return tuple(sorted(cls.PUBLIC_STRATEGIES))

    def describe(self) -> dict[str, Any]:
        """Return a small machine-readable description for dashboards/docs."""
        return {
            "name": self.name,
            "strategy": self.strategy,
            "agents": list(self.agent_map.keys()),
            "routes": list((self.routes or self.agent_map).keys()),
            "flow": list(self.flow),
            "cost_budget": self.cost_budget,
        }

    def run_sync(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        """Synchronous wrapper around :meth:`run` for scripts and notebooks."""
        return asyncio.run(self.run(task, **kwargs))

    def _checkpoint_manager(self):
        from largestack._state.checkpoint import CheckpointManager
        if self.checkpoint_db_path:
            return CheckpointManager(self.checkpoint_db_path)
        return CheckpointManager()

    def _save_checkpoint(self, step: str, state: dict[str, Any]) -> None:
        if not self.durable:
            return
        try:
            self._checkpoint_manager().save(self.thread_id, step, state)
        except Exception:
            # Checkpointing must not hide the real application result. Production
            # users can enforce durable failure by running dedicated checkpoint tests.
            pass

    def load_checkpoint(self) -> tuple[str, dict[str, Any]] | None:
        """Load latest durable checkpoint for this orchestrator/thread."""
        if not self.durable:
            return None
        return self._checkpoint_manager().load_latest(self.thread_id)

    async def run(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        """Run the configured orchestration pattern.

        When ``durable=True``, LARGESTACK stores run-level checkpoints before
        and after execution. This gives resumable/auditable run state without
        claiming full LangGraph-style per-node replay for every strategy.
        """
        if self.durable and self.resume_completed:
            latest = self.load_checkpoint()
            if latest and latest[0] == "completed":
                state = latest[1]
                return OrchestratorResult(
                    output=state.get("output"),
                    strategy=state.get("strategy", self.strategy),
                    trace_id=state.get("trace_id"),
                    total_cost=float(state.get("total_cost", 0.0) or 0.0),
                    steps=state.get("steps", []),
                    metadata={**state.get("metadata", {}), "resumed": True},
                    raw=state.get("raw"),
                )

        self._save_checkpoint("started", {"strategy": self.strategy, "task": task, "metadata": self.describe()})
        try:
            if self.strategy in {"sequential", "parallel"}:
                result = await self._run_team(task, **kwargs)
            elif self.strategy in {"dag", "state_machine"}:
                result = await self._run_workflow(task, **kwargs)
            elif self.strategy == "router":
                result = await self._run_router(task, **kwargs)
            elif self.strategy == "supervisor":
                result = await self._run_supervisor(task, **kwargs)
            elif self.strategy == "map_reduce":
                result = await self._run_map_reduce(task, **kwargs)
            else:
                raise AssertionError(f"unreachable strategy: {self.strategy}")
        except Exception as exc:
            self._save_checkpoint("failed", {"strategy": self.strategy, "error": str(exc), "task": task})
            raise

        self._save_checkpoint("completed", {
            "strategy": result.strategy,
            "output": result.output,
            "trace_id": result.trace_id,
            "total_cost": result.total_cost,
            "steps": result.steps,
            "metadata": result.metadata,
        })
        if self.durable:
            result.metadata = {**result.metadata, "durable": True, "thread_id": self.thread_id}
        return result

    async def _run_team(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        from largestack import Team

        if not self.agents:
            raise ValueError("Team orchestration requires at least one agent")

        team = Team(
            agents=self.agents,
            strategy=self.strategy,
            cost_budget=self.cost_budget,
            on_error=self.on_error,
            retries_per_agent=self.retries_per_agent,
        )
        prompt = task if isinstance(task, str) else task.get("task", str(task)) if isinstance(task, dict) else str(task)
        raw = await team.run(prompt, **kwargs)
        return OrchestratorResult(
            output=getattr(raw, "content", raw),
            strategy=self.strategy,
            trace_id=getattr(raw, "trace_id", None),
            total_cost=float(getattr(raw, "total_cost", 0.0) or 0.0),
            metadata={"agents": list(self.agent_map.keys())},
            raw=raw,
        )

    async def _run_workflow(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        from largestack import Workflow

        if not self.agent_map:
            raise ValueError("Workflow orchestration requires at least one agent")

        wf = Workflow(self.name, mode=self.strategy, cost_budget=self.cost_budget)
        deps: dict[str, list[str]] = {name: [] for name in self.agent_map}
        for src, dst in self.flow:
            if src not in self.agent_map:
                raise ValueError(f"Unknown flow source agent: {src!r}")
            if dst not in self.agent_map:
                raise ValueError(f"Unknown flow destination agent: {dst!r}")
            deps.setdefault(dst, []).append(src)
            deps.setdefault(src, [])
        for name, agent in self.agent_map.items():
            wf.add_node(name, agent, deps=deps.get(name, []))
        initial = task if isinstance(task, dict) else {"task": task}
        raw = await wf.run(initial)
        return OrchestratorResult(
            output=getattr(raw, "final_output", raw),
            strategy=self.strategy,
            trace_id=getattr(raw, "trace_id", None),
            total_cost=float(getattr(raw, "total_cost", 0.0) or 0.0),
            steps=getattr(raw, "steps", []) or [],
            metadata={"flow": list(self.flow), "agents": list(self.agent_map.keys())},
            raw=raw,
        )

    async def _run_router(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        from largestack._orchestrate.router import Router

        routes = self.routes or self.agent_map
        if not routes:
            raise ValueError("Router orchestration requires routes={name: agent} or agents={name: agent}")
        classifier = self.classifier or (self.agents[0] if self.agents else None)
        if classifier is None:
            raise ValueError("Router orchestration requires classifier=<Agent>")
        prompt = task if isinstance(task, str) else task.get("task", str(task)) if isinstance(task, dict) else str(task)
        default = self.default_route or next(iter(routes.keys()))
        router = Router(classifier=classifier, routes=dict(routes), default=default)
        raw = await router.run(prompt)
        return OrchestratorResult(
            output=getattr(raw, "content", raw),
            strategy="router",
            trace_id=getattr(raw, "trace_id", None),
            total_cost=float(getattr(raw, "total_cost", 0.0) or 0.0),
            metadata={"routes": list(routes.keys()), "router_stats": router.stats},
            raw=raw,
        )

    async def _run_supervisor(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        from largestack._core.multiagent import Supervisor

        specialists = self.routes or self.agent_map
        supervisor_agent = self.supervisor_agent or self.classifier
        if supervisor_agent is None and self.agents:
            supervisor_agent = self.agents[0]
            # If specialists came from the same list, don't route the supervisor to itself.
            specialists = {k: v for k, v in self.agent_map.items() if v is not supervisor_agent}
        if supervisor_agent is None:
            raise ValueError("Supervisor orchestration requires supervisor_agent=<Agent>")
        if not specialists:
            raise ValueError("Supervisor orchestration requires specialist routes/agents")
        prompt = task if isinstance(task, str) else task.get("task", str(task)) if isinstance(task, dict) else str(task)
        descriptions = {
            name: getattr(agent, "instructions", "") or f"Specialist agent {name}"
            for name, agent in specialists.items()
        }
        supervisor = Supervisor(
            supervisor_agent=supervisor_agent,
            agents=dict(specialists),
            agent_descriptions=descriptions,
            max_iterations=self.max_iterations,
        )
        raw = await supervisor.run(prompt, **kwargs)
        steps = [getattr(step, "__dict__", step) for step in getattr(raw, "steps", [])]
        return OrchestratorResult(
            output=getattr(raw, "final_answer", raw),
            strategy="supervisor",
            steps=steps,
            metadata={
                "iterations": getattr(raw, "iterations", len(steps)),
                "finished_naturally": getattr(raw, "finished_naturally", None),
                "agents": list(specialists.keys()),
            },
            raw=raw,
        )

    async def _run_map_reduce(self, task: str | dict | list[Any], **kwargs) -> OrchestratorResult:
        from largestack._orchestrate.map_reduce import MapReduce

        mapper = self.mapper or (self.agents[0] if self.agents else None)
        reducer = self.reducer or (self.agents[1] if len(self.agents) > 1 else None)
        if mapper is None or reducer is None:
            raise ValueError("Map-reduce orchestration requires mapper and reducer agents")
        if isinstance(task, dict):
            items = task.get("items") or task.get("documents") or task.get("inputs")
        elif isinstance(task, list):
            items = task
        else:
            items = None
        if not items:
            raise ValueError("Map-reduce task requires a non-empty items/documents/inputs list")
        mr = MapReduce(
            mapper=mapper,
            reducer=reducer,
            max_concurrency=self.max_concurrency,
            on_error=self.on_error,
        )
        raw = await mr.run(list(items))
        return OrchestratorResult(
            output=getattr(raw, "content", raw),
            strategy="map_reduce",
            trace_id=getattr(raw, "trace_id", None),
            total_cost=float(getattr(raw, "total_cost", 0.0) or 0.0),
            metadata={"items": len(items), "max_concurrency": self.max_concurrency},
            raw=raw,
        )
