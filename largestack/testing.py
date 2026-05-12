"""Test utilities — mock models, request blocking, and message capture.

PydanticAI-style TestModel and FunctionModel, with working override and
capture mechanisms (v0.3.10).

Usage
-----

Override an agent's model with a TestModel — no real API call is made:

    from largestack.testing import TestModel

    test_model = TestModel(custom_output_text="canned reply")
    with agent.override(model=test_model):
        result = await agent.run("anything")
    assert "canned reply" in result.content
    assert test_model.calls == 1

Block accidental real LLM calls in tests:

    from largestack.testing import block_model_requests
    from largestack.errors import ModelRequestsBlockedError

    with block_model_requests():
        try:
            await agent.run("Hello")  # would call real provider
        except ModelRequestsBlockedError:
            pass  # expected — no real call happened

Capture messages from an agent run:

    from largestack.testing import capture_run_messages

    with capture_run_messages() as captured:
        await agent.run("hello")
    assert len(captured.user_messages) >= 1
    assert any(m.get("role") == "assistant" for m in captured.messages)

FunctionModel for full control:

    def my_logic(messages, info):
        return {"content": "I got: " + messages[-1]["content"]}

    func_model = FunctionModel(my_logic)
    with agent.override(model=func_model):
        result = await agent.run("ping")
"""
from __future__ import annotations
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("largestack.testing")


# ---------------------------------------------------------------------------
# Mock LLM responses + models
# ---------------------------------------------------------------------------

@dataclass
class MockResponse:
    """Mock LLM response."""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input_tokens": 10, "output_tokens": 20})
    model: str = "test-model"
    finish_reason: str = "stop"


class TestModel:
    """Mock model that returns a canned response and (optionally) calls tools.

    Useful for unit tests where you want to verify agent flow without paying
    for real LLM calls.

    Args:
        custom_output_text: Text to return as final response.
        custom_tool_args: dict mapping tool_name → args used when invoking each tool.
        call_tools: 'all' (default), [] for none, or list of tool names to call.

    Example:
        test_model = TestModel(custom_output_text="OK")
        with agent.override(model=test_model):
            result = await agent.run("Search for X")
        assert test_model.tool_calls_made == ["search_kb"]
    """

    __test__ = False  # tell pytest this is not a test class


    def __init__(
        self,
        custom_output_text: str = "Test response",
        custom_tool_args: dict[str, dict] | None = None,
        call_tools: str | list[str] = "all",
    ):
        self.custom_output_text = custom_output_text
        self.custom_tool_args = custom_tool_args or {}
        self.call_tools = call_tools
        self.tool_calls_made: list[str] = []
        self.messages_received: list = []
        self.calls = 0

    async def chat(self, messages: list, model: str = "", tools: list | None = None,
                   **kwargs) -> dict:
        """Mimic provider chat interface, return raw dict (gateway adapter wraps it)."""
        self.calls += 1
        self.messages_received = list(messages)

        if tools and self.calls == 1:
            tool_calls = []
            tools_to_call = (
                [t["name"] if isinstance(t, dict) else t.name for t in tools]
                if self.call_tools == "all"
                else (self.call_tools if isinstance(self.call_tools, list) else [])
            )
            for tool in tools:
                tname = tool["name"] if isinstance(tool, dict) else tool.name
                if tname in tools_to_call:
                    args = self.custom_tool_args.get(tname, {})
                    if not args and isinstance(tool, dict):
                        schema = tool.get("parameters", {}).get("properties", {})
                        args = {k: _dummy_value(v.get("type", "string"))
                                for k, v in schema.items()}
                    tool_calls.append({
                        "id": f"tool_{len(tool_calls)}",
                        "name": tname,
                        "arguments": args,
                    })
                    self.tool_calls_made.append(tname)

            if tool_calls:
                return {
                    "content": "",
                    "tool_calls": tool_calls,
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "model": "test-model",
                    "finish_reason": "tool_calls",
                }

        return {
            "content": self.custom_output_text,
            "tool_calls": [],
            "usage": {"input_tokens": 15, "output_tokens": 25},
            "model": "test-model",
            "finish_reason": "stop",
        }

    def reset(self) -> None:
        self.tool_calls_made = []
        self.messages_received = []
        self.calls = 0


class FunctionModel:
    """Mock model with full control via a callable.

    Args:
        func: Callable receiving (messages, info) and returning dict response.
              info contains: tools, model, attempt.

    Example:
        def my_logic(messages, info):
            last = messages[-1]["content"]
            return {"content": f"Echo: {last}"}

        with agent.override(model=FunctionModel(my_logic)):
            result = await agent.run("ping")
    """

    def __init__(self, func: Callable[[list, dict], dict]):
        self.func = func
        self.calls = 0
        self.messages_received: list = []

    async def chat(self, messages: list, model: str = "", tools: list | None = None,
                   **kwargs) -> dict:
        self.calls += 1
        self.messages_received = list(messages)

        info = {"tools": tools or [], "model": model, "attempt": self.calls}

        import inspect
        if inspect.iscoroutinefunction(self.func):
            result = await self.func(messages, info)
        else:
            result = self.func(messages, info)

        if isinstance(result, str):
            result = {"content": result}
        result.setdefault("content", "")
        result.setdefault("tool_calls", [])
        result.setdefault("usage", {"input_tokens": 10, "output_tokens": 20})
        result.setdefault("model", "function-model")
        result.setdefault("finish_reason", "stop" if not result["tool_calls"] else "tool_calls")
        return result


# ---------------------------------------------------------------------------
# Captured messages — populated by AgentEngine via _capture_var
# ---------------------------------------------------------------------------

@dataclass
class CapturedMessages:
    """Container for captured messages from a run."""
    messages: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.messages)

    def __iter__(self):
        return iter(self.messages)

    def filter_role(self, role: str) -> list:
        return [m for m in self.messages if m.get("role") == role]

    @property
    def user_messages(self) -> list:
        return self.filter_role("user")

    @property
    def assistant_messages(self) -> list:
        return self.filter_role("assistant")

    @property
    def system_messages(self) -> list:
        return self.filter_role("system")

    @property
    def tool_messages(self) -> list:
        return self.filter_role("tool")

    def add(self, msg: dict) -> None:
        """Append a message. Skips exact (identity) duplicates of the most-recent entry."""
        if msg is None:
            return
        if self.messages and self.messages[-1] is msg:
            return
        self.messages.append(msg)


# ContextVar populated by capture_run_messages(); read by AgentEngine.
# v0.3.10: this is the wiring that was missing in v0.3.9. The engine
# checks _capture_var.get() at message-mutation points and appends to it.
_capture_var: ContextVar["CapturedMessages | None"] = ContextVar(
    "largestack_capture_messages", default=None,
)


def _capture_message(msg: dict) -> None:
    """Internal: called by AgentEngine to record a message into the active capture."""
    cap = _capture_var.get()
    if cap is not None and isinstance(msg, dict):
        cap.add(dict(msg))  # copy so later mutations don't bleed in


class capture_run_messages:
    """Context manager that captures every message passing through the engine.

    Use as:
        with capture_run_messages() as captured:
            await agent.run("hello")
        print(captured.user_messages)
        print(captured.assistant_messages)
        print(captured.tool_messages)

    The capture is per-async-task (ContextVar-scoped), so concurrent runs
    in the same process do not interfere.
    """

    def __init__(self) -> None:
        self._captured = CapturedMessages()
        self._token = None

    def __enter__(self) -> CapturedMessages:
        self._token = _capture_var.set(self._captured)
        return self._captured

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _capture_var.reset(self._token)
            self._token = None


# ---------------------------------------------------------------------------
# Real-model-request gating
# ---------------------------------------------------------------------------

# Read at runtime by largestack._core.gateway.LLMGateway.chat/stream (v0.3.10).
ALLOW_MODEL_REQUESTS = True


def disable_model_requests() -> None:
    """Disable real LLM requests globally. Real provider calls raise
    ``largestack.errors.ModelRequestsBlockedError`` until re-enabled."""
    global ALLOW_MODEL_REQUESTS
    ALLOW_MODEL_REQUESTS = False


def enable_model_requests() -> None:
    """Re-enable real LLM requests."""
    global ALLOW_MODEL_REQUESTS
    ALLOW_MODEL_REQUESTS = True


class block_model_requests:
    """Context manager that blocks real LLM requests inside the block.

    Inside the block, any call to ``LLMGateway.chat()`` / ``stream()`` raises
    ``largestack.errors.ModelRequestsBlockedError``. Use this in tests to assert
    that no real provider call leaks through your test paths.

    Combine with ``agent.override(model=TestModel(...))`` to substitute a
    deterministic model for the duration of the block — the override path
    bypasses the gateway entirely, so real provider calls are still
    blocked while TestModel responses are returned.

    Example:
        with block_model_requests(), agent.override(model=TestModel("ok")):
            result = await agent.run("...")
        assert result.content == "ok"
    """

    def __init__(self) -> None:
        self._prev: bool | None = None

    def __enter__(self) -> "block_model_requests":
        global ALLOW_MODEL_REQUESTS
        self._prev = ALLOW_MODEL_REQUESTS
        ALLOW_MODEL_REQUESTS = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        global ALLOW_MODEL_REQUESTS
        if self._prev is not None:
            ALLOW_MODEL_REQUESTS = self._prev
            self._prev = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_value(json_type: str) -> Any:
    """Generate a dummy value matching JSON type (used by TestModel.chat)."""
    return {
        "string": "test",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "array": [],
        "object": {},
    }.get(json_type, "test")
