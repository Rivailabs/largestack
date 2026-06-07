"""Regression tests for v0.3.10 production-fix patch.

Covers the four P0 defects from the v0.3.9 review (D-1..D-4) plus the
two P2 quality fixes (workflow set_start/set_end on DAG, agent.clone
dead key).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# D-1: agent.override(model=test_model) actually exists and works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_override_with_test_model_no_real_call_needed():
    """D-1: TestModel via agent.override() runs without any API key.

    Before v0.3.10: AttributeError — `Agent` had no `override()` method.
    After v0.3.10: returns the canned content.
    """
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="tester", llm="openai/gpt-4o-mini")
    test_model = TestModel(custom_output_text="canned reply")

    with agent.override(model=test_model):
        result = await agent.run("anything you want")

    assert "canned" in result.content.lower()
    assert test_model.calls >= 1


@pytest.mark.asyncio
async def test_agent_override_restores_previous_state():
    """After exiting the override context, the engine reverts to gateway."""
    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="tester", llm="openai/gpt-4o-mini")
    assert getattr(agent._engine, "_test_model", None) is None

    with agent.override(model=TestModel(custom_output_text="x")):
        assert agent._engine._test_model is not None

    assert agent._engine._test_model is None


@pytest.mark.asyncio
async def test_agent_override_requires_model_kwarg():
    """Calling override() with no model raises ValueError, not AttributeError."""
    from largestack import Agent

    agent = Agent(name="tester", llm="openai/gpt-4o-mini")
    with pytest.raises(ValueError, match="requires a model="):
        agent.override()  # no kwarg


@pytest.mark.asyncio
async def test_function_model_via_override_drives_engine():
    """FunctionModel — full control over the response."""
    from largestack import Agent
    from largestack.testing import FunctionModel

    captured_prompts = []

    def my_logic(messages, info):
        captured_prompts.append(messages[-1]["content"])
        return {"content": "echo: " + messages[-1]["content"]}

    fm = FunctionModel(my_logic)
    agent = Agent(name="echo", llm="openai/gpt-4o-mini")
    with agent.override(model=fm):
        result = await agent.run("ping")
    assert "echo: ping" in result.content
    assert captured_prompts and "ping" in captured_prompts[-1]


@pytest.mark.asyncio
async def test_decorator_agent_override_works():
    """D-1 (decorator API path): TypedAgent.override() also works."""
    from largestack.decorators import Agent
    from largestack.testing import TestModel
    from tests.unit._p0310_helpers import _Deps, make_search_tool

    agent = Agent[_Deps, str](
        "openai/gpt-4o-mini",
        deps_type=_Deps,
        instructions="be helpful",
    )
    make_search_tool(agent)

    test_model = TestModel(custom_output_text="ok", call_tools=[])
    with agent.override(model=test_model):
        result = await agent.run("hello", deps=_Deps(user_id="u1"))

    assert result.output == "ok"


# ---------------------------------------------------------------------------
# D-2: block_model_requests / ALLOW_MODEL_REQUESTS gate is enforced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_model_requests_raises_on_real_path():
    """D-2: with block_model_requests(), real gateway calls raise.

    Before v0.3.10: ALLOW_MODEL_REQUESTS was set but never read; this
    test would pass through to a real (or stubbed) provider.
    After v0.3.10: gateway raises ModelRequestsBlockedError.
    """
    # Clear keys to make sure we'd otherwise hit ProviderError paths
    saved = {
        k: os.environ.pop(k, None)
        for k in list(os.environ)
        if k.startswith(
            ("LARGESTACK_OPENAI_API_KEY", "OPENAI_API_KEY", "LARGESTACK_DEEPSEEK_API_KEY")
        )
    }
    try:
        from largestack import Agent
        from largestack.testing import block_model_requests
        from largestack.errors import ModelRequestsBlockedError

        # Force a fresh config so providers aren't cached
        from largestack._core.config import get_config

        get_config(default_llm="openai/gpt-4o-mini")

        agent = Agent(name="blocked", llm="openai/gpt-4o-mini")
        with block_model_requests():
            with pytest.raises(ModelRequestsBlockedError):
                await agent.run("hello")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


@pytest.mark.asyncio
async def test_block_model_requests_does_not_block_overridden_model():
    """D-2 + D-1 interaction: TestModel overrides bypass the gateway, so
    block_model_requests() does NOT prevent them. This is the intended
    pattern for tests: block real calls, allow TestModel."""
    from largestack import Agent
    from largestack.testing import TestModel, block_model_requests

    agent = Agent(name="x", llm="openai/gpt-4o-mini")
    with block_model_requests(), agent.override(model=TestModel(custom_output_text="ok")):
        result = await agent.run("anything")
    assert result.content == "ok"


def test_disable_enable_model_requests_toggle_global():
    """The simple toggle API works — flag is restored after disable/enable."""
    from largestack import testing as t

    assert t.ALLOW_MODEL_REQUESTS is True
    t.disable_model_requests()
    assert t.ALLOW_MODEL_REQUESTS is False
    t.enable_model_requests()
    assert t.ALLOW_MODEL_REQUESTS is True


def test_block_model_requests_restores_prev_value():
    """Context manager restores the prior flag value, even if it was False."""
    from largestack import testing as t

    t.disable_model_requests()
    assert t.ALLOW_MODEL_REQUESTS is False
    with t.block_model_requests():
        assert t.ALLOW_MODEL_REQUESTS is False
    # On exit, restore prior — which was False
    assert t.ALLOW_MODEL_REQUESTS is False
    t.enable_model_requests()  # restore for other tests


# ---------------------------------------------------------------------------
# D-3: capture_run_messages actually captures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_run_messages_captures_user_and_assistant():
    """D-3: capture_run_messages() must record both the user prompt and
    the assistant response.

    Before v0.3.10: returned an empty CapturedMessages.
    After v0.3.10: at least one user message and one assistant message.
    """
    from largestack import Agent
    from largestack.testing import TestModel, capture_run_messages

    agent = Agent(name="cap", llm="openai/gpt-4o-mini", instructions="You are helpful.")
    with capture_run_messages() as captured:
        with agent.override(model=TestModel(custom_output_text="hi back")):
            await agent.run("hello agent")

    assert len(captured) >= 2, f"expected >=2 messages, got {list(captured)}"
    assert any(
        m.get("role") == "user" and "hello agent" in str(m.get("content", ""))
        for m in captured.messages
    )
    assert any(
        m.get("role") == "assistant" and "hi back" in str(m.get("content", ""))
        for m in captured.messages
    )


@pytest.mark.asyncio
async def test_capture_run_messages_captures_tool_call_and_result():
    """capture should include both the assistant's tool_call and the tool result."""
    from largestack import Agent, tool
    from largestack.testing import TestModel, capture_run_messages

    @tool
    async def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    test_model = TestModel(
        custom_output_text="done",
        custom_tool_args={"add": {"a": 2, "b": 3}},
    )
    agent = Agent(name="adder", llm="openai/gpt-4o-mini", tools=[add])
    with capture_run_messages() as captured:
        with agent.override(model=test_model):
            await agent.run("compute 2+3")

    # We should see: system?, user, assistant (with tool_calls), tool result, assistant final
    roles = [m.get("role") for m in captured.messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "tool" in roles, f"expected a tool message; got roles={roles}"


@pytest.mark.asyncio
async def test_capture_run_messages_isolated_between_runs():
    """Two parallel captures don't leak into each other."""
    from largestack import Agent
    from largestack.testing import TestModel, capture_run_messages

    a1 = Agent(name="a1", llm="openai/gpt-4o-mini")
    a2 = Agent(name="a2", llm="openai/gpt-4o-mini")

    async def task(agent, text, expected):
        with capture_run_messages() as cap:
            with agent.override(model=TestModel(custom_output_text=expected)):
                await agent.run(text)
        return cap

    cap1, cap2 = await asyncio.gather(
        task(a1, "alpha prompt", "alpha out"),
        task(a2, "beta prompt", "beta out"),
    )
    # Each capture only contains its own prompt
    cap1_content = " ".join(str(m.get("content", "")) for m in cap1.messages)
    cap2_content = " ".join(str(m.get("content", "")) for m in cap2.messages)
    assert "alpha" in cap1_content and "beta" not in cap1_content
    assert "beta" in cap2_content and "alpha" not in cap2_content


def test_capture_var_default_is_none_no_overhead():
    """When no capture context is active, _capture_message is a cheap no-op."""
    from largestack.testing import _capture_var, _capture_message

    assert _capture_var.get() is None
    # Should not raise
    _capture_message({"role": "user", "content": "x"})
    _capture_message(None)
    _capture_message({"role": "assistant", "content": "y"})


# ---------------------------------------------------------------------------
# D-4: dev server hot-reload — real watcher when watchfiles available;
#      honest "disabled" message when not.
# ---------------------------------------------------------------------------


def test_dev_server_health_reports_hot_reload_status(tmp_path):
    """/api/health honestly reports whether hot-reload is on."""
    from fastapi.testclient import TestClient
    from largestack._cli.dev_server import create_dev_app, watchfiles_available

    app = create_dev_app(watch_path=str(tmp_path))
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "hot_reload" in body
    assert "watchfiles_installed" in body
    # Whatever the env, the two fields agree about availability
    assert body["watchfiles_installed"] is watchfiles_available()


def test_dev_server_hot_reload_disabled_when_explicitly_off(tmp_path):
    """Forcing enable_hot_reload=False disables the watcher and the SPA
    receives an honest 'disabled' first-event."""
    from fastapi.testclient import TestClient
    from largestack._cli.dev_server import create_dev_app

    app = create_dev_app(watch_path=str(tmp_path), enable_hot_reload=False)
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["hot_reload"] is False


def test_dev_server_hot_reload_request_without_watchfiles_raises(monkeypatch):
    """If the user explicitly asks for hot-reload but watchfiles isn't
    installed, we raise — not silently lie.

    Uses monkeypatch on the dev_server module's `watchfiles_available`
    function rather than reloading the module — reloading pollutes the
    import graph for sibling tests.
    """
    from largestack._cli import dev_server as ds

    monkeypatch.setattr(ds, "watchfiles_available", lambda: False)
    with pytest.raises(RuntimeError, match="watchfiles"):
        ds.create_dev_app(enable_hot_reload=True)


def test_dev_server_root_serves_playground_html(tmp_path):
    """Playground HTML is served at / and /playground."""
    from fastapi.testclient import TestClient
    from largestack._cli.dev_server import create_dev_app

    client = TestClient(create_dev_app(watch_path=str(tmp_path), enable_hot_reload=False))
    for path in ("/", "/playground"):
        r = client.get(path)
        assert r.status_code == 200
        assert "LARGESTACK Playground" in r.text


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("watchfiles"),
    reason="watchfiles not installed; hot-reload integration skipped",
)
@pytest.mark.asyncio
async def test_dev_server_hot_reload_pushes_event_on_file_change(tmp_path):
    """End-to-end: editing a file under watch_path causes the watcher to
    push a `reload` event into every subscriber's queue."""
    from largestack._cli.dev_server import create_dev_app

    # Build app pointing at a fresh temp dir
    app = create_dev_app(watch_path=str(tmp_path), enable_hot_reload=True)

    # Manually invoke lifespan-startup to launch the watcher
    # (TestClient handles this for HTTP requests, but we want the bg task).
    async with app.router.lifespan_context(app):
        # Subscribe like the SSE endpoint does
        q: asyncio.Queue = asyncio.Queue()
        app.state.refresh_subscribers.append(q)

        # Give watcher time to start
        await asyncio.sleep(0.4)

        # Trigger a real file change
        f = tmp_path / "agent.py"
        f.write_text("# v1\n")
        await asyncio.sleep(0.5)
        f.write_text("# v2\n")

        # Wait for an event with timeout
        try:
            msg = await asyncio.wait_for(q.get(), timeout=5.0)
            assert msg == "reload"
        except asyncio.TimeoutError:
            pytest.fail("watcher did not push a reload event")
        finally:
            if q in app.state.refresh_subscribers:
                app.state.refresh_subscribers.remove(q)


# ---------------------------------------------------------------------------
# Workflow set_start / set_end — explicit error on DAG
# ---------------------------------------------------------------------------


def test_workflow_set_start_raises_on_dag():
    """set_start on a DAG workflow now raises ValueError instead of no-op."""
    from largestack import Workflow

    wf = Workflow("p", mode="dag")
    with pytest.raises(ValueError, match="state_machine"):
        wf.set_start("anything")


def test_workflow_set_end_raises_on_dag():
    from largestack import Workflow

    wf = Workflow("p", mode="dag")
    with pytest.raises(ValueError, match="state_machine"):
        wf.set_end("a", "b")


def test_workflow_set_start_works_on_state_machine():
    """Still works on state-machine workflows."""
    from largestack import Workflow

    wf = Workflow("sm", mode="state_machine")
    wf.set_start("init")  # should not raise
    wf.set_end("done")


# ---------------------------------------------------------------------------
# Agent.clone — dead response_model key removed
# ---------------------------------------------------------------------------


def test_agent_clone_no_dead_response_model_key():
    """Confirm clone() no longer references the missing _response_model attr."""
    from largestack import Agent

    a = Agent(name="orig", llm="openai/gpt-4o-mini", instructions="hi")
    b = a.clone(name="copy")
    assert b.name == "copy"
    assert b.llm == "openai/gpt-4o-mini"
    # No AttributeError, no leaked None key
    assert not hasattr(b, "_response_model") or getattr(b, "_response_model", None) is None


# ---------------------------------------------------------------------------
# Release artifacts — no DBs in source tree
# ---------------------------------------------------------------------------


def test_no_committed_db_artifacts_in_source_tree():
    """tmp/test_priority.db and similar artifacts must not be in the repo."""
    repo = Path(__file__).resolve().parent.parent.parent
    bad = []
    for p in repo.rglob("*.db"):
        # Allow .db files inside .largestack/ or under tests/ if intentionally fixture
        if any(part.startswith(".") for part in p.relative_to(repo).parts):
            continue
        if "tests/fixtures" in str(p):
            continue
        if ".venv" in str(p) or "site-packages" in str(p):
            continue
        bad.append(str(p.relative_to(repo)))
    assert not bad, f"committed DB artifacts found: {bad}"


def test_gitignore_covers_cache_dirs():
    """Belt-and-suspenders: confirm .gitignore lists the dirs that leaked
    into the v0.3.9 release zip."""
    repo = Path(__file__).resolve().parent.parent.parent
    gi = (repo / ".gitignore").read_text()
    for needed in ["tmp/", ".cache/", ".npm/", ".npm-global/", "*.db"]:
        assert needed in gi, f".gitignore missing entry: {needed}"


# ---------------------------------------------------------------------------
# ModelRequestsBlockedError exposed at top level
# ---------------------------------------------------------------------------


def test_model_requests_blocked_error_exported():
    import largestack

    assert hasattr(largestack, "ModelRequestsBlockedError")
    from largestack.errors import ModelRequestsBlockedError, LargestackError

    assert issubclass(ModelRequestsBlockedError, LargestackError)
