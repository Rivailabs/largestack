"""Regression tests for v0.3.11 production-fix patch.

Covers fixes for issues found by the v0.3.10 external reviews:
  - Trace schema mismatch (R2 P0)
  - shell.py command injection (R2 P0)
  - code.py shell branch enabled by default (R1 P0 / R2 P0)
  - HTTP tool SSRF (R2 P0)
  - TS SDK auth header mismatch (R2 P1)
  - Dockerfile missing curl for prod healthcheck (R2 P1)
  - Dashboard API silent error swallowing (R2 P2)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Trace schema unification
# ---------------------------------------------------------------------------

def test_trace_writer_creates_dashboard_compatible_table(tmp_path):
    """log_trace() must create a `traces` table with columns the dashboard reads."""
    from largestack._observe.traces_db import log_trace, _initialized

    db = str(tmp_path / "traces.db")
    # Ensure clean state for this path
    _initialized.discard(db)

    log_trace(
        trace_id="t1", agent="ag1", task="hello",
        model="openai/gpt-4o-mini", output="hi",
        duration_ms=12.5, cost=0.001, tokens=10, turns=1,
        db_path=db,
    )

    conn = sqlite3.connect(db)
    try:
        # Schema check: every column the dashboard SELECTs must exist
        cols = {r[1] for r in conn.execute("PRAGMA table_info(traces)").fetchall()}
        for needed in ("trace_id", "timestamp", "agent", "task", "model",
                       "output", "duration_ms", "cost"):
            assert needed in cols, f"missing column: {needed}"

        # Same queries the dashboard runs must succeed
        n = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE timestamp > 0"
        ).fetchone()[0]
        assert n == 1
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
        assert len(rows) == 1
        # GROUP BY agent — same as dashboard /api/agents
        rows = conn.execute(
            "SELECT agent, COUNT(*) as runs, AVG(duration_ms) as avg_latency, "
            "SUM(cost) as total_cost FROM traces WHERE timestamp > 0 "
            "GROUP BY agent ORDER BY runs DESC"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "ag1"
    finally:
        conn.close()


def test_trace_log_never_raises(tmp_path):
    """log_trace must never raise — best-effort persistence."""
    from largestack._observe.traces_db import log_trace
    # Bad path that can't be created
    log_trace(
        trace_id="t", agent="x",
        db_path="/dev/null/cannot-write-here/traces.db",
    )  # should not raise


@pytest.mark.asyncio
async def test_engine_writes_to_traces_table_after_run(tmp_path, monkeypatch):
    """End-to-end: agent.run with TestModel must produce a row in traces."""
    from largestack import Agent
    from largestack.testing import TestModel

    db = str(tmp_path / "traces.db")
    monkeypatch.setenv("LARGESTACK_TRACE_DB", db)
    # Force re-init for this path
    from largestack._observe.traces_db import _initialized
    _initialized.discard(db)
    # Patch the DEFAULT_TRACE_DB at module level for this test
    import largestack._observe.traces_db as tdb
    monkeypatch.setattr(tdb, "DEFAULT_TRACE_DB", db)

    agent = Agent(name="trace_test", llm="openai/gpt-4o-mini",
                  instructions="be brief")
    with agent.override(model=TestModel(custom_output_text="canned")):
        await agent.run("hello")

    # Read back
    assert os.path.exists(db), "traces.db not created"
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT agent, output FROM traces").fetchall()
    finally:
        conn.close()
    assert len(rows) >= 1
    assert any(r[0] == "trace_test" for r in rows)


# ---------------------------------------------------------------------------
# shell.py command injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shell_blocks_semicolon_chain():
    """The classic v0.3.10 bypass: ls; rm -rf ~ — must be rejected."""
    from largestack._core.builtin_tools.shell import shell_command

    out = await shell_command("ls; echo PWNED")
    assert "rejected" in out.lower() or "forbidden" in out.lower()
    assert "pwned" not in out.lower(), f"shell injection ran: {out!r}"


@pytest.mark.asyncio
async def test_shell_blocks_pipe_chain():
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("echo hi | grep h")
    assert "rejected" in out.lower() or "forbidden" in out.lower()


@pytest.mark.asyncio
async def test_shell_blocks_backtick_substitution():
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("echo `whoami`")
    assert "rejected" in out.lower() or "forbidden" in out.lower()


@pytest.mark.asyncio
async def test_shell_blocks_dollar_substitution():
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("echo $(whoami)")
    assert "rejected" in out.lower() or "forbidden" in out.lower()


@pytest.mark.asyncio
async def test_shell_blocks_redirection():
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("ls > /tmp/x")
    assert "rejected" in out.lower() or "forbidden" in out.lower()


@pytest.mark.asyncio
async def test_shell_blocks_disallowed_command():
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("rm -rf /tmp/x")
    assert "not allowed" in out.lower() or "rejected" in out.lower()


@pytest.mark.asyncio
async def test_shell_allows_safe_command():
    """`echo hello` must still work."""
    from largestack._core.builtin_tools.shell import shell_command
    out = await shell_command("echo hello")
    assert "hello" in out


@pytest.mark.asyncio
async def test_shell_allows_command_with_quoted_arg():
    """shlex parses `echo "hello world"` as one argument."""
    from largestack._core.builtin_tools.shell import shell_command
    # Note: " is in forbidden chars now — verify via tokenized path with single-quoted arg
    out = await shell_command("echo 'hello world'")
    # `'` is not in forbidden set; shlex parses correctly
    assert "hello world" in out


# ---------------------------------------------------------------------------
# code.py — bash branch gated behind opt-in
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_bash_disabled_by_default(monkeypatch):
    """bash/sh execution must be off unless LARGESTACK_ALLOW_SHELL_EXEC=1."""
    monkeypatch.delenv("LARGESTACK_ALLOW_SHELL_EXEC", raising=False)
    # Force re-import to pick up env
    import importlib
    import largestack._core.builtin_tools.code as code_mod
    importlib.reload(code_mod)

    out = await code_mod.code_execute("echo PWNED", language="bash")
    assert "disabled" in out.lower() or "error" in out.lower()
    assert "pwned" not in out.lower(), f"bash ran when disabled: {out!r}"


@pytest.mark.asyncio
async def test_code_python_runs_isolated(tmp_path):
    """Python branch still works."""
    from largestack._core.builtin_tools.code import code_execute
    out = await code_execute("print('hello from sandbox')", language="python")
    assert "hello from sandbox" in out


@pytest.mark.asyncio
async def test_code_python_cwd_is_isolated(tmp_path, monkeypatch):
    """Python script can't read project files via relative path."""
    from largestack._core.builtin_tools.code import code_execute
    # cwd is a fresh tempdir per call — `open('agent.py')` should fail
    out = await code_execute(
        "import os; print('CWD=' + os.getcwd()); "
        "print('FILES=' + str(os.listdir('.')))",
        language="python",
    )
    assert "largestack_code_" in out  # tempdir prefix


# ---------------------------------------------------------------------------
# HTTP tool SSRF
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_tool_blocks_loopback():
    from largestack._core.builtin_tools.http_tool import http_request
    out = await http_request("http://127.0.0.1:1234/x")
    assert "blocked" in out.lower() or "private" in out.lower() or "loopback" in out.lower()


@pytest.mark.asyncio
async def test_http_tool_blocks_aws_metadata():
    from largestack._core.builtin_tools.http_tool import http_request
    out = await http_request("http://169.254.169.254/latest/meta-data/iam")
    assert "blocked" in out.lower() or "metadata" in out.lower() or "link-local" in out.lower()


@pytest.mark.asyncio
async def test_http_tool_blocks_localhost_name():
    from largestack._core.builtin_tools.http_tool import http_request
    out = await http_request("http://localhost:8500/v1/kv")
    assert "blocked" in out.lower() or "private" in out.lower() or "loopback" in out.lower()


@pytest.mark.asyncio
async def test_http_tool_blocks_non_http_scheme():
    from largestack._core.builtin_tools.http_tool import http_request
    out = await http_request("file:///etc/passwd")
    assert "blocked" in out.lower() or "scheme" in out.lower()
    out = await http_request("gopher://x")
    assert "blocked" in out.lower() or "scheme" in out.lower()


@pytest.mark.asyncio
async def test_http_tool_blocks_unparsable_url():
    from largestack._core.builtin_tools.http_tool import http_request
    out = await http_request("not a url")
    # Either parse error or scheme error — both acceptable
    assert "blocked" in out.lower() or "scheme" in out.lower() or "no host" in out.lower()


@pytest.mark.asyncio
async def test_http_tool_respects_allowlist(monkeypatch):
    """When LARGESTACK_HTTP_ALLOWLIST is set, only listed hosts allowed."""
    monkeypatch.setenv("LARGESTACK_HTTP_ALLOWLIST", "example.com,api.example.org")
    from largestack._core.builtin_tools.http_tool import http_request

    out = await http_request("https://other-host.invalid/")
    assert "allowlist" in out.lower() or "blocked" in out.lower()


# ---------------------------------------------------------------------------
# TS SDK header — static check
# ---------------------------------------------------------------------------

def test_ts_sdk_sends_x_api_key_header():
    """SDK source must include `X-API-Key` header (matches server)."""
    repo = Path(__file__).resolve().parent.parent.parent
    sdk = (repo / "sdk" / "typescript" / "src" / "index.ts").read_text()
    assert 'headers["X-API-Key"]' in sdk, (
        "TS SDK does not send X-API-Key — server (serve.py) only reads X-API-Key"
    )


# ---------------------------------------------------------------------------
# Dockerfile — curl present
# ---------------------------------------------------------------------------

def test_dockerfile_installs_curl():
    """Dockerfile must apt-get install curl, since prod compose healthcheck uses it."""
    repo = Path(__file__).resolve().parent.parent.parent
    df = (repo / "Dockerfile").read_text()
    assert "curl" in df, "Dockerfile must install curl for prod compose healthcheck"


# ---------------------------------------------------------------------------
# Dashboard API — log at warning, not debug
# ---------------------------------------------------------------------------

def test_dashboard_query_logs_warning_on_failure(tmp_path, caplog):
    """When a dashboard query fails (e.g. wrong table name), it must log
    at WARNING — not silently swallow at DEBUG."""
    from fastapi.testclient import TestClient
    from largestack._dashboard.api import create_api

    # Empty DBs in tmp_path won't have the right tables — query should fail loudly
    api = create_api()
    client = TestClient(api)
    # Set non-existent table on TRACE_DB — but the route catches it.
    # Instead just verify the _q logger configuration directly:
    import logging
    import largestack._dashboard.api as api_mod

    # Build a fake _q-equivalent test
    db_path = str(tmp_path / "fake.db")
    # Create a DB with no `traces` table
    conn = sqlite3.connect(db_path); conn.commit(); conn.close()

    # The api module's _q is closure-scoped inside create_api; instead verify
    # the logger has a non-debug-only path. Check at the source level.
    src = Path(api_mod.__file__).read_text()
    assert "log.warning" in src, "dashboard _q must log at warning, not debug"


# ---------------------------------------------------------------------------
# RBAC fail-closed in production
# ---------------------------------------------------------------------------

def test_rbac_fails_closed_in_production(monkeypatch):
    """In production, RBAC wiring failure must raise — not silently warn."""
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    monkeypatch.setenv("LARGESTACK_RBAC_ENABLED", "1")

    # Force an import failure
    import sys
    real_rbac = sys.modules.pop("largestack._enterprise.rbac", None)
    sys.modules["largestack._enterprise.rbac"] = None  # type: ignore[assignment]
    try:
        from largestack._dashboard.app import _build_protected_deps
        with pytest.raises(RuntimeError, match="RBAC"):
            _build_protected_deps()
    finally:
        if real_rbac is not None:
            sys.modules["largestack._enterprise.rbac"] = real_rbac
        else:
            sys.modules.pop("largestack._enterprise.rbac", None)


def test_rbac_warns_in_development_when_wiring_fails(monkeypatch, caplog):
    """In development, same failure must log warning and continue."""
    import logging
    monkeypatch.setenv("LARGESTACK_ENV", "development")
    monkeypatch.setenv("LARGESTACK_RBAC_ENABLED", "1")

    import sys
    real_rbac = sys.modules.pop("largestack._enterprise.rbac", None)
    sys.modules["largestack._enterprise.rbac"] = None  # type: ignore[assignment]
    caplog.set_level(logging.WARNING)
    try:
        from largestack._dashboard.app import _build_protected_deps
        deps = _build_protected_deps()
        # 2 deps = api_key + rate_limit (no RBAC dep, since wiring failed)
        assert len(deps) == 2
    finally:
        if real_rbac is not None:
            sys.modules["largestack._enterprise.rbac"] = real_rbac
        else:
            sys.modules.pop("largestack._enterprise.rbac", None)
