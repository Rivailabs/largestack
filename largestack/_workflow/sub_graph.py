"""Sub-graph Workflow composition (v0.14.0).

Closes Tier A #20. Lets you embed a ``Workflow`` as a node in another
``Workflow``. LangGraph parity feature.

Usage::

    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node, SubWorkflowNode

    # Inner pipeline
    inner = Workflow("kyc-inner")
    inner.add_node("verify_pan", pan_agent)
    inner.add_node("verify_aadhaar", aadhaar_agent, deps=["verify_pan"])

    # Outer pipeline embeds inner as a single node
    outer = Workflow("loan-application")
    outer.add_node("intake", intake_agent)
    outer.add_node("kyc", as_node(inner), deps=["intake"])
    outer.add_node("approve", approve_agent, deps=["kyc"])

    result = await outer.run({"applicant_id": "U001"})

State propagation:
- Outer state → ``inner_state`` parameter (same dict)
- Inner result → merged into outer state (key collision: inner wins)
- Optional ``state_mapping`` parameter to remap keys at the boundary
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

log = logging.getLogger("largestack.workflow.subgraph")


@dataclass
class SubWorkflowNode:
    """Adapter that makes a ``Workflow`` callable as a node handler.

    Args:
        workflow: the inner ``Workflow`` to run
        state_mapping: optional ``{outer_key: inner_key}`` rename
            applied to the input
        output_mapping: optional ``{inner_key: outer_key}`` rename
            applied to the output
        passthrough: if True, outer state is also forwarded into inner
            (useful when inner needs context from outer)
    """
    workflow: Any  # Workflow instance (avoid import cycle)
    state_mapping: dict[str, str] = field(default_factory=dict)
    output_mapping: dict[str, str] = field(default_factory=dict)
    passthrough: bool = True
    isolate_errors: bool = False

    async def __call__(
        self, state: dict[str, Any] | None = None, **kwargs: Any,
    ) -> dict[str, Any]:
        """Invoke the sub-workflow. Returns the combined state."""
        outer_state: dict[str, Any] = dict(state or {})
        outer_state.update(kwargs)

        # Build inner input
        inner_input: dict[str, Any] = {}
        if self.passthrough:
            inner_input.update(outer_state)
        if self.state_mapping:
            for outer_k, inner_k in self.state_mapping.items():
                if outer_k in outer_state:
                    inner_input[inner_k] = outer_state[outer_k]

        # Run inner workflow
        try:
            inner_result = await self.workflow.run(inner_input)
        except Exception as e:
            if self.isolate_errors:
                log.warning(
                    f"sub-workflow '{getattr(self.workflow, 'name', '?')}' "
                    f"raised {type(e).__name__}: {e} — isolated"
                )
                return {
                    "_subgraph_error": str(e),
                    "_subgraph_error_type": type(e).__name__,
                }
            raise

        if not isinstance(inner_result, dict):
            inner_result = {"result": inner_result}

        # DAGWorkflow catches exceptions per-node and writes
        # ``<node>_error`` keys into the state — detect those.
        error_keys = [
            k for k in inner_result.keys()
            if k.endswith("_error") and not k.startswith("_")
        ]
        if error_keys:
            first_err = inner_result[error_keys[0]]
            if self.isolate_errors:
                log.warning(
                    f"sub-workflow '{getattr(self.workflow, 'name', '?')}' "
                    f"node error: {first_err} — isolated"
                )
                isolated = dict(inner_result)
                isolated["_subgraph_error"] = str(first_err)
                isolated["_subgraph_error_type"] = "SubgraphNodeError"
                return isolated
            else:
                raise RuntimeError(
                    f"sub-workflow node failed: {first_err}"
                )

        # Apply output mapping
        if self.output_mapping:
            mapped: dict[str, Any] = {}
            for inner_k, outer_k in self.output_mapping.items():
                if inner_k in inner_result:
                    mapped[outer_k] = inner_result[inner_k]
            # Keep unmapped keys as-is
            for k, v in inner_result.items():
                if k not in self.output_mapping:
                    mapped.setdefault(k, v)
            return mapped

        return inner_result

    @property
    def name(self) -> str:
        return getattr(self.workflow, "name", "sub_workflow")


def as_node(
    workflow: Any,
    *,
    state_mapping: dict[str, str] | None = None,
    output_mapping: dict[str, str] | None = None,
    passthrough: bool = True,
    isolate_errors: bool = False,
) -> Any:
    """Wrap a ``Workflow`` as a node handler. Convenience constructor.

    Returns an actual ``async def`` function (with metadata attached
    so ``asyncio.iscoroutinefunction`` recognizes it). DAGWorkflow's
    dispatch checks ``iscoroutinefunction`` to decide whether to await,
    so we must return a real async fn — not a dataclass instance with
    async ``__call__``.
    """
    sub_node = SubWorkflowNode(
        workflow=workflow,
        state_mapping=state_mapping or {},
        output_mapping=output_mapping or {},
        passthrough=passthrough,
        isolate_errors=isolate_errors,
    )

    async def _handler(state: dict[str, Any] | None = None, **kw: Any):
        return await sub_node(state, **kw)

    # Attach metadata for introspection
    _handler.sub_node = sub_node  # type: ignore[attr-defined]
    _handler.workflow = workflow  # type: ignore[attr-defined]
    _handler.__name__ = (
        f"sub_{getattr(workflow, 'name', 'workflow')}"
    )
    return _handler


# -------------------- Compose multiple workflows --------------------

class WorkflowComposer:
    """Build a parent workflow from multiple sub-workflows declaratively.

    Used when several sub-workflows feed into each other::

        composer = WorkflowComposer("loan-application")
        composer.add_subgraph("kyc", kyc_wf)
        composer.add_subgraph("scoring", scoring_wf, deps=["kyc"])
        composer.add_subgraph("approval", approval_wf, deps=["scoring"])
        outer = composer.build()
        result = await outer.run({"applicant_id": "U001"})
    """

    def __init__(self, name: str = "composed"):
        self.name = name
        self._sub_specs: list[dict[str, Any]] = []
        self._scalar_nodes: list[dict[str, Any]] = []

    def add_subgraph(
        self,
        node_name: str,
        workflow: Any,
        *,
        deps: list[str] | None = None,
        state_mapping: dict[str, str] | None = None,
        output_mapping: dict[str, str] | None = None,
        isolate_errors: bool = False,
    ) -> "WorkflowComposer":
        if not node_name:
            raise ValueError("node_name is required")
        self._sub_specs.append({
            "node_name": node_name,
            "workflow": workflow,
            "deps": deps or [],
            "state_mapping": state_mapping or {},
            "output_mapping": output_mapping or {},
            "isolate_errors": isolate_errors,
        })
        return self

    def add_node(
        self,
        node_name: str,
        handler: Any,
        *,
        deps: list[str] | None = None,
    ) -> "WorkflowComposer":
        self._scalar_nodes.append({
            "node_name": node_name,
            "handler": handler,
            "deps": deps or [],
        })
        return self

    def build(self) -> Any:
        """Construct the parent ``Workflow`` from the spec."""
        from largestack.workflow import Workflow
        wf = Workflow(self.name, mode="dag")

        # Scalar nodes first
        for s in self._scalar_nodes:
            wf.add_node(s["node_name"], s["handler"], deps=s["deps"])

        # Sub-graph nodes — wrap each in SubWorkflowNode
        for s in self._sub_specs:
            sub_node = as_node(
                s["workflow"],
                state_mapping=s["state_mapping"],
                output_mapping=s["output_mapping"],
                isolate_errors=s["isolate_errors"],
            )
            wf.add_node(s["node_name"], sub_node, deps=s["deps"])

        return wf


__all__ = ["SubWorkflowNode", "as_node", "WorkflowComposer"]
