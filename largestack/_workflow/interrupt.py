"""Human-in-the-loop interrupt primitive (v0.8.0).

A first-class way to pause an agent / workflow run, surface a question
to a human, and resume after their response. This is the primitive
LangGraph calls ``interrupt()``. LARGESTACK's version supports two modes:

1. **Synchronous interrupts** — for request-response flows where you
   want to block in-process until a human callback returns.
2. **Async checkpoint interrupts** — raise ``InterruptException`` carrying
   the question; caller catches it, asks the human (any UI), then calls
   ``resume()`` with the answer to continue.

Pattern 1 (callback):

    from largestack._workflow.interrupt import HumanInTheLoop, InterruptResponse

    async def get_human_answer(prompt: str) -> str:
        # In tests this is a stub; in production this is your UI hook
        return await my_websocket_ask(prompt)

    hitl = HumanInTheLoop(callback=get_human_answer)
    answer = await hitl.ask("Approve this loan? (yes/no)")

Pattern 2 (exception-based for graph workflows):

    from largestack._workflow.interrupt import interrupt, resume_with

    async def loan_review_node(state):
        if state["amount"] > 1_000_000:
            # This raises InterruptException — caller catches and resumes
            answer = interrupt(
                question="Approve this large loan?",
                default="deny",
            )
            state["approved"] = answer == "approve"
        return state

The exception-based pattern integrates naturally with the Graph DSL
once checkpointing is added in v0.9. For v0.8 we ship the API and
the callback-based path that works without checkpointing.
"""
from __future__ import annotations
import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("largestack.workflow.interrupt")


@dataclass
class InterruptResponse:
    """A human's response to an interrupt."""
    interrupt_id: str
    answer: Any
    metadata: dict = field(default_factory=dict)


class InterruptException(Exception):
    """Raised by ``interrupt()`` to signal pause-for-human.

    The exception carries the question and a unique ``interrupt_id``
    so the caller can match the resumed answer to the right interrupt.
    """

    def __init__(
        self,
        question: str,
        *,
        interrupt_id: str | None = None,
        default: Any = None,
        choices: list | None = None,
        metadata: dict | None = None,
    ):
        self.interrupt_id = interrupt_id or str(uuid.uuid4())
        self.question = question
        self.default = default
        self.choices = list(choices) if choices else None
        self.metadata = metadata or {}
        super().__init__(f"interrupt({self.interrupt_id}): {question}")


def interrupt(
    question: str,
    *,
    interrupt_id: str | None = None,
    default: Any = None,
    choices: list | None = None,
    metadata: dict | None = None,
) -> Any:
    """Raise an InterruptException to pause for human input.

    This is the primary primitive for human-in-the-loop. It always
    raises — calling code must catch ``InterruptException``, get the
    human's answer, then resume.

    Args:
        question: what to ask the human.
        interrupt_id: stable ID for matching responses (auto-generated if None).
        default: value to use if the human declines / times out.
        choices: optional list of valid answers (for radio-button UIs).
        metadata: extra context for the UI (e.g. ``{"severity": "high"}``).

    Raises:
        Always raises ``InterruptException``.
    """
    raise InterruptException(
        question=question,
        interrupt_id=interrupt_id,
        default=default,
        choices=choices,
        metadata=metadata,
    )


def resume_with(answer: Any, default_used: bool = False) -> InterruptResponse:
    """Construct an InterruptResponse for resuming.

    Convenience for the common pattern where the caller needs to
    forward an answer back to the workflow.
    """
    return InterruptResponse(
        interrupt_id="",  # caller can fill in if matching is needed
        answer=answer,
        metadata={"default_used": default_used},
    )


class HumanInTheLoop:
    """Callback-based human-in-the-loop helper.

    Args:
        callback: async or sync callable taking ``(prompt: str)`` and
            returning the human's answer (or any value).
        default_timeout_seconds: if the callback is async and supports
            cancellation, this caps wait time. ``None`` = wait forever.
    """

    def __init__(
        self,
        callback: Callable,
        *,
        default_timeout_seconds: float | None = None,
    ):
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._callback = callback
        self._default_timeout = default_timeout_seconds
        self._history: list[dict] = []

    @property
    def history(self) -> list[dict]:
        """Read-only access to all asks/responses so far."""
        return list(self._history)

    async def ask(
        self,
        prompt: str,
        *,
        default: Any = None,
        timeout: float | None = None,
        choices: list | None = None,
    ) -> Any:
        """Ask the human via the callback. Returns their answer.

        Args:
            prompt: question to display.
            default: returned if the callback fails or times out.
            timeout: per-call timeout override (seconds).
            choices: optional set of valid answers; non-matching answers
                trigger a re-ask once.

        Returns:
            the answer (whatever the callback returned), validated
            against ``choices`` if provided.
        """
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        record: dict = {"prompt": prompt, "default_used": False}

        try:
            result = await self._invoke(prompt, effective_timeout)
        except asyncio.TimeoutError:
            log.warning(f"HITL: prompt timed out, using default ({default!r})")
            record["error"] = "timeout"
            record["default_used"] = True
            self._history.append(record)
            return default
        except Exception as e:
            log.warning(f"HITL: callback failed: {e}; using default")
            record["error"] = str(e)
            record["default_used"] = True
            self._history.append(record)
            return default

        # Validate against choices
        if choices is not None and result not in choices:
            log.debug(f"HITL: answer {result!r} not in choices {choices}; re-asking once")
            record["first_invalid"] = result
            try:
                result = await self._invoke(
                    f"{prompt}\n(Please pick one of: {choices})",
                    effective_timeout,
                )
            except Exception as e:
                log.warning(f"HITL re-ask failed: {e}; using default")
                record["error"] = str(e)
                record["default_used"] = True
                self._history.append(record)
                return default
            if choices is not None and result not in choices:
                # Still invalid — give up to default
                record["second_invalid"] = result
                record["default_used"] = True
                self._history.append(record)
                return default

        record["answer"] = result
        self._history.append(record)
        return result

    async def _invoke(self, prompt: str, timeout: float | None) -> Any:
        """Invoke callback, handling sync/async and timeout."""
        result = self._callback(prompt)
        if inspect.isawaitable(result):
            if timeout is not None:
                return await asyncio.wait_for(result, timeout=timeout)
            return await result
        return result
