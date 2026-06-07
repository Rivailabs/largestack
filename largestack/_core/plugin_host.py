"""Plugin process isolation — VS Code-style separate process for plugins.

Each plugin runs in its own subprocess with NDJSON IPC.
Plugin crash doesn't crash the core runtime.
"""

from __future__ import annotations
import asyncio, json, logging, sys
from typing import Any, Callable

log = logging.getLogger("largestack.plugin")


class PluginHost:
    """Host plugins in isolated subprocesses."""

    def __init__(self):
        self._plugins: dict[str, dict] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def load(self, name: str, command: str, env: dict = None):
        """Load a plugin in a subprocess."""
        import os

        plugin_env = {**os.environ, **(env or {})}
        proc = await asyncio.create_subprocess_exec(
            *command.split(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=plugin_env,
        )
        self._processes[name] = proc
        self._plugins[name] = {"command": command, "status": "running", "pid": proc.pid}
        log.info(f"Plugin '{name}' loaded (PID {proc.pid})")

    async def call(self, name: str, method: str, params: dict = None) -> Any:
        """Call a method on a plugin via NDJSON IPC."""
        proc = self._processes.get(name)
        if not proc or proc.returncode is not None:
            raise RuntimeError(f"Plugin '{name}' not running")

        request = json.dumps({"method": method, "params": params or {}}) + "\n"
        proc.stdin.write(request.encode())
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        return json.loads(line.decode())

    async def unload(self, name: str):
        """Unload a plugin."""
        proc = self._processes.pop(name, None)
        if proc:
            proc.terminate()
            await proc.wait()
        self._plugins.pop(name, None)
        log.info(f"Plugin '{name}' unloaded")

    async def health_check(self, name: str) -> bool:
        proc = self._processes.get(name)
        return proc is not None and proc.returncode is None

    def list_plugins(self) -> dict[str, dict]:
        return dict(self._plugins)
