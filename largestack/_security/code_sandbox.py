"""Sandboxed code execution — E2B-compatible interface.

50% of Fortune 500 run agent code in sandboxes. Docker is NOT a sandbox.

Backends:
    - subprocess: Basic subprocess with resource limits (default)
    - docker: Docker container isolation
    - e2b: E2B cloud sandbox (production recommended)

    from largestack._security.code_sandbox import CodeSandbox
    sb = CodeSandbox(backend="subprocess", timeout=30)
    result = await sb.execute("print(2 + 2)", language="python")
    # {"stdout": "4\\n", "stderr": "", "exit_code": 0, "duration_ms": 12.5}
"""
from __future__ import annotations
import asyncio, os, signal, tempfile, time, logging, sys
from typing import Any

log = logging.getLogger("largestack.sandbox")


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

class SandboxResult:
    def __init__(self, stdout: str = "", stderr: str = "", exit_code: int = 0, duration_ms: float = 0):
        self.stdout = stdout; self.stderr = stderr
        self.exit_code = exit_code; self.duration_ms = duration_ms
        self.success = exit_code == 0
    def to_dict(self) -> dict:
        return {"stdout": self.stdout, "stderr": self.stderr,
                "exit_code": self.exit_code, "duration_ms": self.duration_ms, "success": self.success}

class CodeSandbox:
    """Execute code in a sandboxed environment.
    
    WARNING: The subprocess backend provides NO kernel isolation.
    It is suitable for development/testing only.
    For production, use backend='e2b' (Firecracker microVMs).
    """
    """Execute code in a sandboxed environment."""

    def __init__(self, backend: str = "subprocess", timeout: float = 30,
                 max_memory_mb: int = 0, allowed_imports: list[str] = None,
                 e2b_api_key: str = None):
        self.backend = backend
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.allowed_imports = allowed_imports
        self.e2b_api_key = e2b_api_key or os.environ.get("E2B_API_KEY")

    async def execute(self, code: str, language: str = "python",
                      env: dict = None) -> SandboxResult:
        """Execute code and return result."""
        # Security: block dangerous imports
        if language == "python" and self.allowed_imports:
            for line in code.split("\n"):
                line = line.strip()
                if line.startswith("import ") or line.startswith("from "):
                    module = line.split()[1].split(".")[0].rstrip(";,")
                    if module not in self.allowed_imports:
                        return SandboxResult(stderr=f"Import blocked: {module}", exit_code=1)

        if self.backend == "subprocess":
            log.warning("CodeSandbox: subprocess backend has NO kernel isolation. "
                       "Use backend='e2b' for production (Firecracker microVMs).")
        if self.backend == "e2b":
            return await self._e2b_execute(code, language, env)
        elif self.backend == "docker":
            return await self._docker_execute(code, language, env)
        else:
            return await self._subprocess_execute(code, language, env)


    def _resource_limiter(self):
        """Return a best-effort preexec memory limiter for subprocess backend.

        Disabled by default because RLIMIT_AS is not portable and can break
        interpreter startup in constrained containers. For production isolation,
        use backend='e2b' or backend='docker'.
        """
        if not self.max_memory_mb or self.max_memory_mb <= 0:
            return None

        def _limit():
            try:
                import resource
                if hasattr(resource, "RLIMIT_AS"):
                    limit = int(self.max_memory_mb) * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except Exception:
                pass

        return _limit

    async def _subprocess_execute(self, code: str, language: str, env: dict = None) -> SandboxResult:
        """Execute in subprocess with resource limits."""
        if language == "python":
            cmd = [sys.executable, "-c", code]
        elif language == "javascript":
            cmd = ["node", "-e", code]
        elif language == "bash":
            cmd = ["bash", "-c", code]
        else:
            return SandboxResult(stderr=f"Unsupported language: {language}", exit_code=1)

        proc_env = {**os.environ, **(env or {})}
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=proc_env,
                preexec_fn=self._resource_limiter() if os.name != 'nt' else None
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            ms = (time.monotonic() - t0) * 1000
            return SandboxResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"),
                                 proc.returncode or 0, ms)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return SandboxResult(stderr=f"Timeout after {self.timeout}s", exit_code=124,
                                 duration_ms=(time.monotonic() - t0) * 1000)
        except Exception as e:
            return SandboxResult(stderr=str(e), exit_code=1,
                                 duration_ms=(time.monotonic() - t0) * 1000)

    async def _e2b_execute(self, code: str, language: str, env: dict = None) -> SandboxResult:
        """Execute in E2B cloud sandbox (most secure, production-grade)."""
        try:
            from e2b_code_interpreter import Sandbox
            t0 = time.monotonic()
            with Sandbox(api_key=self.e2b_api_key) as sb:
                if language == "python":
                    result = sb.run_code(code)
                else:
                    result = sb.process.start_and_wait(f"echo '{code}' | {language}")
                ms = (time.monotonic() - t0) * 1000
                stdout = "\n".join(str(r) for r in (result.results or []))
                stderr = "\n".join(str(e) for e in (result.error_traceback or []))
                return SandboxResult(stdout, stderr, 0 if not result.error else 1, ms)
        except ImportError:
            log.warning("E2B not installed: pip install e2b-code-interpreter. Falling back to subprocess.")
            return await self._subprocess_execute(code, language, env)

    async def _docker_execute(self, code: str, language: str, env: dict = None) -> SandboxResult:
        """Execute in Docker container."""
        import shutil
        if not shutil.which("docker"):
            log.warning("Docker not found. Falling back to subprocess.")
            return await self._subprocess_execute(code, language, env)

        images = {"python": "python:3.12-slim", "javascript": "node:20-slim", "bash": "ubuntu:24.04"}
        image = images.get(language, "python:3.12-slim")
        cmd_in_container = f'{language} -c "{code}"' if language != "bash" else f'bash -c "{code}"'

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm", "--network=none",
                f"--memory={self.max_memory_mb}m", "--cpus=0.5",
                "--pids-limit=50", "--read-only",
                image, "sh", "-c", cmd_in_container,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            ms = (time.monotonic() - t0) * 1000
            return SandboxResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"),
                                 proc.returncode or 0, ms)
        except asyncio.TimeoutError:
            return SandboxResult(stderr=f"Docker timeout after {self.timeout}s", exit_code=124)
        except Exception as e:
            return SandboxResult(stderr=str(e), exit_code=1)
