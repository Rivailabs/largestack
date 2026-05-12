"""Tests for sandboxed code execution."""
import sys, asyncio; sys.path.insert(0, ".")
from largestack._security.code_sandbox import CodeSandbox

def test_sandbox_basic():
    sb = CodeSandbox(timeout=5)
    r = asyncio.run(sb.execute("print(2+2)", language="python"))
    assert r.stdout.strip() == "4" and r.success and r.exit_code == 0

def test_sandbox_error():
    sb = CodeSandbox(timeout=5)
    r = asyncio.run(sb.execute("raise ValueError('boom')", language="python"))
    assert not r.success and r.exit_code != 0

def test_sandbox_timeout():
    sb = CodeSandbox(timeout=2)
    r = asyncio.run(sb.execute("import time; time.sleep(10)", language="python"))
    assert not r.success

def test_sandbox_import_blocking():
    sb = CodeSandbox(timeout=5, allowed_imports=["math", "json"])
    r = asyncio.run(sb.execute("import os; print(os.getcwd())", language="python"))
    assert not r.success and "blocked" in r.stderr.lower()

def test_sandbox_allowed_import():
    sb = CodeSandbox(timeout=5, allowed_imports=["math"])
    r = asyncio.run(sb.execute("import math; print(math.sqrt(16))", language="python"))
    assert r.stdout.strip() == "4.0" and r.success

def test_sandbox_result_dict():
    sb = CodeSandbox(timeout=5)
    r = asyncio.run(sb.execute("print('ok')", language="python"))
    d = r.to_dict()
    assert d["success"] and d["stdout"].strip() == "ok"
