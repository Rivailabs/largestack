"""Modern decorator API with typed dependency injection — PydanticAI-style.

Usage:
    from dataclasses import dataclass
    from largestack.decorators import Agent, RunContext, ModelRetry
    
    @dataclass
    class Deps:
        db: Database
        user_id: str
    
    agent = Agent[Deps, str](
        'openai/gpt-4o-mini',
        deps_type=Deps,
        instructions='You are a support agent.',
    )
    
    @agent.tool
    async def search_kb(ctx: RunContext[Deps], query: str) -> list[str]:
        '''Search knowledge base.'''
        return await ctx.deps.db.search(query, ctx.deps.user_id)
    
    @agent.output_validator
    async def check(ctx: RunContext[Deps], output: str) -> str:
        if 'badword' in output:
            raise ModelRetry('Avoid bad words')
        return output
    
    result = await agent.run('Find docs', deps=Deps(db=mydb, user_id='u1'))
"""
from __future__ import annotations
import inspect
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Generic, TypeVar, get_type_hints, get_origin, get_args,
    Awaitable, Union, Optional, overload,
)

log = logging.getLogger("largestack.decorators")

# Async-safe per-run context (replaces self._current_ctx for concurrency safety)
_current_ctx_var: ContextVar = ContextVar("largestack_current_ctx")

DepsT = TypeVar("DepsT")
OutputT = TypeVar("OutputT")
T = TypeVar("T")


class ModelRetry(Exception):
    """Raised inside output validators to ask the LLM to retry with feedback."""
    def __init__(self, hint: str):
        self.hint = hint
        super().__init__(hint)


@dataclass
class RunContext(Generic[DepsT]):
    """Context passed to tools and validators with typed dependencies.
    
    Attributes:
        deps: User-provided dependencies of type DepsT
        usage: Accumulated token + cost usage
        retry_count: Number of retries so far
        messages: Conversation history
        model: Current model identifier
    """
    deps: DepsT
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "cost": 0.0})
    retry_count: int = 0
    messages: list = field(default_factory=list)
    model: str = ""
    
    def increment_retry(self) -> None:
        self.retry_count += 1
    
    def add_usage(self, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0.0) -> None:
        self.usage["input_tokens"] += input_tokens
        self.usage["output_tokens"] += output_tokens
        self.usage["cost"] += cost


@dataclass
class ToolDefinition:
    """Tool metadata extracted from decorated function."""
    name: str
    description: str
    parameters_schema: dict
    function: Callable
    takes_ctx: bool
    
    async def call(self, ctx: RunContext, **kwargs) -> Any:
        """Invoke the tool, passing ctx if it accepts one."""
        if self.takes_ctx:
            if inspect.iscoroutinefunction(self.function):
                return await self.function(ctx, **kwargs)
            return self.function(ctx, **kwargs)
        if inspect.iscoroutinefunction(self.function):
            return await self.function(**kwargs)
        return self.function(**kwargs)


def _extract_tool_schema(func: Callable, takes_ctx: bool) -> dict:
    """Extract JSON schema from function signature + docstring."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    
    properties = {}
    required = []
    
    params = list(sig.parameters.items())
    if takes_ctx and params:
        params = params[1:]  # Skip ctx parameter
    
    for name, param in params:
        if name in ("self", "cls"):
            continue
        py_type = hints.get(name, str)
        json_type = _python_to_json_type(py_type)
        properties[name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _python_to_json_type(py_type: Any) -> str:
    """Map Python type to JSON schema type. Handles PEP 604 unions (X | None)."""
    from types import UnionType
    origin = get_origin(py_type)
    # P0-4 (v0.3.3): handle BOTH typing.Union AND PEP 604 X | None
    if origin is Union or origin is UnionType:
        args = [a for a in get_args(py_type) if a is not type(None)]
        if args:
            return _python_to_json_type(args[0])
    if py_type is str: return "string"
    if py_type is int: return "integer"
    if py_type is float: return "number"
    if py_type is bool: return "boolean"
    if origin is list or py_type is list: return "array"
    if origin is dict or py_type is dict: return "object"
    return "string"


def _function_takes_ctx(func: Callable) -> bool:
    """Check if first parameter is RunContext."""
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    if not params:
        return False
    first = params[0]
    if first.annotation is inspect.Parameter.empty:
        return first.name in ("ctx", "context", "run_context")
    ann = first.annotation
    if ann is RunContext:
        return True
    origin = get_origin(ann)
    if origin is RunContext:
        return True
    # String annotation (forward ref)
    if isinstance(ann, str) and "RunContext" in ann:
        return True
    return False


class Agent(Generic[DepsT, OutputT]):
    """Typed agent with decorator-based tool registration.
    
    ``DepsT`` is the type of user dependencies passed via ``deps=``;
    ``OutputT`` is the expected output type (``str``, a ``BaseModel`` subclass, etc.).
    
    Example:
        ```python
        agent = Agent[MyDeps, str](
            "openai/gpt-4o-mini",
            deps_type=MyDeps,
            instructions="Be helpful.",
        )
        ```
    """
    
    def __init__(
        self,
        model: str,
        *,
        deps_type: type = type(None),
        output_type: type = str,
        instructions: str = "",
        name: str = "agent",
        max_retries: int = 2,
        cost_budget: float = 1.0,
        guardrails=None,
        retries: int = 0,
    ):
        self.model = model
        self.deps_type = deps_type
        self.output_type = output_type
        self.instructions = instructions
        self.name = name
        self.max_retries = max_retries
        self.cost_budget = cost_budget
        self.guardrails = guardrails
        self.retries = retries
        
        self._tools: dict[str, ToolDefinition] = {}
        self._output_validators: list[Callable] = []
        self._instructions_funcs: list[Callable] = []
        
        # Lazy-import to avoid circular deps
        self._underlying_agent = None
    
    def tool(self, func: Callable | None = None, *, name: str | None = None,
             description: str | None = None) -> Callable:
        """Register a tool. Function may take RunContext[Deps] as first arg.
        
        Examples:
            @agent.tool
            async def search(ctx: RunContext[Deps], query: str) -> str:
                '''Search knowledge base.'''
                ...
            
            @agent.tool
            def calculate(x: int, y: int) -> int:
                '''Add two numbers.'''
                return x + y
        """
        def decorator(fn: Callable) -> Callable:
            takes_ctx = _function_takes_ctx(fn)
            tool_name = name or fn.__name__
            doc = description or (inspect.getdoc(fn) or "").strip().split("\n")[0]
            schema = _extract_tool_schema(fn, takes_ctx)
            
            self._tools[tool_name] = ToolDefinition(
                name=tool_name, description=doc,
                parameters_schema=schema, function=fn, takes_ctx=takes_ctx,
            )
            return fn
        
        if func is not None:
            return decorator(func)
        return decorator
    
    def tool_plain(self, func: Callable) -> Callable:
        """Register a tool that does NOT receive RunContext."""
        tool_name = func.__name__
        doc = (inspect.getdoc(func) or "").strip().split("\n")[0]
        schema = _extract_tool_schema(func, takes_ctx=False)
        
        self._tools[tool_name] = ToolDefinition(
            name=tool_name, description=doc,
            parameters_schema=schema, function=func, takes_ctx=False,
        )
        return func
    
    def output_validator(self, func: Callable) -> Callable:
        """Register output validator. Raise ModelRetry to request retry with hint.
        
        Example:
            @agent.output_validator
            async def check(ctx: RunContext[Deps], output: str) -> str:
                if invalid(output):
                    raise ModelRetry('reformat as JSON')
                return output
        """
        self._output_validators.append(func)
        return func
    
    def instructions_func(self, func: Callable) -> Callable:
        """Register dynamic instructions function.
        
        Example:
            @agent.instructions_func
            def get_instructions(ctx: RunContext[Deps]) -> str:
                return f"You help user {ctx.deps.user_id}"
        """
        self._instructions_funcs.append(func)
        return func
    
    def _get_underlying(self, ctx: "RunContext | None" = None):
        """Lazy-create the underlying largestack.Agent. Wraps tools that need ctx."""
        if self._underlying_agent is None:
            from largestack import Agent as BaseAgent
            from largestack._core.tools import ToolRegistry
            
            registry = ToolRegistry()
            for name, td in self._tools.items():
                # Wrap context tools using ContextVar (concurrency-safe)
                if td.takes_ctx:
                    _td = td  # bind via default to avoid late-binding
                    if inspect.iscoroutinefunction(_td.function):
                        async def wrapped(_td=_td, **kwargs):
                            current_ctx = _current_ctx_var.get()
                            return await _td.function(current_ctx, **kwargs)
                    else:
                        def wrapped(_td=_td, **kwargs):
                            current_ctx = _current_ctx_var.get()
                            return _td.function(current_ctx, **kwargs)
                    wrapped.__name__ = _td.name
                    wrapped.__doc__ = _td.description
                    wrapped._tool_schema = {
                        "name": _td.name,
                        "description": _td.description,
                        "parameters": _td.parameters_schema,
                    }
                    registry.register(wrapped, name=_td.name, description=_td.description)
                else:
                    registry.register(td.function, name=td.name, description=td.description)
            
            self._underlying_agent = BaseAgent(
                name=self.name,
                instructions=self.instructions,
                llm=self.model,
                cost_budget=self.cost_budget,
                guardrails=self.guardrails,
                retries=self.retries,
            )
            self._underlying_agent._tool_registry = registry
        return self._underlying_agent
    
    async def run(
        self,
        prompt: str,
        *,
        deps: DepsT | None = None,
        message_history: list | None = None,
    ) -> "AgentRunResult[OutputT]":
        """Run agent asynchronously."""
        ctx = RunContext(
            deps=deps if deps is not None else (None if self.deps_type is type(None) else self.deps_type()),
            model=self.model,
        )
        
        # Build instructions from base + dynamic
        instructions = self.instructions
        for func in self._instructions_funcs:
            try:
                if inspect.iscoroutinefunction(func):
                    extra = await func(ctx)
                else:
                    extra = func(ctx)
                instructions = f"{instructions}\n{extra}".strip()
            except Exception as e:
                log.warning(f"Instructions function failed: {e}")
        
        # Run via underlying agent
        underlying = self._get_underlying()
        # v0.3.6: save+restore instructions instead of permanent mutation.
        # Two concurrent runs would otherwise overwrite each other. The proper
        # long-term fix is per-call instruction kwargs threaded into the engine,
        # but save+restore protects the common case (sequential per-instance use).
        # For true concurrent use of the same decorator instance, callers
        # should clone the agent or use per-task instances.
        prev_instructions = underlying.instructions
        prev_engine_instructions = getattr(getattr(underlying, "_engine", None), "instructions", None)
        underlying.instructions = instructions
        if hasattr(underlying, "_engine"):
            underlying._engine.instructions = instructions
        # P0.1: set context via ContextVar (concurrency-safe across async runs)
        token = _current_ctx_var.set(ctx)
        
        last_error = None
        try:
            for attempt in range(self.max_retries + 1):
                try:
                    from pydantic import BaseModel as _BaseModel
                    from largestack._core.structured import build_structured_prompt, parse_structured
                    _wants_model = isinstance(self.output_type, type) and issubclass(self.output_type, _BaseModel)
                    _inner = build_structured_prompt(self.output_type, prompt) if _wants_model else prompt
                    result = await underlying.run(_inner)
                    if _wants_model:
                        try:
                            output = parse_structured(result.content, self.output_type)
                        except ValueError as _pe:
                            ctx.increment_retry()
                            last_error = _pe
                            if attempt < self.max_retries:
                                prompt = f"{prompt}\n\n[Previous reply was not valid JSON for the schema: {_pe}]"
                                continue
                            raise
                    else:
                        output = result.content
                    
                    # Run output validators
                    for validator in self._output_validators:
                        try:
                            if inspect.iscoroutinefunction(validator):
                                output = await validator(ctx, output)
                            else:
                                output = validator(ctx, output)
                        except ModelRetry as e:
                            ctx.increment_retry()
                            last_error = e
                            if attempt < self.max_retries:
                                prompt = f"{prompt}\n\n[Retry hint: {e.hint}]"
                                break
                            raise
                    else:
                        return AgentRunResult(
                            output=output,
                            usage=ctx.usage,
                            retry_count=ctx.retry_count,
                            cost=result.total_cost,
                            trace_id=result.trace_id,
                            tool_calls_made=list(getattr(result, "tool_calls_made", [])),
                            tool_calls_failed=list(getattr(result, "tool_calls_failed", [])),
                        )
                except ModelRetry as e:
                    ctx.increment_retry()
                    last_error = e
                    if attempt >= self.max_retries:
                        raise
            
            raise last_error or RuntimeError("Agent retries exhausted")
        finally:
            # P0.1: always reset ContextVar to avoid leaking ctx between concurrent runs
            _current_ctx_var.reset(token)
            # v0.3.6: restore previous instructions
            underlying.instructions = prev_instructions
            if hasattr(underlying, "_engine") and prev_engine_instructions is not None:
                underlying._engine.instructions = prev_engine_instructions
    
    def run_sync(self, prompt: str, **kwargs) -> "AgentRunResult[OutputT]":
        """Run agent synchronously (wraps async)."""
        import asyncio
        return asyncio.run(self.run(prompt, **kwargs))

    def override(self, *, model=None):
        """Context manager: temporarily swap in a TestModel/FunctionModel.

        Mirrors ``largestack.Agent.override()`` for the typed decorator API.
        Inside the block, no real provider call is made.

        Example:
            from largestack.testing import TestModel
            with agent.override(model=TestModel(custom_output_text="ok")):
                result = await agent.run("anything", deps=Deps(...))
            assert result.output == "ok"
        """
        if model is None:
            raise ValueError("Agent.override() requires a model= keyword argument")
        # Materialize the underlying agent so its engine exists
        underlying = self._get_underlying()
        return underlying.override(model=model)

    @property
    def tools(self) -> dict[str, ToolDefinition]:
        return self._tools.copy()

    def __class_getitem__(cls, params):
        return cls


@dataclass
class AgentRunResult(Generic[OutputT]):
    """Result of an agent run."""
    output: OutputT
    usage: dict
    retry_count: int = 0
    cost: float = 0.0
    trace_id: str = ""
    tool_calls_made: list = field(default_factory=list)
    tool_calls_failed: list = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"AgentRunResult(output={self.output!r}, cost=${self.cost:.6f}, retries={self.retry_count})"
