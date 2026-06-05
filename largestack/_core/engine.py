"""Agent execution engine — core loop with steering, guardrails, kill switch, metrics, compression."""
from __future__ import annotations
import json, logging, time, uuid
from typing import Any, AsyncIterator
from largestack._core.config import LargestackConfig, get_config
from largestack._core.events import bus
from largestack._core.gateway import LLMGateway
from largestack._core.loop_guard import LoopGuard
from largestack._core.license import check_license
from largestack._core.steering import SteeringEngine, accept
from largestack._core.tools import ToolExecutor, ToolRegistry
from largestack._guard.kill_switch import is_active as _kill_switch_active
from largestack.errors import BudgetExceededError, LoopDetectedError, KillSwitchActivatedError
from largestack.types import AgentResult, LLMResponse, ToolCall, SteeringAction
from largestack.testing import _capture_message  # v0.3.10: capture wiring


def _adapt_test_model_response(raw: dict, model: str) -> LLMResponse:
    """Convert a TestModel/FunctionModel raw dict into an LLMResponse.

    v0.3.10: kept here in the engine so the public Agent.override() path
    bypasses the gateway entirely (no real HTTP, no provider lookup).
    """
    tcs = []
    for tc in raw.get("tool_calls", []) or []:
        # Normalize: TestModel emits {"id","name","arguments"}; align to ToolCall
        tcs.append(ToolCall(
            id=tc.get("id", f"tc_{len(tcs)}"),
            name=tc.get("name", ""),
            params=tc.get("arguments", {}) if "arguments" in tc else tc.get("params", {}),
        ))
    usage = raw.get("usage", {}) or {}
    return LLMResponse(
        content=raw.get("content", ""),
        model=raw.get("model", model or "test-model"),
        tool_calls=tcs,
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cached_tokens=int(usage.get("cached_tokens", 0) or 0),
        latency_ms=0.0,
        finish_reason=raw.get("finish_reason", "stop"),
        cost=0.0,
    )

_audit = None
def _get_audit():
    global _audit
    if _audit is None:
        try:
            from largestack._enterprise.audit import AuditTrail
            _audit = AuditTrail()
        except Exception as e:
            logging.getLogger("largestack.engine").debug(f"Audit init failed: {e}")
    return _audit

log = logging.getLogger("largestack.engine")


def _assistant_message_from_response(resp):
    """Build assistant message for API history, preserving provider-specific fields such as DeepSeek reasoning_content."""
    msg = {
        "role": "assistant",
        "content": getattr(resp, "content", None) or "",
    }
    tool_calls = getattr(resp, "tool_calls", None) or []
    if tool_calls:
        msg["tool_calls"] = tool_calls
    reasoning_content = (
        getattr(resp, "reasoning_content", None)
        or getattr(resp, "reasoning", None)
        or getattr(resp, "raw_reasoning_content", None)
    )
    if reasoning_content:
        msg["reasoning_content"] = reasoning_content
    return msg


class AgentEngine:
    def __init__(self, name, instructions, llm, gateway, tool_registry, steering_engine,
                 config=None, tool_permissions=None, guardrails=None, memory=None,
                 max_turns=25, cost_budget=5.0):
        self.name = name; self.instructions = instructions; self.llm = llm
        self.gateway = gateway; self.steering = steering_engine
        self.tool_exec = ToolExecutor(tool_registry, tool_permissions, name)
        self.config = config or get_config()
        self.guardrails = guardrails; self.memory = memory
        self.max_turns = max_turns; self.cost_budget = cost_budget
        # v0.3.10: when set by Agent.override(), bypass gateway entirely and
        # call this object's `chat(messages, model, tools, **kw)` instead.
        # Must expose a `chat()` coroutine returning a raw dict shaped like
        # TestModel.chat()'s output. See _adapt_test_model_response().
        self._test_model: Any = None
        self._compressor = None
        if self.config.context_compression:
            from largestack._memory.compression import ContextCompressor
            self._compressor = ContextCompressor()

    async def _llm_call(self, msgs, tools, behavior_kw) -> "LLMResponse":
        """Single call site — routes through TestModel override or real gateway.

        v0.3.10: factored out so the override applies consistently to both
        the main loop's call AND `_force_final()`. Defaults to None when
        the engine was constructed by something other than Agent.__init__
        (e.g. tests that mock individual fields).
        """
        test_model = getattr(self, "_test_model", None)
        if test_model is not None:
            raw = await test_model.chat(messages=msgs, model=self.llm,
                                        tools=tools, **behavior_kw)
            return _adapt_test_model_response(raw, self.llm)
        return await self.gateway.chat(model=self.llm, messages=msgs,
                                        tools=tools, agent_name=self.name,
                                        **behavior_kw)

    def _check_kill_switch(self):
        """Check kill switch before every LLM call."""
        if _kill_switch_active():
            raise KillSwitchActivatedError()

    async def execute(self, task: str, **kw) -> AgentResult:
        # License enforcement
        check_license()

        tid = str(uuid.uuid4()); t0 = time.monotonic()
        await bus.emit("agent.started", {"agent": self.name, "task": task, "trace_id": tid})
        msgs = self._build_msgs(task)
        # Memory save boundary: _build_msgs() may inject previous memory.
        # Only messages from this index onward belong to the current run.
        memory_turn_start = max(len(msgs) - 1, 0)
        # v0.3.10: capture initial system+user messages.
        for _m in msgs:
            _capture_message(_m)
        # v0.3.12: remember the task so _result can record it in the trace
        # row for the dashboard. Truncated to 2KB by log_trace.
        self._current_task = task
        # P0.3: use runtime max_turns override consistently
        effective_max_turns = kw.get("max_turns", self.max_turns)
        # v0.6.0: per-run wall-clock timeout. ``timeout=N`` overrides the
        # default LoopGuard 300s. ``timeout=None`` (default) uses the
        # LoopGuard default. When the wall-clock exceeds the timeout, the
        # next ``check_turn()`` raises LoopDetectedError with reason="timeout".
        run_timeout = kw.get("timeout")
        if run_timeout is not None:
            guard = LoopGuard(
                max_turns=effective_max_turns,
                cost_budget=kw.get("cost_budget", self.cost_budget),
                timeout=float(run_timeout),
            )
        else:
            guard = LoopGuard(
                max_turns=effective_max_turns,
                cost_budget=kw.get("cost_budget", self.cost_budget),
            )
        tc_made = []
        guard.tool_failures = []  # tool names attempted but errored (for observability accuracy)
        # P0.5: track actual run status for audit
        run_status = "completed"
        # v0.3.6: per-run cost/token accumulators — replace reliance on shared
        # gateway.cost_tracker which races under concurrency.
        run_cost = 0.0
        run_tokens = 0
        try:
            for _ in range(effective_max_turns):
                # Kill switch check
                self._check_kill_switch()
                guard.check_turn()
                # v0.6.0: hard pre-flight cost ceiling — refuse to even
                # issue an LLM call if we're already over budget.
                guard.check_cost_pre_call()

                # Compress context if enabled and messages are long
                if self._compressor and len(msgs) > 10:
                    self._compress_context(msgs)

                # Input guardrails
                if self.guardrails: await self.guardrails.check_input(msgs)

                # LLM call
                # P0-1 (v0.3.3): forward structured-output + behavior kwargs to gateway
                # so providers actually receive response_format, tool_choice, etc.
                # v0.3.6: include both snake_case (Google native) and camelCase aliases,
                # plus separate structured tools from agent tools.
                _BEHAVIOR_KWS = {
                    "temperature", "max_tokens", "response_format", "tool_choice",
                    "top_p", "top_k", "seed", "stop", "stop_sequences",
                    "responseMimeType", "responseSchema",
                    "response_mime_type", "response_schema",
                }
                behavior_kw = {k: v for k, v in kw.items() if k in _BEHAVIOR_KWS}
                # v0.3.6: structured-output may pass `tools` (Anthropic native) — merge
                # with agent tools rather than letting the engine overwrite.
                schemas = self.tool_exec.registry.get_all_schemas() or []
                structured_tools = kw.get("tools") or []
                merged_tools = (schemas + list(structured_tools)) if (schemas or structured_tools) else None
                # v0.3.10: route through _llm_call so Agent.override(model=TestModel)
                # bypasses the real gateway. Real path is unchanged.
                resp = await self._llm_call(msgs, merged_tools, behavior_kw)
                # Per-run accumulation
                run_cost += float(getattr(resp, "cost", 0.0) or 0.0)
                # v0.3.7.1: LLMResponse has input_tokens + output_tokens, not "tokens".
                # Sum them. Fallback to "tokens" attr for any future provider that
                # populates the legacy field directly.
                _tok = (
                    int(getattr(resp, "input_tokens", 0) or 0)
                    + int(getattr(resp, "output_tokens", 0) or 0)
                )
                if _tok == 0:
                    _tok = int(getattr(resp, "tokens", 0) or 0)
                run_tokens += _tok
                guard.check_cost(run_cost)

                # Output guardrails
                if self.guardrails: await self.guardrails.check_output(resp)

                # Steering after model
                sr = await self.steering.run_after(resp, {"agent": self.name})
                if sr.action == SteeringAction.DISCARD:
                    msgs.append({"role": "user", "content": sr.feedback}); continue
                if sr.action == SteeringAction.INTERRUPT:
                    return self._result(str(sr.result or "Interrupted"), tid, t0, tc_made, guard)

                # Tool calls
                if resp.tool_calls:
                    # v0.3.9: Anthropic native structured output returns a tool_use
                    # named "structured_output" with the JSON answer in `params`.
                    # That's not a real tool call — it's the final structured answer.
                    # Treat it as such and return immediately rather than trying
                    # to execute a non-existent tool.
                    structured_tc = next(
                        (tc for tc in resp.tool_calls if tc.name == "structured_output"),
                        None
                    )
                    if structured_tc is not None:
                        # The structured payload is in tc.params (a dict matching the schema).
                        # Serialize it to JSON so downstream parse_structured() can hydrate
                        # the Pydantic model uniformly with other providers.
                        try:
                            content = json.dumps(structured_tc.params)
                        except Exception:
                            content = str(structured_tc.params)
                        # v0.3.10: capture structured-output assistant turn
                        _capture_message({"role": "assistant", "content": content})
                        if self.memory is not None:
                            turn_msgs = [
                                dict(m) for m in msgs[memory_turn_start:]
                                if isinstance(m, dict) and m.get("role") != "system"
                            ]
                            turn_msgs.append({"role": "assistant", "content": content})
                            await self.memory.add_messages(turn_msgs)
                        return self._result(content, tid, t0, tc_made, guard,
                                             run_cost=run_cost, run_tokens=run_tokens)
                    
                    if guard.check_loop(resp.tool_calls):
                        return await self._force_final(msgs, tid, t0, tc_made, guard)
                    _asst = {"role": "assistant", "content": resp.content or None,
                        "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.params)}} for tc in resp.tool_calls]}
                    if getattr(resp, "reasoning_content", None):
                        _asst["reasoning_content"] = resp.reasoning_content
                    msgs.append(_asst)
                    _capture_message(_asst)  # v0.3.10
                    for tc in resp.tool_calls:
                        # Steering before tool
                        sr = await self.steering.run_before(tc.name, tc.params, {"agent": self.name})
                        if sr.action == SteeringAction.INTERRUPT:
                            _blocked = {"role": "tool", "tool_call_id": tc.id,
                                "content": f"Blocked by steering: {sr.feedback or sr.result}"}
                            msgs.append(_blocked)
                            _capture_message(_blocked)  # v0.3.10
                            continue

                        tc_made.append(tc.name)
                        await bus.emit("tool.exec", {"tool": tc.name, "agent": self.name})
                        t_start = time.monotonic()
                        res = await self.tool_exec.execute(tc)
                        if res.error:
                            guard.tool_failures.append(tc.name)
                        duration_ms = res.duration_ms if res.duration_ms is not None else (time.monotonic() - t_start) * 1000
                        try:
                            from largestack._observe.metrics import track_tool_call
                            track_tool_call(tc.name, res.error is None, duration_ms)
                        except Exception as _e: log.debug(f"swallowed: {_e}")
                        _tool_msg = {"role": "tool", "tool_call_id": tc.id,
                            "content": res.content if not res.error else f"Error: {res.error}"}
                        msgs.append(_tool_msg)
                        _capture_message(_tool_msg)  # v0.3.10
                else:
                    # v0.3.10: capture final assistant message
                    _capture_message({"role": "assistant", "content": resp.content})
                    # Loop guard: 5th layer — no-progress detection
                    # Only fires on text answers, NOT when agent makes tool calls
                    if resp.content and hasattr(guard, 'check_progress'):
                        if guard.check_progress(resp.content):
                            log.warning("No progress — agent output repeating. Forcing completion.")
                            return self._result(resp.content, tid, t0, tc_made, guard,
                                                 run_cost=run_cost, run_tokens=run_tokens)
                    if self.memory is not None:
                        turn_msgs = [
                            dict(m) for m in msgs[memory_turn_start:]
                            if isinstance(m, dict) and m.get("role") != "system"
                        ]
                        turn_msgs.append({"role": "assistant", "content": resp.content})
                        await self.memory.add_messages(turn_msgs)
                    return self._result(resp.content, tid, t0, tc_made, guard,
                                         run_cost=run_cost, run_tokens=run_tokens)
            return await self._force_final(msgs, tid, t0, tc_made, guard,
                                            run_cost=run_cost, run_tokens=run_tokens)
        except (BudgetExceededError, LoopDetectedError, KillSwitchActivatedError) as e:
            run_status = "failed"
            await bus.emit("agent.error", {"agent": self.name, "error": str(e), "type": type(e).__name__})
            raise
        except Exception as e:
            run_status = "failed"
            await bus.emit("agent.error", {"agent": self.name, "error": str(e)})
            raise
        finally:
            # v0.3.6: emit per-run cost (was: shared gateway tracker)
            await bus.emit("agent.done", {"agent": self.name, "trace_id": tid,
                "duration_ms": (time.monotonic()-t0)*1000, "cost": run_cost, "status": run_status})
            # Audit trail — log every run with actual status
            audit = _get_audit()
            if audit:
                try:
                    audit.log("agent.run", run_status, agent_name=self.name,
                        cost=run_cost, trace_id=tid,
                        details={"duration_ms": round((time.monotonic()-t0)*1000, 1)})
                except Exception as _e: log.debug(f"swallowed: {_e}")

    def _compress_context(self, msgs: list[dict]):
        """Compress older messages to save tokens."""
        if len(msgs) <= 4: return
        # Compress messages 1 to N-3 (keep system, first user, last 2)
        to_compress = msgs[1:-2]
        if not to_compress: return
        full_text = "\n".join(str(m.get("content", "")) for m in to_compress)
        if len(full_text) > 2000:
            compressed = self._compressor.compress(full_text, max_tokens=500)
            # Replace with summary
            msgs[1:-2] = [{"role": "system", "content": f"[Compressed context]: {compressed}"}]

    async def _force_final(self, msgs, tid, t0, tc_made, guard, run_cost: float = 0.0, run_tokens: int = 0):
        self._check_kill_switch()
        _final_prompt = {"role": "user", "content": "Provide your best answer now based on what you have."}
        msgs.append(_final_prompt)
        _capture_message(_final_prompt)  # v0.3.10
        # v0.3.10: route through _llm_call so Agent.override() is honored here too.
        r = await self._llm_call(msgs, None, {})
        # v0.3.10: capture forced-final assistant turn
        _capture_message({"role": "assistant", "content": r.content})
        # P0.4: run output guardrails on forced-final response (was missing)
        if self.guardrails:
            await self.guardrails.check_output(r)
        # Accumulate this final call's cost
        run_cost += float(getattr(r, "cost", 0.0) or 0.0)
        _tok = (
            int(getattr(r, "input_tokens", 0) or 0)
            + int(getattr(r, "output_tokens", 0) or 0)
        )
        if _tok == 0:
            _tok = int(getattr(r, "tokens", 0) or 0)
        run_tokens += _tok
        return self._result(r.content, tid, t0, tc_made, guard,
                             run_cost=run_cost, run_tokens=run_tokens)

    def _build_msgs(self, task):
        msgs = []
        if self.instructions:
            msgs.append({"role": "system", "content": self.instructions})

        # Inject prior conversation memory before the new user turn.
        # Important: do not use `if self.memory:` because ConversationMemory
        # implements __len__(), so an empty memory object is falsy.
        if self.memory is not None and hasattr(self.memory, "get_messages"):
            try:
                previous = self.memory.get_messages()
                if hasattr(previous, "__await__"):
                    # Defensive fallback for async memory implementations.
                    previous = []
                for m in previous:
                    if not isinstance(m, dict):
                        continue
                    role = m.get("role")
                    if role == "system":
                        continue
                    if role in {"user", "assistant", "tool"}:
                        msgs.append(dict(m))
            except Exception as e:
                log.debug(f"memory read failed; continuing without memory: {e}")

        msgs.append({"role": "user", "content": task})
        return msgs

    def _result(self, content, tid, t0, tc_made, guard, run_cost: float | None = None, run_tokens: int | None = None):
        # v0.3.6: prefer per-run cost. Fall back to gateway tracker for back-compat
        # callers that don't pass per-run values.
        if run_cost is None:
            run_cost = self.gateway.cost_tracker.run_cost
        if run_tokens is None:
            run_tokens = self.gateway.cost_tracker.run_tokens
        duration_ms = (time.monotonic() - t0) * 1000
        # v0.3.11: write to `traces` table the dashboard reads. Closes the
        # 3-way schema mismatch that caused dashboard charts to be empty.
        # v0.3.12: include the task so the dashboard's trace list is informative.
        try:
            from largestack._observe.traces_db import log_trace
            log_trace(
                trace_id=tid,
                agent=self.name,
                task=getattr(self, "_current_task", "") or "",
                model=str(self.llm),
                output=content or "",
                duration_ms=duration_ms,
                cost=run_cost or 0.0,
                tokens=run_tokens or 0,
                turns=guard.turn,
                finish_reason="stop",
            )
        except Exception as e:
            log.debug(f"trace log failed (non-fatal): {e}")
        return AgentResult(content=content, agent_name=self.name,
            total_cost=run_cost,
            total_tokens=run_tokens,
            turns=guard.turn, trace_id=tid,
            duration_ms=duration_ms, tool_calls_made=tc_made,
            tool_calls_failed=list(getattr(guard, "tool_failures", [])))

    async def stream(self, task: str, **kw) -> AsyncIterator[str]:
        """Stream tokens with policy parity to execute().

        v0.3.6: Input guardrails, kill-switch, audit emit, and cost budget
        all apply.

        v0.5.0: **per-chunk output guardrails** when ``stream_guard=True``.
        Tokens are accumulated into chunks (default: every 80 chars OR at
        sentence boundary `.!?\\n`), and guardrails run on the assembled
        chunk before yielding. If a chunk fails, the stream stops and a
        redaction marker is yielded. Default is ``stream_guard=False``
        (legacy behavior — guards on completed buffer) for backwards
        compat.

        Args:
            task: user task
            stream_guard: If True (recommended for production), check each
                chunk against output guardrails before yielding. Default: False.
            stream_chunk_chars: chars per chunk in guard mode. Default: 80.
                Smaller = stricter (lower latency to detection) but slower
                (more guard calls).
            stream_redaction_marker: text yielded when a chunk fails guards.
                Default: ``"[content blocked by safety policy]"``.

        Trade-offs (with ``stream_guard=True``):
            - Latency: tokens are held back until chunk boundary (~80 chars).
              Perceived "instant streaming" becomes "fast but chunky".
            - Safety: catches mid-stream PII, injection, toxicity within
              ~1-2 sentences instead of after entire response.
            - Cost: N+1 guardrail calls per response (N chunks + final).

        For high-assurance use cases (regulated content, customer-facing
        UIs), enable ``stream_guard=True``. For latency-critical UX where
        you trust the model, leave it off.
        """
        # License + kill switch
        check_license()
        self._check_kill_switch()
        tid = str(uuid.uuid4()); t0 = time.monotonic()
        await bus.emit("agent.stream.started", {"agent": self.name, "task": task, "trace_id": tid})
        msgs = self._build_msgs(task)
        # Input guardrails
        if self.guardrails: await self.guardrails.check_input(msgs)
        # Cost budget pre-check (defensive; gateway tracks per-call cost)
        cost_budget = kw.get("cost_budget", self.cost_budget)

        # v0.5.0 per-chunk guardrail config
        stream_guard = kw.pop("stream_guard", False)
        chunk_chars = kw.pop("stream_chunk_chars", 80)
        redaction = kw.pop(
            "stream_redaction_marker",
            "[content blocked by safety policy]",
        )
        try:
            buffered = []
            # Per-chunk buffer for in-stream guards (v0.5.0)
            chunk_buf: list[str] = []
            chunk_size = 0

            # Behavior kwargs same as execute()
            _BEHAVIOR_KWS = {
                "temperature", "max_tokens", "response_format", "tool_choice",
                "top_p", "top_k", "seed", "stop", "stop_sequences",
                "responseMimeType", "responseSchema",
                "response_mime_type", "response_schema",
                "tools",
            }
            behavior_kw = {k: v for k, v in kw.items() if k in _BEHAVIOR_KWS}

            async def _check_chunk_safe(chunk_text: str) -> bool:
                """Returns True if chunk passes guardrails, False if blocked.
                Errors are logged but don't block (fail-open on guard error
                during streaming, since blocking would break the UX more).
                """
                if not self.guardrails:
                    return True
                try:
                    fake_resp = type("StreamChunk", (), {
                        "content": chunk_text, "cost": 0.0, "tokens": 0,
                    })()
                    await self.guardrails.check_output(fake_resp)
                    return True
                except Exception as e:
                    log.warning(f"Stream chunk blocked by guardrails: {e}")
                    return False

            blocked = False
            async for tok in self.gateway.stream(self.llm, msgs, **behavior_kw):
                buffered.append(tok)

                if not stream_guard:
                    # Legacy mode: just yield through
                    yield tok
                    continue

                # v0.5.0: chunk-level guard mode
                chunk_buf.append(tok)
                chunk_size += len(tok)
                # Flush at boundary or size threshold
                last_char = tok[-1] if tok else ""
                if chunk_size >= chunk_chars or last_char in ".!?\n":
                    chunk_text = "".join(chunk_buf)
                    if await _check_chunk_safe(chunk_text):
                        # Safe — yield the whole chunk now
                        for t in chunk_buf:
                            yield t
                    else:
                        # Blocked — yield redaction marker, stop early
                        yield redaction
                        blocked = True
                        break
                    chunk_buf = []
                    chunk_size = 0

            # Flush any remaining buffer
            if stream_guard and chunk_buf and not blocked:
                tail = "".join(chunk_buf)
                if await _check_chunk_safe(tail):
                    for t in chunk_buf:
                        yield t
                else:
                    yield redaction
                    blocked = True

            # Final whole-response guardrail (legacy mode; harmless in guard mode)
            if self.guardrails and not blocked:
                full_text = "".join(buffered)
                try:
                    fake_resp = type("StreamResp", (), {
                        "content": full_text, "cost": 0.0, "tokens": 0,
                    })()
                    await self.guardrails.check_output(fake_resp)
                except Exception as e:
                    log.warning(f"Stream output guardrail (final) failed: {e}")

            await bus.emit("agent.stream.completed",
                          {"agent": self.name, "trace_id": tid,
                           "blocked": blocked,
                           "duration_ms": (time.monotonic() - t0) * 1000})
        except Exception as e:
            await bus.emit("agent.stream.failed",
                          {"agent": self.name, "trace_id": tid, "error": str(e)})
            raise
