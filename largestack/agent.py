"""Public Agent class — primary interface for Largestack AI.

Features:
- Structured output via response_model (Pydantic)
- Shared memory across agents
- Agent-level retry with fallback
- Completion/error callbacks
- Session-based chat
"""
from __future__ import annotations
import logging

log = logging.getLogger("largestack.agent")
from typing import Any, AsyncIterator, Type
from pydantic import BaseModel
from largestack._core.config import get_config
from largestack._core.engine import AgentEngine
from largestack._core.gateway import LLMGateway
from largestack._core.steering import SteeringEngine
from largestack._core.tools import ToolRegistry
from largestack._guard.pipeline import GuardrailPipeline
from largestack._memory.buffer import ConversationMemory
from largestack.types import AgentResult

class Agent:
    """AI Agent with tracing, cost control, guardrails, and structured output.

    Usage:
        agent = Agent(name="helper", llm="openai/gpt-4o-mini")
        result = await agent.run("Hello!")
        
        # Structured output
        result = await agent.run("Analyze data", response_model=MySchema)
        
        # Smart routing
        agent = Agent(name="auto", llm="auto")
    """
    def __init__(self, name: str, instructions: str = "You are a helpful assistant.",
                 llm: str|None=None, tools: list|None=None, guardrails: Any=None,
                 memory: Any=None, steering: list|None=None, cost_budget: float|None=None,
                 max_turns: int|None=None, tool_permissions: dict|None=None,
                 shared_memory: Any=None, retries: int=0, fallback: Any=None,
                 on_complete: Any=None, on_error: Any=None, **kw):
        self.config = get_config()
        self.name = name; self.instructions = instructions
        self.llm = llm or self.config.default_llm; self.tools = tools or []
        self.memory = memory if memory is not None else ConversationMemory()
        self.shared_memory = shared_memory  # SharedMemorySpace for cross-agent data
        self.cost_budget = cost_budget if cost_budget is not None else self.config.cost_budget
        self.max_turns = max_turns if max_turns is not None else self.config.max_turns
        self.tool_permissions = tool_permissions
        self.retries = retries  # 0 = no retry, 1 = one retry (2 attempts total)
        self.fallback = fallback  # Fallback Agent if this one fails
        self._on_complete = on_complete
        self._on_error = on_error

        if self.config.trace_enabled:
            try:
                from largestack._observe.tracer import setup_tracing
                setup_tracing(self.config.trace_db_path)
            except Exception as _e: log.debug(f"tracing setup failed: {_e}")

        self._reg = ToolRegistry()
        for t in self.tools: self._reg.register(t)
        self._steering_rules = steering or []
        self._steer = SteeringEngine(self._steering_rules)

        if guardrails is False:
            # Explicit opt-out for benchmarks/tests/local trusted runs.
            self._guards = None
        elif isinstance(guardrails, GuardrailPipeline):
            self._guards = guardrails
        elif guardrails:
            self._guards = self._build_guards(guardrails)
        elif self.config.guardrails_enabled:
            self._guards = self._default_guards()
        else:
            self._guards = None

        self._gw = LLMGateway(self.config)
        self.tool_permissions = tool_permissions  # store for engine rebuild on registry change
        self._engine = AgentEngine(name=name, instructions=instructions, llm=self.llm,
            gateway=self._gw, tool_registry=self._reg, steering_engine=self._steer,
            config=self.config, tool_permissions=tool_permissions, guardrails=self._guards,
            memory=self.memory, max_turns=self.max_turns, cost_budget=self.cost_budget)

    @property
    def _tool_registry(self):
        return self._reg

    @property
    def guardrails(self):
        """Public read-only access to the configured guardrail pipeline.

        Returns the ``GuardrailPipeline`` configured at construction time, or
        ``None`` if no guardrails were configured.
        """
        return self._guards
    
    @_tool_registry.setter
    def _tool_registry(self, registry):
        """Allow decorator API to inject its own registry."""
        self._reg = registry
        # Rebuild engine with new registry
        self._engine = AgentEngine(name=self.name, instructions=self.instructions, llm=self.llm,
            gateway=self._gw, tool_registry=self._reg, steering_engine=self._steer,
            config=self.config, tool_permissions=getattr(self, "tool_permissions", None),
            guardrails=self._guards, memory=self.memory,
            max_turns=self.max_turns, cost_budget=self.cost_budget)
    


    async def aclose(self) -> None:
        """Close owned async provider/client resources.

        Required for live provider tests and short-lived asyncio.run(...)
        calls where the event loop closes immediately after the agent call.
        """
        import asyncio
        import contextlib
        import inspect

        seen: set[int] = set()

        async def _close_obj(obj) -> None:
            if obj is None:
                return

            oid = id(obj)
            if oid in seen:
                return
            seen.add(oid)

            # Close provider dictionaries first, e.g. Gateway.providers.
            providers = getattr(obj, "providers", None)
            if isinstance(providers, dict):
                for provider in list(providers.values()):
                    await _close_obj(provider)

            # Close common nested owners/clients.
            for name in (
                "_gw", "gateway",
                "_engine", "engine",
                "_provider", "provider",
                "_llm_provider", "llm_provider",
                "_client", "client",
                "_c",
                "_llm", "llm",
                "_router", "router",
            ):
                child = getattr(obj, name, None)
                if child is not None and child is not obj:
                    await _close_obj(child)

            # Finally close the object itself.
            close = getattr(obj, "aclose", None) or getattr(obj, "close", None)
            if close is not None and obj is not self:
                with contextlib.suppress(Exception):
                    result = close()
                    if inspect.isawaitable(result):
                        await result

        await _close_obj(self)

        with contextlib.suppress(Exception):
            await asyncio.sleep(0)
            await asyncio.sleep(0.20)

    async def run(self, task: str, response_model: Type[BaseModel] | None = None, images: list[str] | None = None, **kw) -> AgentResult | BaseModel:
        """Run agent on task. Optionally parse into Pydantic model.
        
        Args:
            task: The task/question
            response_model: If set, parse response into this Pydantic model
        
        v0.3.6: Per-run cost tracking — does NOT reset shared gateway cost tracker.
        Two concurrent runs on the same gateway no longer overwrite each other's
        cost data. Per-call cost is read off each `ChatResponse.cost` and
        accumulated by the engine into `AgentResult.total_cost`.
        """
        # v0.3.6: do NOT reset shared self._gw.cost_tracker — concurrent runs
        # on the same gateway would race. Per-run cost is computed from the
        # response objects in the engine.execute() loop.
        
        # Vision support — multimodal messages WITH guardrails
        if images:
            from largestack._core.vision import build_vision_messages
            from largestack.testing import _capture_message  # v0.3.10
            msgs = build_vision_messages(task, images, self.instructions)
            for _m in msgs:
                _capture_message(_m)  # v0.3.10
            # Run input guardrails on vision content too
            if self._guards:
                text_msgs = [{"role": m.get("role","user"), "content": task} for m in msgs if m.get("role") == "user"]
                await self._guards.check_input(text_msgs)
            # v0.3.10: honor Agent.override() on the vision path too
            if getattr(self._engine, "_test_model", None) is not None:
                raw = await self._engine._test_model.chat(messages=msgs, model=self.llm, tools=None)
                from largestack._core.engine import _adapt_test_model_response
                resp = _adapt_test_model_response(raw, self.llm)
            else:
                resp = await self._gw.chat(model=self.llm, messages=msgs, agent_name=self.name)
            _capture_message({"role": "assistant", "content": resp.content})  # v0.3.10
            # Run output guardrails
            if self._guards:
                await self._guards.check_output(resp)
            result = AgentResult(content=resp.content, agent_name=self.name,
                total_cost=resp.cost, trace_id="vision", duration_ms=resp.latency_ms)
            if self.shared_memory:
                await self.shared_memory.put(f"{self.name}_output", result.content)
            if self._on_complete: self._safe_callback(self._on_complete, result)
            return result
        
        last_error = None
        for attempt in range(1 + self.retries):  # 1 initial + N retries
            try:
                if response_model:
                    from largestack._core.structured import run_structured
                    result = await run_structured(self, task, response_model, max_retries=2, **kw)
                    if self._on_complete: self._safe_callback(self._on_complete, result)
                    return result
                
                result = await self._engine.execute(task, **kw)
                
                # Write to shared memory if configured
                if self.shared_memory:
                    import asyncio
                    await self.shared_memory.put(f"{self.name}_output", result.content)
                    await self.shared_memory.put(f"{self.name}_result", result)
                
                if self._on_complete: self._safe_callback(self._on_complete, result)
                return result
            except Exception as e:
                last_error = e
                if self._on_error: self._safe_callback(self._on_error, e)
                if attempt < self.retries:
                    import logging; logging.getLogger("largestack.agent").warning(
                        f"Agent '{self.name}' attempt {attempt+1}/{self.retries} failed: {e}")
        
        # Try fallback agent
        if self.fallback:
            try:
                return await self.fallback.run(task, response_model=response_model, **kw)
            except Exception:
                pass
        
        raise last_error

    def run_sync(
        self,
        task: str,
        response_model: Type[BaseModel] | None = None,
        images: list[str] | None = None,
        **kw,
    ) -> AgentResult | BaseModel:
        """Synchronous wrapper around ``run()`` for non-async callers (v0.7.0).

        Use this when you're in a synchronous script, Jupyter notebook
        without async support, or any context that hasn't already
        constructed an event loop.

        Behavior:
        - If no event loop is running, this calls ``asyncio.run(self.run(...))``.
        - If an event loop IS already running (e.g. inside a notebook
          with ipykernel + nest_asyncio, or inside another async
          function), it raises ``RuntimeError`` directing the caller to
          ``await agent.run(...)`` instead. Silent fallback would deadlock.

        Args:
            same as ``run()``.

        Returns:
            same as ``run()``.

        Raises:
            RuntimeError: if called from an already-running event loop.
        """
        import asyncio
        try:
            # If a loop is running, asyncio.get_running_loop() returns it
            asyncio.get_running_loop()
            raise RuntimeError(
                "run_sync() cannot be called from an active event loop. "
                "Use `await agent.run(...)` instead."
            )
        except RuntimeError as e:
            # No running loop — safe to spin one up
            if "no running event loop" not in str(e).lower() and "no current event loop" not in str(e).lower():
                if "cannot be called from an active" in str(e):
                    raise  # propagate our own error message
                # Otherwise fall through (some Python versions raise different messages)
        return asyncio.run(
            self.run(task, response_model=response_model, images=images, **kw)
        )

    async def stream(self, task: str, **kw) -> AsyncIterator[str]:
        async for tok in self._engine.stream(task, **kw): yield tok

    def clone(self, **overrides) -> "Agent":
        """Clone with all attributes forwarded. Overrides take precedence.
        
        Note: steering rules forward via stored list (not the SteeringEngine instance).
        v0.3.10: removed dead `response_model` key — there is no `_response_model`
        attribute on Agent (response_model is per-call, not per-instance).
        """
        p = {
            "name": self.name,
            "instructions": self.instructions,
            "llm": self.llm,
            "tools": list(self.tools) if self.tools else None,
            "cost_budget": self.cost_budget,
            "max_turns": self.max_turns,
            "guardrails": getattr(self, "_guards", None),
            "memory": getattr(self, "memory", None),
            "tool_permissions": getattr(self, "tool_permissions", None),
            "shared_memory": getattr(self, "shared_memory", None),
            "retries": getattr(self, "retries", 0),
            "fallback": getattr(self, "fallback", None),
            "on_complete": getattr(self, "_on_complete", None),
            "on_error": getattr(self, "_on_error", None),
            "steering": getattr(self, "_steering_rules", None),
        }
        p = {k: v for k, v in p.items() if v is not None}
        p.update(overrides)
        return Agent(**p)

    def _safe_callback(self, cb, data):
        import asyncio
        try:
            if asyncio.iscoroutinefunction(cb):
                # Hold reference + log exceptions
                if not hasattr(self, '_callback_tasks'):
                    self._callback_tasks = set()
                task = asyncio.create_task(cb(data))
                self._callback_tasks.add(task)
                def _on_done(t):
                    self._callback_tasks.discard(t)
                    if t.exception():
                        log.warning(f"Callback failed: {t.exception()}")
                task.add_done_callback(_on_done)
            else:
                cb(data)
        except Exception as e:
            log.warning(f"Callback error: {e}")

    def _default_guards(self) -> GuardrailPipeline:
        guards = []
        if self.config.pii_detection:
            from largestack._guard.pii import PIIGuard; guards.append(PIIGuard(action="warn"))
        if self.config.injection_detection:
            from largestack._guard.injection import InjectionGuard; guards.append(InjectionGuard())
        if self.config.hallucination_detection:
            from largestack._guard.hallucination import HallucinationGuard; guards.append(HallucinationGuard())
        if self.config.toxicity_detection:
            from largestack._guard.toxicity import ToxicityGuard; guards.append(ToxicityGuard())
        if self.config.topic_blocklist:
            from largestack._guard.topic import TopicGuard
            guards.append(TopicGuard(blocklist=self.config.topic_blocklist.split(",")))
        return GuardrailPipeline(guards)

    def _build_guards(self, config) -> GuardrailPipeline:
        if isinstance(config, list):
            guards = []
            valid_names = {"pii", "pii_ml", "injection", "prompt_guard", "hallucination",
                           "nli_hallucination", "toxicity", "topic"}
            for name in config:
                if name == "pii": from largestack._guard.pii import PIIGuard; guards.append(PIIGuard())
                elif name == "pii_ml": from largestack._guard.pii_ml import EnhancedPIIGuard; guards.append(EnhancedPIIGuard())
                elif name == "injection": from largestack._guard.injection import InjectionGuard; guards.append(InjectionGuard())
                elif name == "prompt_guard": from largestack._guard.prompt_guard import PromptGuard2; guards.append(PromptGuard2())
                elif name == "hallucination": from largestack._guard.hallucination import HallucinationGuard; guards.append(HallucinationGuard())
                elif name == "nli_hallucination": from largestack._guard.nli_hallucination import NLIHallucinationGuard; guards.append(NLIHallucinationGuard())
                elif name == "toxicity": from largestack._guard.toxicity import ToxicityGuard; guards.append(ToxicityGuard())
                elif name == "topic": from largestack._guard.topic import TopicGuard; guards.append(TopicGuard())
                else:
                    raise ValueError(f"Unknown guardrail '{name}'. Valid: {sorted(valid_names)}")
            return GuardrailPipeline(guards)
        return GuardrailPipeline()

    def __repr__(self): return f"Agent(name='{self.name}', llm='{self.llm}', tools={self._reg.list_names()})"

    # ------------------------------------------------------------------
    # Test override (v0.3.10)
    # ------------------------------------------------------------------
    def override(self, *, model=None):
        """Context manager: temporarily swap in a TestModel/FunctionModel.

        Inside the block, the engine bypasses the gateway and calls
        ``model.chat(messages, model, tools, **kw)`` directly. Real provider
        calls do not happen, so this works in CI without API keys.

        Example:
            from largestack.testing import TestModel
            test_model = TestModel(custom_output_text="canned")
            with agent.override(model=test_model):
                result = await agent.run("anything")
            assert result.content == "canned"

        Args:
            model: A TestModel, FunctionModel, or any object with an
                   ``async def chat(messages, model, tools, **kw) -> dict``
                   method matching the TestModel contract.

        Returns:
            A context manager that restores the previous override on exit.

        Raises:
            ValueError: if ``model`` is None.
        """
        if model is None:
            raise ValueError("Agent.override() requires a model= keyword argument")

        agent = self

        class _Override:
            def __enter__(_self):
                _self._prev = getattr(agent._engine, "_test_model", None)
                agent._engine._test_model = model
                return agent

            def __exit__(_self, exc_type, exc, tb):
                agent._engine._test_model = _self._prev
                _self._prev = None

        return _Override()
