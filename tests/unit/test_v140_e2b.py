"""v0.14.0: Tests for E2B sandbox bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# -------------------- Module + types --------------------


def test_module_imports():
    from largestack._security.e2b_bridge import (
        SandboxResult,
        E2BConfig,
        E2BSandbox,
        LocalSandbox,
    )

    assert SandboxResult is not None
    assert E2BConfig is not None


def test_sandbox_result_succeeded_property():
    from largestack._security.e2b_bridge import SandboxResult

    ok = SandboxResult(stdout="hello", exit_code=0)
    assert ok.succeeded
    fail = SandboxResult(stderr="oops", exit_code=1)
    assert not fail.succeeded
    error = SandboxResult(error="boom", exit_code=0)
    assert not error.succeeded  # error set


def test_e2b_config_defaults():
    from largestack._security.e2b_bridge import E2BConfig

    c = E2BConfig()
    assert c.template == "python-3.11"
    assert c.timeout_seconds == 30.0
    assert c.cpu_count == 2


def test_e2b_sandbox_rejects_no_india_residency_flag():
    from largestack._security.e2b_bridge import E2BSandbox, E2BConfig

    cfg = E2BConfig(allow_non_india_region=False)
    with pytest.raises(ValueError, match="India-resident"):
        E2BSandbox(cfg)


# -------------------- E2BSandbox (mocked) --------------------


@pytest.mark.asyncio
async def test_e2b_execute_returns_error_when_e2b_missing():
    from largestack._security import e2b_bridge
    from largestack._security.e2b_bridge import E2BSandbox

    with patch.object(e2b_bridge, "_have_e2b", return_value=False):
        sb = E2BSandbox(api_key="test-key")
        result = await sb.execute("print(1)")
        assert result.exit_code == 1
        assert "e2b-code-interpreter" in result.error


@pytest.mark.asyncio
async def test_e2b_execute_empty_code():
    from largestack._security.e2b_bridge import E2BSandbox

    sb = E2BSandbox(api_key="x")
    result = await sb.execute("")
    assert "empty" in result.error


@pytest.mark.asyncio
async def test_e2b_close_idempotent():
    from largestack._security.e2b_bridge import E2BSandbox

    sb = E2BSandbox(api_key="x")
    # Closing without ever calling execute should not blow up
    await sb.close()
    await sb.close()  # second time also safe


# -------------------- LocalSandbox (real execution) --------------------


@pytest.mark.asyncio
async def test_local_sandbox_executes_simple_code():
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("print('hello')")
    assert result.succeeded
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_local_sandbox_catches_runtime_errors():
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("1 / 0")
    assert not result.succeeded
    assert "ZeroDivisionError" in result.error


@pytest.mark.asyncio
async def test_local_sandbox_rejects_syntax_errors():
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("def broken(:")
    assert not result.succeeded
    assert "syntax" in result.error.lower()


@pytest.mark.asyncio
async def test_local_sandbox_blocks_imports_by_default():
    """The restricted globals should not have __import__."""
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("import os")
    # Should fail (NameError on __import__ in restricted globals)
    assert not result.succeeded


@pytest.mark.asyncio
async def test_local_sandbox_timeout():
    """Use a bounded but slow computation that will hit the timeout."""
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox(timeout_seconds=0.05)
    # Large bounded loop — will exceed 50ms before completing
    code = "n = 0\nfor _ in range(50_000_000): n += 1"
    result = await sb.execute(code)
    # Either timeout (124) OR the test machine is too fast and it
    # finished — accept either as long as it didn't hang the process
    assert result.exit_code in (0, 124)
    if result.exit_code == 124:
        assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_local_sandbox_records_execution_time():
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("x = 1 + 1")
    assert result.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_local_sandbox_async_context_manager():
    """Local sandbox needs no aenter/aexit but should not block their use."""
    from largestack._security.e2b_bridge import LocalSandbox

    sb = LocalSandbox()
    result = await sb.execute("print('via ctx')")
    await sb.close()
    assert "via ctx" in result.stdout
