"""Parallel guardrail pipeline — all checks run simultaneously.

Supports fail_closed (default) so guard crashes block requests instead of allowing through.
"""

from __future__ import annotations
import asyncio, logging
from typing import Any
from largestack.errors import GuardrailBlockedError
from largestack.types import GuardrailAction

log = logging.getLogger("largestack.guard")


class GuardrailPipeline:
    """Pipeline that runs guards in parallel.

    Args:
        guards: List of guard objects with check_input / check_output methods.
        action: BLOCK (raise on violation) or WARN (log only).
        fail_closed: If True (default), unexpected guard exceptions raise as
                     GuardrailBlockedError. If False, exceptions are logged
                     and the request proceeds. Set fail_closed=False only for
                     non-critical guards in dev environments.
    """

    def __init__(
        self,
        guards: list = None,
        action: GuardrailAction = GuardrailAction.BLOCK,
        fail_closed: bool = True,
    ):
        self.guards = guards or []
        self.action = action
        self.fail_closed = fail_closed

    @classmethod
    def create(
        cls,
        pii: bool = True,
        injection: bool = True,
        hallucination: bool = False,
        toxicity: bool = False,
        topic_blocklist: list[str] = None,
        pii_action: str = "redact",
        injection_sensitivity: str = "medium",
        **kwargs,
    ) -> "GuardrailPipeline":
        """Convenience constructor — same as ``create_guardrails(...)``.

        Lets you write ``Guardrails.create(pii=True, injection=True)`` instead
        of ``from largestack import create_guardrails; create_guardrails(...)``.

        Note: this factory does NOT take a ``schema=`` parameter. For JSON-
        schema validation on agent output, use ``TypedAgent`` with a Pydantic
        ``output_model=`` instead — schema enforcement belongs to the model
        layer, not the guardrail layer.
        """
        # Lazy import to avoid circular reference
        from largestack.guardrails import create_guardrails

        return create_guardrails(
            pii=pii,
            injection=injection,
            hallucination=hallucination,
            toxicity=toxicity,
            topic_blocklist=topic_blocklist,
            pii_action=pii_action,
            injection_sensitivity=injection_sensitivity,
        )

    async def check_input(self, messages: list[dict]):
        if not self.guards:
            return
        tasks = [g.check_input(messages) for g in self.guards if hasattr(g, "check_input")]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, GuardrailBlockedError):
                    if self.action == GuardrailAction.BLOCK:
                        raise r
                    else:
                        log.warning(f"Guard warning: {r}")
                elif isinstance(r, Exception):
                    log.exception(f"Guard {i} raised unexpected exception: {r}")
                    if self.fail_closed:
                        raise GuardrailBlockedError(
                            "guardrail_error", f"Guard {i} crashed: {type(r).__name__}: {r}"
                        )

    async def check_output(self, response: Any):
        if not self.guards:
            return
        tasks = [g.check_output(response) for g in self.guards if hasattr(g, "check_output")]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, GuardrailBlockedError):
                    if self.action == GuardrailAction.BLOCK:
                        raise r
                    else:
                        log.warning(f"Guard warning: {r}")
                elif isinstance(r, Exception):
                    log.exception(f"Output guard {i} raised: {r}")
                    if self.fail_closed:
                        raise GuardrailBlockedError(
                            "guardrail_error", f"Output guard {i} crashed: {type(r).__name__}: {r}"
                        )
