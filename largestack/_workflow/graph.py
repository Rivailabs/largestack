"""Graph Workflow DSL — LangGraph-style state machine for agents (v0.8.0).

The biggest gap LARGESTACK had vs LangGraph was a first-class graph-based
state machine. This module fills it.

Core concepts:
- **State**: a Python dict (or Pydantic model) carried through the graph.
- **Node**: a function that takes State and returns updated State.
- **Edge**: an unconditional transition from one node to another.
- **Conditional edge**: a router function that picks the next node based on State.
- **Subgraph**: a Graph used as a node within another Graph.
- **Special nodes**: ``START`` and ``END``.

This is intentionally simpler than LangGraph (no checkpointing in this
release — that's v0.9 work) but covers the core 80% of LangGraph use cases:
- Multi-step reasoning workflows
- Agent supervisor patterns
- Branching logic (if X, do A; else do B)
- Parallel branches that converge
- Cycle-bounded loops (with safe iteration limits)

Usage:

    from largestack._workflow.graph import Graph, START, END

    g = Graph()
    g.add_node("classify", classify_fn)
    g.add_node("answer", answer_fn)
    g.add_node("escalate", escalate_fn)

    g.set_entry("classify")
    g.add_conditional_edges(
        "classify",
        lambda state: "answer" if state["intent"] == "simple" else "escalate",
        {"answer": "answer", "escalate": "escalate"},
    )
    g.add_edge("answer", END)
    g.add_edge("escalate", END)

    final_state = await g.run({"question": "What time is it?"})

Subgraphs:

    sub = Graph()
    sub.add_node("a", node_a); sub.add_node("b", node_b)
    sub.set_entry("a"); sub.add_edge("a", "b"); sub.add_edge("b", END)

    main = Graph()
    main.add_node("preprocess", preprocess)
    main.add_node("sub", sub.as_node())  # use sub as a node!
    main.set_entry("preprocess")
    main.add_edge("preprocess", "sub")
    main.add_edge("sub", END)
"""
from __future__ import annotations
import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("largestack.workflow.graph")

# Sentinels for entry / exit
START = "__start__"
END = "__end__"


@dataclass
class GraphRunResult:
    """Result of a graph execution."""
    state: dict
    path: list[str] = field(default_factory=list)
    iterations: int = 0
    truncated: bool = False  # True if ran out of max_iterations


class Graph:
    """A directed graph of nodes (functions) operating on shared state.

    Args:
        max_iterations: hard cap on node executions per run (default 50).
            Prevents runaway cycles.
    """

    def __init__(self, *, max_iterations: int = 50):
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.max_iterations = max_iterations
        self._nodes: dict[str, Callable] = {}
        self._edges: dict[str, str] = {}  # source → target (unconditional)
        self._conditional_edges: dict[str, tuple[Callable, dict]] = {}
        # source → (router_fn, branch_map)
        self._entry: str | None = None
        self._compiled = False

    # -------------------- Building --------------------

    def add_node(self, name: str, fn: Callable) -> "Graph":
        """Add a node to the graph.

        Args:
            name: unique name. Cannot be ``START`` or ``END``.
            fn: callable taking ``state: dict`` and returning a new
                state dict (or a partial dict to merge). May be sync
                or async.

        Returns self for chaining.
        """
        if name in {START, END}:
            raise ValueError(f"reserved node name: {name!r}")
        if not name or not isinstance(name, str):
            raise ValueError("node name must be a non-empty string")
        if name in self._nodes:
            raise ValueError(f"node {name!r} already exists")
        if not callable(fn):
            raise TypeError("fn must be callable")
        self._nodes[name] = fn
        return self

    def set_entry(self, name: str) -> "Graph":
        """Set the entry node (first node executed)."""
        if name not in self._nodes:
            raise ValueError(f"entry node {name!r} not found")
        self._entry = name
        return self

    def add_edge(self, source: str, target: str) -> "Graph":
        """Add an unconditional edge from source to target.

        Args:
            source: name of source node.
            target: name of target node, or ``END``.
        """
        if source not in self._nodes:
            raise ValueError(f"source node {source!r} not found")
        if target != END and target not in self._nodes:
            raise ValueError(f"target node {target!r} not found")
        if source in self._conditional_edges:
            raise ValueError(
                f"node {source!r} already has conditional edges; "
                f"can't have both kinds"
            )
        if source in self._edges:
            raise ValueError(f"node {source!r} already has an edge")
        self._edges[source] = target
        return self

    def add_conditional_edges(
        self,
        source: str,
        router: Callable,
        branches: dict[str, str],
    ) -> "Graph":
        """Add conditional edges from source. Router decides which branch.

        Args:
            source: source node name.
            router: callable taking state and returning a key from ``branches``.
                May be sync or async.
            branches: dict mapping router output → target node name (or END).
        """
        if source not in self._nodes:
            raise ValueError(f"source node {source!r} not found")
        if source in self._edges:
            raise ValueError(
                f"node {source!r} already has an edge; "
                f"can't add conditional edges too"
            )
        if not callable(router):
            raise TypeError("router must be callable")
        if not branches:
            raise ValueError("branches dict must be non-empty")
        for k, v in branches.items():
            if v != END and v not in self._nodes:
                raise ValueError(f"branch target {v!r} not found")
        self._conditional_edges[source] = (router, dict(branches))
        return self

    # -------------------- Compile / Validate --------------------

    def compile(self) -> "Graph":
        """Validate the graph. Required before run() (called automatically)."""
        if self._entry is None:
            raise ValueError("entry node not set; call set_entry()")
        # Check every non-END node has at least one outgoing edge
        for name in self._nodes:
            if name not in self._edges and name not in self._conditional_edges:
                raise ValueError(
                    f"node {name!r} has no outgoing edge; "
                    f"add_edge or add_conditional_edges (use END as target if terminal)"
                )
        self._compiled = True
        return self

    # -------------------- Run --------------------

    async def run(self, initial_state: dict | None = None) -> GraphRunResult:
        """Execute the graph from entry to END.

        Args:
            initial_state: starting state dict.

        Returns:
            GraphRunResult with final state, path taken, iteration count.
        """
        if not self._compiled:
            self.compile()
        if self._entry is None:
            raise RuntimeError("entry not set")

        state: dict = dict(initial_state or {})
        current = self._entry
        path: list[str] = []
        iterations = 0
        truncated = False

        while current != END:
            iterations += 1
            if iterations > self.max_iterations:
                log.warning(
                    f"graph: hit max_iterations ({self.max_iterations}); truncating"
                )
                truncated = True
                break

            path.append(current)
            node_fn = self._nodes.get(current)
            if node_fn is None:
                raise RuntimeError(f"node {current!r} disappeared mid-run")

            # Execute node
            update = await self._maybe_await(node_fn, state)
            if update is None:
                pass  # node mutated state in-place
            elif isinstance(update, dict):
                state.update(update)
            else:
                raise TypeError(
                    f"node {current!r} returned {type(update).__name__}; "
                    f"must return dict or None"
                )

            # Decide next node
            current = await self._next(current, state)

        return GraphRunResult(
            state=state, path=path, iterations=iterations, truncated=truncated,
        )

    async def _next(self, current: str, state: dict) -> str:
        """Determine the next node from current."""
        if current in self._edges:
            return self._edges[current]
        if current in self._conditional_edges:
            router, branches = self._conditional_edges[current]
            choice = await self._maybe_await(router, state)
            if choice not in branches:
                raise ValueError(
                    f"router for {current!r} returned {choice!r}; "
                    f"valid branches: {list(branches.keys())}"
                )
            return branches[choice]
        # Should not reach here after compile()
        raise RuntimeError(f"node {current!r} has no outgoing edge")

    @staticmethod
    async def _maybe_await(fn: Callable, *args, **kwargs) -> Any:
        """Call fn, awaiting if it returns a coroutine."""
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    # -------------------- Subgraph composition --------------------

    def as_node(self) -> Callable:
        """Wrap this graph as a node fn for use in a parent graph.

        The wrapped function takes state, runs this subgraph, and
        returns the final subgraph state to merge into parent state.
        """
        if not self._compiled:
            self.compile()

        async def _subgraph_node(state: dict) -> dict:
            result = await self.run(state)
            return result.state

        return _subgraph_node

    # -------------------- Introspection --------------------

    def nodes(self) -> list[str]:
        return list(self._nodes.keys())

    def to_mermaid(self) -> str:
        """Render the graph as Mermaid flowchart syntax (for docs/debug)."""
        lines = ["graph TD"]
        if self._entry:
            lines.append(f"    START([START]) --> {self._entry}")
        for src, tgt in self._edges.items():
            tgt_label = "END([END])" if tgt == END else tgt
            lines.append(f"    {src} --> {tgt_label}")
        for src, (_, branches) in self._conditional_edges.items():
            for branch_name, tgt in branches.items():
                tgt_label = "END([END])" if tgt == END else tgt
                lines.append(f"    {src} -->|{branch_name}| {tgt_label}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Graph(nodes={len(self._nodes)}, "
            f"edges={len(self._edges)}, "
            f"conditional={len(self._conditional_edges)})"
        )
