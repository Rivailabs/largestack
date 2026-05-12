"""E2B sandbox bridge (v0.14.0).

Closes Tier A #16. Production-grade sandbox for ``CodeAgentV11`` via
E2B (https://e2b.dev). The local CPython sandbox is fine for dev but
has security limitations; E2B provides:

- Firecracker microVM isolation (1ms boot)
- Per-tenant filesystem
- Memory + CPU limits enforced at hypervisor level
- Network egress allowlist
- Persistent volumes (across runs)

The bridge implements the same interface as the local sandbox so
``CodeAgentV11`` can swap them transparently.

Usage::

    from largestack._security.e2b_bridge import E2BSandbox
    sandbox = E2BSandbox(api_key="...", template="python-3.11")
    result = await sandbox.execute("print('hello from E2B')")
    print(result.stdout)
    await sandbox.close()
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.security.e2b")


def _have_e2b() -> bool:
    try:
        import e2b_code_interpreter  # noqa
        return True
    except ImportError:
        try:
            import e2b  # noqa
            return True
        except ImportError:
            return False


def _validate_local_exec_ast(tree):
    """Reject high-risk constructs before local fallback execution.

    Defense-in-depth only. Production deployments should prefer an external
    isolation backend such as E2B, Docker, gVisor, or Firecracker.
    """
    import ast

    blocked_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
        ast.Lambda,
    )
    blocked_names = {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
    }

    for node in ast.walk(tree):
        if isinstance(node, blocked_nodes):
            raise ValueError(f"blocked syntax: {type(node).__name__}")

        if isinstance(node, ast.Name) and node.id in blocked_names:
            raise ValueError(f"blocked name: {node.id}")

        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__")
            or node.attr in {"__class__", "__mro__", "__subclasses__"}
        ):
            raise ValueError(f"blocked attribute: {node.attr}")


@dataclass


class SandboxResult:
    """Result of code execution in a sandbox."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.error


@dataclass
class E2BConfig:
    """Configuration for E2B sandbox bridge."""
    api_key: str = ""
    template: str = "python-3.11"
    timeout_seconds: float = 30.0
    cpu_count: int = 2
    memory_mb: int = 512
    # India-residency: E2B currently runs in US/EU. For India deploys,
    # set ``allow_non_india_region=False`` and the bridge will refuse.
    allow_non_india_region: bool = True
    network_egress_allowlist: list[str] = field(default_factory=list)


class E2BSandbox:
    """Production-grade sandbox via E2B Firecracker microVMs.

    Args:
        config: ``E2BConfig`` with API key + resource limits
        api_key: shorthand if no other config needed
    """

    def __init__(
        self,
        config: E2BConfig | None = None,
        *,
        api_key: str | None = None,
        template: str = "python-3.11",
    ):
        if config is None:
            config = E2BConfig(
                api_key=api_key or "",
                template=template,
            )
        self.config = config
        self._sandbox = None
        self._closed = False

        if not config.allow_non_india_region:
            raise ValueError(
                "E2B does not currently offer India-resident sandboxes. "
                "Set allow_non_india_region=True or use the local sandbox."
            )

    async def _ensure_sandbox(self):
        """Lazy-create the E2B Sandbox handle."""
        if self._sandbox is not None:
            return self._sandbox
        if not _have_e2b():
            raise ImportError(
                "e2b-code-interpreter required. Install: "
                "pip install e2b-code-interpreter"
            )

        # Prefer the modern code_interpreter package
        try:
            from e2b_code_interpreter import AsyncSandbox
            self._sandbox = await AsyncSandbox.create(
                template=self.config.template,
                api_key=self.config.api_key or None,
                timeout=int(self.config.timeout_seconds),
            )
        except ImportError:
            from e2b import AsyncSandbox  # legacy
            self._sandbox = await AsyncSandbox.create(
                template=self.config.template,
                api_key=self.config.api_key or None,
            )
        return self._sandbox

    async def execute(
        self,
        code: str,
        *,
        timeout_seconds: float | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run Python code in the sandbox and return the result."""
        if self._closed:
            raise RuntimeError("sandbox is closed")
        if not code:
            return SandboxResult(error="empty code")

        timeout = timeout_seconds or self.config.timeout_seconds

        try:
            sb = await self._ensure_sandbox()
        except ImportError as e:
            return SandboxResult(error=str(e), exit_code=1)

        import time
        start = time.monotonic()
        try:
            # E2B's run_code returns an Execution object
            execution = await asyncio.wait_for(
                sb.run_code(code, envs=env or {}),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                error=f"timeout after {timeout}s",
                exit_code=124,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return SandboxResult(
                error=str(e),
                exit_code=1,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        # Normalise execution shape
        stdout = ""
        stderr = ""
        if hasattr(execution, "logs"):
            stdout = "\n".join(execution.logs.stdout or [])
            stderr = "\n".join(execution.logs.stderr or [])
        elif hasattr(execution, "stdout"):
            stdout = execution.stdout or ""
            stderr = getattr(execution, "stderr", "") or ""

        err = ""
        if hasattr(execution, "error") and execution.error:
            err = str(execution.error)

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=0 if not err else 1,
            error=err,
            execution_time_ms=elapsed_ms,
            metadata={"template": self.config.template},
        )

    async def upload_file(
        self, local_path: str, sandbox_path: str,
    ) -> bool:
        """Upload a file into the sandbox."""
        sb = await self._ensure_sandbox()
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            await sb.files.write(sandbox_path, data)
            return True
        except Exception as e:
            log.warning(f"upload_file failed: {e}")
            return False

    async def download_file(
        self, sandbox_path: str, local_path: str,
    ) -> bool:
        """Download a file from the sandbox."""
        sb = await self._ensure_sandbox()
        try:
            data = await sb.files.read(sandbox_path)
            with open(local_path, "wb") as f:
                if isinstance(data, str):
                    f.write(data.encode())
                else:
                    f.write(data)
            return True
        except Exception as e:
            log.warning(f"download_file failed: {e}")
            return False

    async def close(self) -> None:
        """Close and destroy the sandbox."""
        if self._sandbox is not None and not self._closed:
            try:
                await self._sandbox.kill()
            except Exception as e:
                log.warning(f"sandbox close failed: {e}")
            finally:
                self._sandbox = None
                self._closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# -------------------- Local fallback (already exists) --------------------

class LocalSandbox:
    """Fallback sandbox using stdlib ``exec`` with restricted globals.

    For dev/testing only — NOT a security boundary in production.
    Use ``E2BSandbox`` for production.
    """

    def __init__(self, *, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        code: str,
        *,
        timeout_seconds: float | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        if not code:
            return SandboxResult(error="empty code")

        import io, contextlib, time, ast
        try:
            ast.parse(code)
        except SyntaxError as e:
            return SandboxResult(
                error=f"syntax error: {e}", exit_code=1,
            )

        try:
            import ast

            parsed = ast.parse(code, mode="exec")
            _validate_local_exec_ast(parsed)
            compiled_code = compile(parsed, "<sandbox>", "exec")
        except SyntaxError as e:
            return SandboxResult(
                error=f"syntax error: {e}", exit_code=1,
            )
        except ValueError as e:
            return SandboxResult(
                error=f"blocked unsafe code: {e}", exit_code=1,
            )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        def _run():
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                # Restricted globals — no __import__ access by default
                safe_globals = {
                    "__builtins__": {
                        "print": print, "len": len, "range": range,
                        "str": str, "int": int, "float": float,
                        "list": list, "dict": dict, "tuple": tuple,
                        "set": set, "bool": bool, "abs": abs,
                        "min": min, "max": max, "sum": sum,
                        "sorted": sorted, "enumerate": enumerate,
                        "zip": zip, "map": map, "filter": filter,
                        "round": round,
                    },
                }
                exec(compiled_code, safe_globals, {})  # nosec B102

        timeout = timeout_seconds or self.timeout_seconds
        start = time.monotonic()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_run), timeout=timeout,
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                error=f"timeout after {timeout}s",
                exit_code=124,
                execution_time_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return SandboxResult(
                error=f"{type(e).__name__}: {e}",
                exit_code=1,
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                execution_time_ms=(time.monotonic() - start) * 1000,
            )

        return SandboxResult(
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            exit_code=0,
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

    async def close(self) -> None:
        pass


__all__ = [
    "SandboxResult", "E2BConfig", "E2BSandbox", "LocalSandbox",
]
