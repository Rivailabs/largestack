"""Tool system — @tool decorator, registry, schema gen, execution with sandbox+timeout."""
from __future__ import annotations
import asyncio, enum, inspect, json, logging, time, hashlib
from types import UnionType
from typing import Any, Callable, Literal, Union, get_args, get_origin, get_type_hints
from largestack.errors import ToolExecutionError, ToolPermissionError
from largestack.types import ToolCall, ToolResult

log = logging.getLogger("largestack.tools")

# P1: comprehensive type → JSON-schema mapping
def _type_to_schema(t: Any) -> dict:
    """Convert a Python type annotation to JSON schema. Handles:
    - primitives (str, int, float, bool)
    - Optional[X] / X | None (PEP 604) → schema for X
    - Union[X, Y] / X | Y (PEP 604) → anyOf
    - List[X] / list[X] → array with items
    - Dict[K,V] → object with additionalProperties
    - Literal["a","b"] → enum
    - Enum subclass → enum
    - Pydantic BaseModel → its model_json_schema()
    - dict, list, Any → loose object/array/any
    """
    if t is None or t is type(None):
        return {"type": "null"}
    
    primitives = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if t in primitives:
        return {"type": primitives[t]}
    
    origin = get_origin(t); args = get_args(t)
    
    # Literal["a", "b"]
    if origin is Literal:
        return {"type": "string", "enum": list(args)}
    
    # P0-4 (v0.3.3): handle BOTH typing.Union AND PEP 604 types.UnionType
    if origin is Union or origin is UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_schema(non_none[0])
        return {"anyOf": [_type_to_schema(a) for a in non_none]}
    
    # list / List
    if origin in (list, tuple, set, frozenset) or t is list:
        item_type = args[0] if args else Any
        items = _type_to_schema(item_type) if item_type is not Any else {}
        return {"type": "array", "items": items}
    
    # dict / Dict
    if origin is dict or t is dict:
        if args and len(args) == 2:
            return {"type": "object", "additionalProperties": _type_to_schema(args[1])}
        return {"type": "object"}
    
    # Enum subclass
    try:
        if isinstance(t, type) and issubclass(t, enum.Enum):
            return {"type": "string", "enum": [m.value for m in t]}
    except TypeError:
        pass
    
    # Pydantic BaseModel
    try:
        if isinstance(t, type):
            if hasattr(t, "model_json_schema"):  # Pydantic v2
                return t.model_json_schema()
            if hasattr(t, "schema"):  # Pydantic v1
                return t.schema()
    except Exception:
        pass
    
    # Fallback
    return {"type": "string"}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}; self._schemas: dict[str, dict] = {}

    def register(self, fn: Callable, name: str | None = None, description: str | None = None):
        s = getattr(fn, "_tool_schema", None) or self._gen(fn)
        if name: s["name"] = name
        if description: s["description"] = description
        self._tools[s["name"]] = fn; self._schemas[s["name"]] = s

    def get(self, name: str) -> Callable | None: return self._tools.get(name)
    def get_schema(self, name: str) -> dict | None: return self._schemas.get(name)
    def get_all_schemas(self) -> list[dict]: return list(self._schemas.values())
    def list_names(self) -> list[str]: return list(self._tools.keys())

    @staticmethod
    def _gen(fn: Callable) -> dict:
        hints = get_type_hints(fn); sig = inspect.signature(fn); props = {}; req = []
        for n, p in sig.parameters.items():
            if n in ("self", "cls", "ctx"): continue
            ann = hints.get(n)
            if ann and "RunContext" in str(ann): continue
            ann = hints.get(n, str)
            # P1: full type mapping (was: only primitive types)
            schema = _type_to_schema(ann)
            props[n] = schema
            if p.default != inspect.Parameter.empty:
                props[n]["default"] = p.default
            else:
                req.append(n)
        return {"name": fn.__name__, "description": inspect.getdoc(fn) or "",
                "parameters": {"type": "object", "properties": props, "required": req}}

def tool(fn=None, *, timeout=30.0, retries=1, sandbox=None, name=None, description=None,
         idempotent: bool = False,
         backoff: str = "exponential",
         backoff_max_seconds: float = 30.0,
         backoff_jitter: bool = True,
         circuit_breaker_threshold: int = 0,
         circuit_breaker_window_seconds: float = 60.0,
         circuit_breaker_cooldown_seconds: float = 30.0):
    """Decorator to define a tool. Type hints → JSON Schema auto.

    Args:
        timeout: Per-call timeout in seconds.
        retries: Number of retries on failure (in addition to the first attempt).
        idempotent: If True, identical (name, params) calls are cached for
                    the agent's lifetime (LRU+TTL bounded). Default False —
                    same call repeats execute the tool. Set idempotent=True
                    only for pure functions (no DB writes, no time-dependent
                    output, no external state changes).

        # v0.6.0 — retry/circuit-breaker enhancements:
        backoff: ``"exponential"`` (default), ``"linear"``, ``"constant"``, or
            ``"none"``. Controls the delay between retries.
        backoff_max_seconds: Cap on a single backoff sleep. Default 30s.
        backoff_jitter: If True (default), apply ±25% randomized jitter to
            backoff delays — prevents thundering herd under shared failure
            modes.
        circuit_breaker_threshold: If > 0, open the circuit after this many
            consecutive failures within ``circuit_breaker_window_seconds``,
            and short-circuit subsequent calls for ``circuit_breaker_cooldown_seconds``.
            Default 0 = disabled (legacy behavior).
        circuit_breaker_window_seconds: Time window for failure counting.
        circuit_breaker_cooldown_seconds: How long the circuit stays open.
    """
    def dec(f):
        s = ToolRegistry._gen(f)
        if name: s["name"] = name
        if description: s["description"] = description
        f._tool_schema = s; f._tool_timeout = timeout; f._tool_retries = retries
        f._tool_sandbox = sandbox; f._is_largestack_tool = True
        f._tool_idempotent = idempotent
        # v0.6.0 retry/CB config attached as function attributes
        f._tool_backoff = backoff
        f._tool_backoff_max = backoff_max_seconds
        f._tool_backoff_jitter = backoff_jitter
        f._tool_cb_threshold = circuit_breaker_threshold
        f._tool_cb_window = circuit_breaker_window_seconds
        f._tool_cb_cooldown = circuit_breaker_cooldown_seconds
        return f
    return dec(fn) if fn else dec

class ToolExecutor:
    # B-10 (v0.3.4): bound the idempotency cache to prevent memory leak in long-lived agents.
    # OrderedDict gives LRU semantics; entries also have TTL to prevent stale results.
    _IDEM_MAX_SIZE = 1024
    _IDEM_TTL_SECONDS = 3600

    def __init__(self, registry: ToolRegistry, permissions: dict|None=None, agent_name="default",
                 policy: Any = None):
        from collections import OrderedDict, deque
        self.registry = registry; self.perms = permissions or {}; self.agent = agent_name
        # v1.1.1: optional ToolAccessPolicy (rate limit + param validation). When
        # set, it is actually enforced in execute() — previously it was never called.
        self.policy = policy
        # value = (content, inserted_at)
        self._idem: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
        # v0.6.0 circuit-breaker state per tool name:
        #   _cb_failures: deque of recent failure timestamps (within window)
        #   _cb_open_until: time after which the circuit auto-closes
        self._cb_failures: dict[str, "deque[float]"] = {}
        self._cb_open_until: dict[str, float] = {}

    def _cb_should_skip(self, fn_name: str, threshold: int, window: float, cooldown: float) -> str | None:
        """v0.6.0: returns short-circuit error string if circuit open, else None.

        Cleans up state as a side-effect: prunes stale failures, auto-closes
        open circuit when cooldown elapsed.
        """
        if threshold <= 0:
            return None
        now = time.monotonic()
        # If currently open and cooldown not yet elapsed, short-circuit
        open_until = self._cb_open_until.get(fn_name, 0.0)
        if now < open_until:
            remaining = open_until - now
            return f"Circuit open for tool {fn_name!r} (cooldown {remaining:.1f}s remaining)"
        elif open_until and now >= open_until:
            # Cooldown elapsed — close the circuit, reset counter
            self._cb_open_until.pop(fn_name, None)
            self._cb_failures.pop(fn_name, None)
        return None

    def _cb_record_failure(self, fn_name: str, threshold: int, window: float, cooldown: float):
        """v0.6.0: record a failure; open the circuit if threshold reached."""
        if threshold <= 0:
            return
        from collections import deque
        now = time.monotonic()
        dq = self._cb_failures.setdefault(fn_name, deque())
        dq.append(now)
        # Prune outside the window
        while dq and (now - dq[0]) > window:
            dq.popleft()
        if len(dq) >= threshold:
            self._cb_open_until[fn_name] = now + cooldown
            log.warning(
                f"Circuit breaker OPEN for tool {fn_name!r}: "
                f"{len(dq)} failures in {window}s, cooling down for {cooldown}s"
            )

    def _cb_record_success(self, fn_name: str):
        """v0.6.0: a success clears the failure counter for this tool."""
        self._cb_failures.pop(fn_name, None)

    @staticmethod
    def _backoff_delay(attempt: int, strategy: str, max_seconds: float, jitter: bool) -> float:
        """v0.6.0: compute the sleep before the *next* retry attempt.

        Strategies:
            exponential: 2^attempt seconds (1, 2, 4, 8, ...)
            linear:      attempt+1 seconds (1, 2, 3, ...)
            constant:    1 second
            none:        0 seconds
        """
        if strategy == "none":
            return 0.0
        if strategy == "linear":
            base = float(attempt + 1)
        elif strategy == "constant":
            base = 1.0
        else:  # exponential (default)
            base = float(2 ** attempt)
        delay = min(base, max_seconds)
        if jitter:
            import random
            delay = delay * (0.75 + 0.5 * random.random())  # ±25%
        return max(0.0, delay)


    def _idem_get(self, key: str) -> str | None:
        entry = self._idem.get(key)
        if entry is None: return None
        content, ts = entry
        if time.time() - ts > self._IDEM_TTL_SECONDS:
            # Expired — drop and miss
            self._idem.pop(key, None)
            return None
        # LRU: move to end (most-recently-used)
        self._idem.move_to_end(key)
        return content

    def _idem_put(self, key: str, content: str) -> None:
        # Evict oldest if at capacity
        if key in self._idem:
            self._idem.move_to_end(key)
        self._idem[key] = (content, time.time())
        while len(self._idem) > self._IDEM_MAX_SIZE:
            self._idem.popitem(last=False)  # FIFO eviction of LRU

    @staticmethod
    def _coerce_params(fn: Callable, params: dict) -> dict:
        """Best-effort coercion of tool args to their annotated scalar types.

        Models sometimes send numbers/bools as strings; without coercion an
        ``int`` tool receiving ``"19"`` does string concatenation. Non-scalar or
        unknown-typed args pass through unchanged; failed coercions are left as-is
        so the tool's own error surfaces.
        """
        if not isinstance(params, dict) or not params:
            return params
        try:
            hints = get_type_hints(fn)
        except Exception:
            return params
        out = dict(params)
        for name, val in params.items():
            hint = hints.get(name)
            if hint in (int, float) and isinstance(val, str):
                try:
                    out[name] = hint(val.strip())
                except (ValueError, TypeError):
                    pass
            elif hint is int and isinstance(val, float) and float(val).is_integer():
                out[name] = int(val)
            elif hint is bool and isinstance(val, str):
                low = val.strip().lower()
                if low in ("true", "1", "yes"):
                    out[name] = True
                elif low in ("false", "0", "no"):
                    out[name] = False
        return out

    async def execute(self, tc: ToolCall) -> ToolResult:
        t0 = time.monotonic()
        # v1.1.1: permission denial returns a recoverable tool error instead of
        # raising out of the whole agent run (consistent with runtime tool errors,
        # so the model can self-correct to an allowed tool).
        try:
            self._check_perms(tc.name)
        except ToolPermissionError as e:
            return ToolResult(tool_call_id=tc.id, content="", error=str(e),
                              duration_ms=(time.monotonic() - t0) * 1000)
        # v1.1.1: enforce the ToolAccessPolicy (rate limit + parameter validation)
        # if one is configured — this is the OWASP ASI02 control wired into the loop.
        if self.policy is not None:
            try:
                ok, reason = await self.policy.enforce(self.agent, tc.name, tc.params)
            except Exception as e:  # never let policy internals abort the run
                ok, reason = False, f"policy error: {e}"
            if not ok:
                return ToolResult(tool_call_id=tc.id, content="", error=f"Tool policy denied: {reason}",
                                  duration_ms=(time.monotonic() - t0) * 1000)
        fn = self.registry.get(tc.name)
        if not fn: return ToolResult(tool_call_id=tc.id, content="", error=f"Tool '{tc.name}' not found")
        # v1.1.1: coerce args to their annotated scalar types. Models often send
        # numbers as strings ("19"); without this, add(a:int,b:int) would do string
        # concatenation ("19"+"23"="1923"). Best-effort; unknown/complex types pass through.
        call_params = self._coerce_params(fn, tc.params)
        # v0.3.5: Only cache results for tools explicitly marked idempotent.
        # Default False — most tools mutate state (DB writes, API calls with side effects).
        is_idempotent = getattr(fn, "_tool_idempotent", False)
        ik = None
        if is_idempotent:
            ik = hashlib.sha256(f"{tc.name}:{json.dumps(tc.params, sort_keys=True)}".encode()).hexdigest()
            cached = self._idem_get(ik)
            if cached is not None:
                return ToolResult(tool_call_id=tc.id, content=cached, duration_ms=(time.monotonic()-t0)*1000)
        to = getattr(fn, "_tool_timeout", 30.0)
        # P1.2: actually use _tool_retries metadata
        retries = getattr(fn, "_tool_retries", 0)

        # v0.6.0 retry/CB config
        backoff_strategy = getattr(fn, "_tool_backoff", "exponential")
        backoff_max = getattr(fn, "_tool_backoff_max", 30.0)
        backoff_jitter = getattr(fn, "_tool_backoff_jitter", True)
        cb_threshold = getattr(fn, "_tool_cb_threshold", 0)
        cb_window = getattr(fn, "_tool_cb_window", 60.0)
        cb_cooldown = getattr(fn, "_tool_cb_cooldown", 30.0)

        # v0.6.0: short-circuit if breaker is open
        cb_msg = self._cb_should_skip(tc.name, cb_threshold, cb_window, cb_cooldown)
        if cb_msg is not None:
            return ToolResult(
                tool_call_id=tc.id, content="", error=cb_msg,
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        last_err = None
        for attempt in range(retries + 1):
            try:
                if asyncio.iscoroutinefunction(fn):
                    result = await asyncio.wait_for(fn(**call_params), timeout=to)
                else:
                    # P1.1: sync tools also get a real timeout via thread offload
                    result = await asyncio.wait_for(
                        asyncio.to_thread(fn, **call_params), timeout=to
                    )
                content = str(result) if result is not None else ""
                if is_idempotent and ik is not None:
                    self._idem_put(ik, content)
                # v0.6.0: success clears any previous CB failures
                self._cb_record_success(tc.name)
                return ToolResult(tool_call_id=tc.id, content=content,
                                  duration_ms=(time.monotonic()-t0)*1000)
            except asyncio.TimeoutError:
                last_err = f"Timeout after {to}s"
            except Exception as e:
                last_err = str(e)
            if attempt < retries:
                # v0.6.0: configurable backoff + jitter
                delay = self._backoff_delay(
                    attempt, backoff_strategy, backoff_max, backoff_jitter
                )
                if delay > 0:
                    await asyncio.sleep(delay)

        # v0.6.0: failure path — record into CB tracker
        self._cb_record_failure(tc.name, cb_threshold, cb_window, cb_cooldown)
        return ToolResult(tool_call_id=tc.id, content="", error=last_err,
                          duration_ms=(time.monotonic()-t0)*1000)

    def _check_perms(self, name: str):
        deny = self.perms.get("deny", []); allow = self.perms.get("allow")
        if deny and name in deny: raise ToolPermissionError(name, self.agent)
        if allow and name not in allow: raise ToolPermissionError(name, self.agent)
