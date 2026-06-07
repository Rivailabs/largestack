"""E2B sandbox adapter — Firecracker-isolated code execution.

Production-grade replacement for local subprocess execution.

Usage:
    from largestack._core.e2b_sandbox import E2BSandbox

    sandbox = E2BSandbox(api_key="e2b_...")
    result = await sandbox.run_python("print(2+2)")
    print(result.stdout)  # "4"
"""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("largestack.e2b")


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


@dataclass
class SandboxResult:
    """Result of a sandboxed execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error: str | None = None
    artifacts: list[dict] = None

    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []


class E2BSandbox:
    """E2B-backed Python execution sandbox.

    Falls back to local subprocess if E2B not installed (with warning).
    """

    def __init__(self, api_key: str | None = None, template: str = "code-interpreter-v1"):
        self.api_key = (
            api_key or os.environ.get("E2B_API_KEY") or os.environ.get("LARGESTACK_E2B_API_KEY")
        )
        self.template = template
        self._sandbox = None
        self._available = False
        try:
            from e2b_code_interpreter import Sandbox

            self._Sandbox = Sandbox
            self._available = True
        except ImportError:
            log.warning("e2b-code-interpreter not installed. pip install e2b-code-interpreter")

    async def __aenter__(self):
        if self._available and self.api_key:
            self._sandbox = self._Sandbox.create(api_key=self.api_key, template=self.template)
        return self

    async def __aexit__(self, *args):
        if self._sandbox:
            self._sandbox.kill()

    async def run_python(self, code: str, timeout: int = 30) -> SandboxResult:
        """Execute Python in isolated sandbox."""
        if self._available and self.api_key:
            return await self._run_e2b(code, timeout)
        return await self._run_local(code, timeout)

    async def _run_e2b(self, code: str, timeout: int) -> SandboxResult:
        try:
            if not self._sandbox:
                self._sandbox = self._Sandbox.create(api_key=self.api_key, template=self.template)
            execution = self._sandbox.run_code(code, timeout=timeout)
            return SandboxResult(
                stdout="\n".join(execution.logs.stdout) if execution.logs else "",
                stderr="\n".join(execution.logs.stderr) if execution.logs else "",
                exit_code=0 if not execution.error else 1,
                error=str(execution.error) if execution.error else None,
            )
        except Exception as e:
            log.error(f"E2B execution failed: {e}")
            return SandboxResult(error=str(e), exit_code=1)

    async def _run_local(self, code: str, timeout: int) -> SandboxResult:
        """Local fallback (less secure).

        Always kills/drains subprocesses on timeout to avoid ResourceWarning leaks.
        """
        import asyncio
        import sys
        import tempfile

        path = None
        proc = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=".py",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as f:
                f.write(code)
                path = f.name

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass

                try:
                    stdout, stderr = await proc.communicate()
                except Exception:
                    try:
                        await proc.wait()
                    except Exception:
                        pass
                    stdout, stderr = b"", b""

                return SandboxResult(
                    error=f"Timeout after {timeout}s",
                    exit_code=124,
                    stdout=(stdout or b"").decode("utf-8", errors="replace"),
                    stderr=(stderr or b"").decode("utf-8", errors="replace"),
                )

            return SandboxResult(
                stdout=(stdout or b"").decode("utf-8", errors="replace"),
                stderr=(stderr or b"").decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
            )

        except Exception as e:
            return SandboxResult(error=str(e), exit_code=1)

        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    @property
    def available(self) -> bool:
        return self._available and bool(self.api_key)
