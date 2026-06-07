"""Public Workflow — DAG and state machine with Agent support and cost budget."""

from __future__ import annotations
from typing import Any, Callable
from largestack._orchestrate.dag import DAGWorkflow
from largestack._orchestrate.state_machine import StateMachine


class Workflow:
    """Build complex agent workflows. Accepts Agent objects directly.

    wf = Workflow("pipeline")
    wf.add_node("research", researcher_agent)           # Agent object!
    wf.add_node("write", writer_agent, deps=["research"])
    result = await wf.run({"task": "Analyze AI trends"})
    """

    def __init__(
        self,
        name: str = "workflow",
        mode: str = "dag",
        max_transitions: int = 50,
        cost_budget: float = 0,
    ):
        self.name = name
        self.mode = mode
        if mode == "state_machine":
            self._impl = StateMachine(name, max_transitions, cost_budget)
        else:
            self._impl = DAGWorkflow(name, cost_budget)

    def add_node(self, name: str, handler: Any, deps: list[str] = None):
        if isinstance(self._impl, DAGWorkflow):
            self._impl.add_node(name, handler, deps)
        else:
            self._impl.add_node(name, handler)

    def add_agent(self, agent: Any, deps: list[str] = None):
        """Convenience alias: register an Agent as a node using its .name.

        Equivalent to ``wf.add_node(agent.name, agent, deps=deps)``.
        Lets you write:

            wf.add_agent(extractor)
            wf.add_agent(validator, deps=["bom-extractor"])

        instead of building a state-handler wrapper for every Agent.
        """
        if not hasattr(agent, "name"):
            raise TypeError(
                "add_agent() expects an Agent (or any object with a .name attr). "
                "For raw async handlers use add_node(name, handler, deps=...)."
            )
        return self.add_node(agent.name, agent, deps)

    def add_edge(self, source: str, target: str, condition: Callable = None):
        self._impl.add_edge(source, target, condition)

    def set_start(self, name: str):
        """Set the start node. Only valid for state-machine workflows.

        v0.3.10: raises ValueError instead of silently no-op when called on a
        DAG workflow. DAGs derive ordering from the dependency graph and have
        no concept of a 'start' node (any node with no deps is a start).
        """
        if isinstance(self._impl, StateMachine):
            self._impl.set_start(name)
            return
        raise ValueError(
            "set_start() is only valid for mode='state_machine' workflows. "
            f"This workflow uses mode='{self.mode}'. "
            "DAG workflows infer start nodes from the dependency graph "
            "(any node with no deps is a start)."
        )

    def set_end(self, *names: str):
        """Set end nodes. Only valid for state-machine workflows.

        v0.3.10: raises ValueError instead of silently no-op when called on a
        DAG workflow. DAGs derive terminals from the dependency graph (any
        node that no other node depends on is an end).
        """
        if isinstance(self._impl, StateMachine):
            self._impl.set_end(*names)
            return
        raise ValueError(
            "set_end() is only valid for mode='state_machine' workflows. "
            f"This workflow uses mode='{self.mode}'. "
            "DAG workflows infer end nodes from the dependency graph "
            "(any node that no other node depends on is an end)."
        )

    async def run(self, initial_state: dict = None) -> "WorkflowResult":
        """Run the workflow.

        Returns a :class:`WorkflowResult` which behaves as both a dict (legacy
        access via ``result["key"]``) and an object with named attributes
        (``result.final_output``, ``result.steps``, ``result.total_cost``,
        ``result.guardrail_events``, ``result.trace_id``).
        """
        raw = await self._impl.run(initial_state)
        return WorkflowResult.from_state(raw, workflow_name=self.name)


class WorkflowResult(dict):
    """Result of ``Workflow.run()``.

    Behaves as a plain ``dict`` (so old code using ``result["key"]`` keeps
    working) and exposes named attributes for ergonomic access:

    - ``result.final_output`` — output of the last node that ran (the deepest
      leaf in a DAG, or the final state of a state machine). Falls back to the
      whole state dict if no clear leaf exists.
    - ``result.steps`` — list of ``{name, output, cost}`` dicts in execution
      order.
    - ``result.total_cost`` — sum of all node costs (was ``_total_cost`` key).
    - ``result.guardrail_events`` — any guardrail blocks that fired (always a
      list, may be empty).
    - ``result.trace_id`` — workflow-level trace id (uuid4) for cross-system
      correlation.
    - ``result.status`` — ``"completed"`` (or ``"error"`` if an exception
      surfaced through state).

    The attributes are computed lazily on access, so they always reflect the
    current state of the underlying dict — mutating ``result["new_key"]``
    after construction is honored.
    """

    @classmethod
    def from_state(cls, state: dict | None, *, workflow_name: str = "workflow") -> "WorkflowResult":
        import uuid as _uuid

        state = dict(state) if state else {}
        wr = cls(state)
        # Cache only the immutable identity bits; everything derivable stays a property.
        wr.__dict__["_trace_id"] = state.get("_trace_id") or str(_uuid.uuid4())
        wr.__dict__["_workflow_name"] = workflow_name
        return wr

    # ---- derived attributes ----

    @property
    def total_cost(self) -> float:
        return float(self.get("_total_cost", 0.0))

    @property
    def steps(self) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for k in self.keys():
            if k.endswith("_output") and not k.startswith("_"):
                node = k[: -len("_output")]
                if node in seen:
                    continue
                seen.add(node)
                out.append(
                    {
                        "name": node,
                        "output": self[k],
                        "cost": float(self.get(f"{node}_cost", 0.0)),
                    }
                )
        return out

    @property
    def final_output(self):
        s = self.steps
        if s:
            return s[-1]["output"]
        # Strip private/system keys for the fallback view
        return {k: v for k, v in self.items() if not k.startswith("_")}

    @property
    def guardrail_events(self) -> list:
        return list(self.get("_guardrail_events", []))

    @property
    def trace_id(self) -> str:
        return self.__dict__.get("_trace_id", "")

    @property
    def workflow_name(self) -> str:
        return self.__dict__.get("_workflow_name", "workflow")

    @property
    def status(self) -> str:
        return "error" if self.get("_error") else "completed"

    # ---- pickling: preserve our extra __dict__ state ----

    def __reduce__(self):
        return (
            _rebuild_workflow_result,
            (
                dict(self),
                self.__dict__.get("_trace_id"),
                self.__dict__.get("_workflow_name", "workflow"),
            ),
        )


def _rebuild_workflow_result(state: dict, trace_id: str, workflow_name: str) -> WorkflowResult:
    wr = WorkflowResult(state)
    wr.__dict__["_trace_id"] = trace_id
    wr.__dict__["_workflow_name"] = workflow_name
    return wr
