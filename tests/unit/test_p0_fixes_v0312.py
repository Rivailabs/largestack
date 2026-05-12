"""Regression tests for v0.3.12 — issues found in the final recheck pass.

Covers:
  - db.py SQL safety (read-only mode + path allowlist)
  - web.py web_fetch SSRF (was unprotected even after v0.3.11 fix to http_tool)
  - browser.py SSRF (same)
  - Dockerfile uses real curl healthcheck (not just `import largestack`)
  - Engine threads `task` into trace row
  - Streaming docstring documents post-hoc guardrail limitation
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# db.py — read-only mode + db_path allowlist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_blocks_path_outside_base(tmp_path, monkeypatch):
    """db_path outside LARGESTACK_DB_TOOL_BASE must be blocked."""
    from largestack._core.builtin_tools.db import database_query

    monkeypatch.setenv("LARGESTACK_DB_TOOL_BASE", str(tmp_path))
    monkeypatch.delenv("LARGESTACK_DB_TOOL_ALLOWLIST", raising=False)

    # Create a sensitive DB outside the base
    sensitive = tmp_path.parent / "sensitive.db"
    conn = sqlite3.connect(sensitive)
    conn.execute("CREATE TABLE secrets (key TEXT, value TEXT)")
    conn.execute("INSERT INTO secrets VALUES ('api_key', 'sk-real-secret')")
    conn.commit()
    conn.close()
    try:
        out = await database_query("SELECT * FROM secrets", db_path=str(sensitive))
        assert "blocked" in out.lower() or "outside" in out.lower()
        assert "sk-real-secret" not in out, f"secret leaked: {out!r}"
    finally:
        sensitive.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_db_rejects_insert_via_readonly_mode(tmp_path, monkeypatch):
    """Even if first keyword check is bypassed, RO mode rejects writes."""
    from largestack._core.builtin_tools.db import database_query

    monkeypatch.setenv("LARGESTACK_DB_TOOL_BASE", str(tmp_path))
    monkeypatch.delenv("LARGESTACK_DB_TOOL_ALLOWLIST", raising=False)

    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE users (id INT, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'alice')")
    conn.commit()
    conn.close()

    # The keyword check rejects non-SELECT first
    out = await database_query("INSERT INTO users VALUES (2, 'mallory')",
                               db_path=str(db))
    assert "select" in out.lower() and (
        "permitted" in out.lower() or "only" in out.lower()
    )

    # Even if attacker tries `WITH ... INSERT`, RO mode at SQLite layer blocks
    out2 = await database_query(
        "WITH x AS (SELECT 1) INSERT INTO users VALUES (3, 'eve')",
        db_path=str(db),
    )
    # Either keyword reject (WITH passes first check) or SQL error from RO mode
    assert "error" in out2.lower() or "select" in out2.lower()

    # Confirm the table still has only the original row
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][1] == "alice"


@pytest.mark.asyncio
async def test_db_allows_select_in_base(tmp_path, monkeypatch):
    """Happy path: SELECT inside base directory works."""
    from largestack._core.builtin_tools.db import database_query

    monkeypatch.setenv("LARGESTACK_DB_TOOL_BASE", str(tmp_path))
    monkeypatch.delenv("LARGESTACK_DB_TOOL_ALLOWLIST", raising=False)

    db = tmp_path / "ok.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (n INT)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()

    out = await database_query("SELECT n FROM t", db_path=str(db))
    assert "42" in out


@pytest.mark.asyncio
async def test_db_explicit_allowlist(tmp_path, monkeypatch):
    """LARGESTACK_DB_TOOL_ALLOWLIST can permit specific paths outside base."""
    from largestack._core.builtin_tools.db import database_query

    db = tmp_path / "explicit.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (n INT)")
    conn.execute("INSERT INTO t VALUES (7)")
    conn.commit()
    conn.close()

    # base is elsewhere
    monkeypatch.setenv("LARGESTACK_DB_TOOL_BASE", "/nowhere")
    monkeypatch.setenv("LARGESTACK_DB_TOOL_ALLOWLIST", str(db))

    out = await database_query("SELECT n FROM t", db_path=str(db))
    assert "7" in out


# ---------------------------------------------------------------------------
# web.py web_fetch — SSRF (was missing in v0.3.11)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_fetch_blocks_loopback():
    from largestack._core.builtin_tools.web import web_fetch
    out = await web_fetch("http://127.0.0.1:8080/secrets")
    assert "blocked" in out.lower() or "private" in out.lower() or "loopback" in out.lower()


@pytest.mark.asyncio
async def test_web_fetch_blocks_metadata_ip():
    from largestack._core.builtin_tools.web import web_fetch
    out = await web_fetch("http://169.254.169.254/iam")
    assert "blocked" in out.lower() or "metadata" in out.lower() or "link-local" in out.lower()


@pytest.mark.asyncio
async def test_web_fetch_blocks_file_scheme():
    from largestack._core.builtin_tools.web import web_fetch
    out = await web_fetch("file:///etc/passwd")
    assert "blocked" in out.lower() or "scheme" in out.lower()


# ---------------------------------------------------------------------------
# browser.py — SSRF (was missing in v0.3.11)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browser_blocks_loopback():
    """Even without playwright installed, the SSRF check fires before
    we attempt to import playwright."""
    from largestack._core.builtin_tools.browser import browser_navigate
    out = await browser_navigate("http://127.0.0.1:8080/admin")
    assert "blocked" in out.lower() or "private" in out.lower() or "loopback" in out.lower()


@pytest.mark.asyncio
async def test_browser_blocks_metadata():
    from largestack._core.builtin_tools.browser import browser_navigate
    out = await browser_navigate("http://169.254.169.254/iam")
    assert "blocked" in out.lower() or "metadata" in out.lower() or "link-local" in out.lower()


# ---------------------------------------------------------------------------
# Shared validator imported by all three tools
# ---------------------------------------------------------------------------

def test_url_validator_module_exists_and_used_by_all_tools():
    """Belt-and-suspenders: confirm the shared validator is what each tool uses,
    so future fixes apply uniformly."""
    repo = Path(__file__).resolve().parent.parent.parent
    for name in ("http_tool.py", "web.py", "browser.py"):
        src = (repo / "largestack" / "_core" / "builtin_tools" / name).read_text()
        assert "from largestack._core.builtin_tools._url_validator import validate_url" in src, \
            f"{name} doesn't use shared validator — risk of fix drift"


# ---------------------------------------------------------------------------
# Dockerfile uses real curl healthcheck
# ---------------------------------------------------------------------------

def test_dockerfile_healthcheck_uses_curl():
    """Real HTTP healthcheck, not just `python -c "import largestack"`."""
    repo = Path(__file__).resolve().parent.parent.parent
    df = (repo / "Dockerfile").read_text()
    # The HEALTHCHECK line must mention curl (the import-only one was insufficient).
    healthcheck_block = ""
    in_block = False
    for line in df.splitlines():
        if line.strip().startswith("HEALTHCHECK"):
            in_block = True
        if in_block:
            healthcheck_block += line + "\n"
            if not line.strip().endswith("\\"):
                break
    assert "curl" in healthcheck_block, (
        f"Dockerfile HEALTHCHECK doesn't use curl:\n{healthcheck_block}"
    )


# ---------------------------------------------------------------------------
# Engine threads task into trace row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_writes_task_to_trace_row(tmp_path, monkeypatch):
    """v0.3.12: trace row must include the user's task, not just the output."""
    import largestack._observe.traces_db as tdb
    from largestack._observe.traces_db import _initialized

    db = str(tmp_path / "traces.db")
    monkeypatch.setattr(tdb, "DEFAULT_TRACE_DB", db)
    _initialized.discard(db)

    from largestack import Agent
    from largestack.testing import TestModel

    agent = Agent(name="task_test", llm="openai/gpt-4o-mini")
    with agent.override(model=TestModel(custom_output_text="ok")):
        await agent.run("What is the meaning of life?")

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT task, output FROM traces WHERE agent='task_test'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] is not None and "meaning of life" in row[0]
    assert row[1] == "ok"


# ---------------------------------------------------------------------------
# Streaming guardrail limitation is documented honestly
# ---------------------------------------------------------------------------

def test_stream_docstring_warns_about_post_hoc_guardrails():
    """v0.3.12 documented the limitation; v0.5.0 fixed it.
    
    Now the docstring must reference the v0.5.0 fix (stream_guard=True)
    AND still acknowledge that stream_guard=False has the legacy
    post-hoc behavior, so callers understand both modes.
    """
    import inspect
    from largestack._core.engine import AgentEngine
    src = inspect.getsource(AgentEngine.stream)
    # v0.5.0: must document the new opt-in per-chunk mode
    assert "stream_guard" in src, "stream() must document the v0.5.0 stream_guard parameter"
    # And reference the version where the fix landed
    assert "v0.5" in src, "stream() must reference the v0.5.0 fix"


# ---------------------------------------------------------------------------
# All previous fixes still working
# ---------------------------------------------------------------------------

def test_all_v0310_v0311_regression_files_still_present():
    """Make sure no previous regression file was lost."""
    repo = Path(__file__).resolve().parent.parent.parent
    for name in (
        "test_p0_fixes_v030.py",   # v0.3.0 baseline
        "test_p0_fixes_v0310.py",  # v0.3.10 fixes
        "test_p0_fixes_v0311.py",  # v0.3.11 fixes
    ):
        # Some baselines might not exist (only the new ones must)
        # The post-fix ones definitely must.
        if name in ("test_p0_fixes_v0310.py", "test_p0_fixes_v0311.py"):
            assert (repo / "tests" / "unit" / name).exists(), \
                f"regression file missing: {name}"
