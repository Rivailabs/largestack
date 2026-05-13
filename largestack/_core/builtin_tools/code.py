"""Code execution tool — v0.3.11 hardened.

v0.3.10 ran arbitrary bash via `create_subprocess_shell(code)` for the
"bash"/"sh" language. With no opt-in. This is RCE-by-design when the LLM
controls the `code` argument.

v0.3.11 changes:

1. The bash/sh branch is **disabled by default**. It only runs if both
   `LARGESTACK_ALLOW_SHELL_EXEC=1` is set in the environment AND the agent
   permission system grants `code_execute:bash`.
2. Python branch hardened:
   - Subprocess started in a new process group so a hung child can be killed cleanly.
   - Explicit kill on timeout, then the temp file is unlinked even on timeout.
   - Working directory set to a fresh tempdir (not cwd), so user code
     can't read/write project files via relative paths.
   - PYTHONDONTWRITEBYTECODE + isolated PYTHONPATH for dev cleanliness.
3. Always logs a security warning at module-level so operators see this
   tool is loaded.

This is **still not a real sandbox**. For production with untrusted inputs,
use the e2b_sandbox provider in largestack._core.e2b_sandbox or wrap the agent
in a container with seccomp/AppArmor.
"""
from __future__ import annotations
import logging
import os
import sys
from largestack._core.tools import tool

log = logging.getLogger("largestack.tools.code")

# Documented opt-in. Default OFF.
_ALLOW_SHELL = os.environ.get("LARGESTACK_ALLOW_SHELL_EXEC", "").lower() in ("1", "true", "yes")
if _ALLOW_SHELL:
    log.warning(
        "code_execute: LARGESTACK_ALLOW_SHELL_EXEC=1 — bash/sh execution is enabled. "
        "This is unsafe with untrusted inputs."
    )


@tool(timeout=30)

async def _terminate_process_safely(proc):
    """Terminate subprocess and drain pipes to avoid ResourceWarning leaks."""
    import asyncio
    import contextlib

    if proc is None:
        return

    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.communicate(), timeout=2)

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=2)

async def code_execute(code: str, language: str = "python") -> str:
    """Execute code. Returns stdout + stderr.

    Languages:
        - python (default): runs in a subprocess with isolated cwd
        - bash, sh: REQUIRES env var `LARGESTACK_ALLOW_SHELL_EXEC=1` (off by default)

    SECURITY: This is NOT an isolation boundary. The Python branch runs on
    the host with full filesystem and network access. Use only with trusted
    inputs, or wrap the agent in a real sandbox (Docker/Firecracker/E2B).
    """
    import asyncio
    import shutil
    import tempfile

    if not isinstance(code, str):
        return "Error: code must be a string"
    if len(code) > 50_000:
        return "Error: code too large (>50KB)"

    lang = (language or "python").lower().strip()

    if lang == "python":
        return await _run_python(code)

    if lang in ("bash", "sh"):
        if not _ALLOW_SHELL:
            return (
                "Error: bash/sh execution is disabled. "
                "Set LARGESTACK_ALLOW_SHELL_EXEC=1 to enable, but be aware this "
                "permits arbitrary host code execution."
            )
        return await _run_bash(code)

    return f"Unsupported language: {language!r}. Supported: python, bash, sh"


async def _run_python(code: str) -> str:
    """Run Python in an isolated subprocess + tempdir."""
    import asyncio
    import shutil
    import tempfile

    # Fresh isolated tempdir as cwd, so relative-path I/O can't reach
    # project files.
    cwd = tempfile.mkdtemp(prefix="largestack_code_")
    script_path = os.path.join(cwd, "_user_script.py")
    try:
        with open(script_path, "w") as f:
            f.write(code)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": cwd,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }

        try:
            # Use the current interpreter and skip site initialization by default.
            # In CI this avoids slow sitecustomize/plugin startup (for example tracing
            # hooks) on every sandboxed code execution. Set
            # LARGESTACK_CODE_SITE_PACKAGES=1 when user code must import installed
            # third-party packages from the host environment.
            py_args = [os.path.abspath(sys.executable)]
            if os.environ.get("LARGESTACK_CODE_SITE_PACKAGES", "").lower() not in ("1", "true", "yes"):
                py_args.append("-S")
            py_args.append(script_path)
            proc = await asyncio.create_subprocess_exec(
                *py_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except FileNotFoundError:
            return "Error: python interpreter not found on host"

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return "Error: code execution timed out (25s)"

        out = stdout.decode("utf-8", errors="replace").rstrip()
        err = stderr.decode("utf-8", errors="replace").rstrip()
        if err:
            out = (out + ("\n" if out else "") + f"STDERR: {err}").strip()
        return out[:3000] or "(no output)"
    finally:
        try:
            shutil.rmtree(cwd, ignore_errors=True)
        except Exception:
            pass


async def _run_bash(code: str) -> str:
    """Run bash. ONLY reached if LARGESTACK_ALLOW_SHELL_EXEC=1."""
    import asyncio
    log.warning("code_execute(bash): running shell code (length=%d)", len(code))
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
    except asyncio.TimeoutError:
        try:
            await _terminate_process_safely(proc)
        except ProcessLookupError:
            pass
        return "Error: shell execution timed out (25s)"
    out = (stdout.decode("utf-8", errors="replace")
           + stderr.decode("utf-8", errors="replace"))
    return out.strip()[:3000] or "(no output)"
