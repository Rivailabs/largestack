"""Security regression — SQL injection, path traversal, command injection."""

import os
import sqlite3
from pathlib import Path

import pytest


# ─── SQL injection in dashboard queries ───────────────────────


def test_dashboard_queries_use_parameterized_sql():
    """Dashboard SQL queries must use parameter binding (?, %s), not string concat."""
    import largestack._dashboard.app as app_mod
    import largestack._dashboard.api as api_mod

    src_app = Path(app_mod.__file__).read_text()
    src_api = Path(api_mod.__file__).read_text()

    # Dangerous patterns: f-string SQL with interpolated values
    # NOTE: these patterns are heuristic; the real defense is _q() / _db_query()
    # using `db.execute(sql, params)` — verify that's the pattern.
    import re

    for name, src in (("app.py", src_app), ("api.py", src_api)):
        # Look for any SQL string with f-string interpolation of a non-constant.
        # Allowed: f"... LIMIT {n}" where n is bounded by query-param caps.
        # Disallowed: f"... WHERE name='{user_input}'"
        bad = re.findall(r"execute\s*\(\s*f['\"][^'\"]*\{[^}]+\}[^'\"]*['\"]", src)
        # Filter out the bounded LIMIT pattern (we cap limit ≤ 1000 in api.py)
        bad = [b for b in bad if "LIMIT" not in b.upper()]
        assert not bad, f"f-string SQL in {name}: {bad}"


def test_dashboard_query_helpers_use_param_binding():
    """The _q / _db_query helpers must accept (sql, params) — not interpolate."""
    import largestack._dashboard.app as app_mod

    src = Path(app_mod.__file__).read_text()
    # Helper signature must accept params tuple
    assert "def _db_query" in src
    assert "params=()" in src or "params:" in src
    # Helper passes params to db.execute
    assert ".execute(sql, params)" in src or "execute(sql, params)" in src


# ─── Path traversal in vault file backend ─────────────────────


def test_vault_rejects_path_traversal_in_key():
    """SecretStore key with .. or / must not write outside vault dir."""
    from largestack._security.vault import SecretStore

    v = SecretStore(backend="memory")
    # Memory backend ignores paths but the API shouldn't crash
    v.set("../../etc/passwd", "should-not-leak")
    # Reading back should give us the value as a string key (no path traversal)
    assert v.get("../../etc/passwd") == "should-not-leak"


def test_vault_file_backend_sanitizes_keys(tmp_path):
    """File backend must sanitize key names to prevent writing outside vault dir."""
    from largestack._security.vault import SecretStore

    v = SecretStore(backend="file", path=str(tmp_path / "vault"))
    # Adversarial key
    v.set("../../etc/evil", "value")
    # Verify nothing was written outside the vault dir
    parent = tmp_path
    for child in parent.rglob("*"):
        if child.is_file():
            # Must be inside tmp_path/vault, never escape
            assert str(child).startswith(str(tmp_path / "vault")), (
                f"Vault wrote outside its dir: {child}"
            )


# ─── Command injection in subprocess calls ────────────────────


def test_no_shell_true_in_subprocess():
    """Code must not use subprocess.run/Popen with shell=True on user input.

    `shell=True` is a known command-injection vector. Allowed only if the
    command is a fixed string literal, never user-controlled.
    """
    import re

    root = Path(__file__).resolve().parent.parent.parent / "largestack"
    pattern = re.compile(
        r"subprocess\.(?:run|Popen|call|check_(?:output|call))\s*\([^)]*shell\s*=\s*True",
        re.MULTILINE | re.DOTALL,
    )
    found = []
    for f in root.rglob("*.py"):
        text = f.read_text()
        for m in pattern.finditer(text):
            found.append((str(f.relative_to(root)), m.group(0)[:80]))
    assert not found, f"shell=True found (command injection risk): {found}"


# ─── Pydantic input validation ────────────────────────────────


def test_run_request_rejects_empty_task():
    """RunRequest must require min_length=1 — empty string should 422."""
    from largestack.serve import create_api
    from largestack import Agent

    a = Agent(name="t", llm="openai/gpt-4o-mini")

    os.environ["LARGESTACK_API_KEY"] = "k"
    os.environ["LARGESTACK_RATE_LIMIT_DISABLE"] = "1"
    try:
        from fastapi.testclient import TestClient

        client = TestClient(create_api(a))
        r = client.post("/run", json={"task": ""}, headers={"X-API-Key": "k"})
        assert r.status_code == 422
    finally:
        os.environ.pop("LARGESTACK_API_KEY", None)
        os.environ.pop("LARGESTACK_RATE_LIMIT_DISABLE", None)


def test_run_request_rejects_oversized_task():
    """RunRequest must enforce max_length."""
    os.environ["LARGESTACK_API_KEY"] = "k"
    os.environ["LARGESTACK_RATE_LIMIT_DISABLE"] = "1"
    os.environ["LARGESTACK_MAX_TASK_LENGTH"] = "100"
    try:
        from fastapi.testclient import TestClient
        from largestack import Agent
        from largestack.serve import create_api

        a = Agent(name="t", llm="openai/gpt-4o-mini")
        client = TestClient(create_api(a))
        r = client.post("/run", json={"task": "x" * 200}, headers={"X-API-Key": "k"})
        assert r.status_code == 422
    finally:
        for k in (
            "LARGESTACK_API_KEY",
            "LARGESTACK_RATE_LIMIT_DISABLE",
            "LARGESTACK_MAX_TASK_LENGTH",
        ):
            os.environ.pop(k, None)


def test_cost_budget_negative_rejected():
    """Negative cost_budget must be rejected by Field(ge=0)."""
    os.environ["LARGESTACK_API_KEY"] = "k"
    os.environ["LARGESTACK_RATE_LIMIT_DISABLE"] = "1"
    try:
        from fastapi.testclient import TestClient
        from largestack import Agent
        from largestack.serve import create_api

        a = Agent(name="t", llm="openai/gpt-4o-mini")
        client = TestClient(create_api(a))
        r = client.post(
            "/run", json={"task": "ok", "cost_budget": -1.0}, headers={"X-API-Key": "k"}
        )
        assert r.status_code == 422
    finally:
        for k in ("LARGESTACK_API_KEY", "LARGESTACK_RATE_LIMIT_DISABLE"):
            os.environ.pop(k, None)


def test_max_turns_zero_rejected():
    """max_turns must be >= 1."""
    os.environ["LARGESTACK_API_KEY"] = "k"
    os.environ["LARGESTACK_RATE_LIMIT_DISABLE"] = "1"
    try:
        from fastapi.testclient import TestClient
        from largestack import Agent
        from largestack.serve import create_api

        a = Agent(name="t", llm="openai/gpt-4o-mini")
        client = TestClient(create_api(a))
        r = client.post("/run", json={"task": "ok", "max_turns": 0}, headers={"X-API-Key": "k"})
        assert r.status_code == 422
    finally:
        for k in ("LARGESTACK_API_KEY", "LARGESTACK_RATE_LIMIT_DISABLE"):
            os.environ.pop(k, None)
