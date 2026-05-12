"""Agent version control — prompts + tools + model as versioned unit."""
from __future__ import annotations
import json, hashlib, time, os
from typing import Any

class AgentVersion:
    """Version an agent's configuration for rollback."""
    def __init__(self, storage_path: str = "~/.largestack/versions"):
        self.path = os.path.expanduser(storage_path)
        os.makedirs(self.path, exist_ok=True)
    
    def save(self, agent_name: str, config: dict) -> str:
        """Save agent version. Returns version hash."""
        version_hash = hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:12]
        version_data = {
            "hash": version_hash, "config": config,
            "created_at": time.time(), "agent": agent_name
        }
        version_file = os.path.join(self.path, f"{agent_name}_{version_hash}.json")
        with open(version_file, "w") as f:
            json.dump(version_data, f, indent=2, default=str)
        
        # Update latest pointer
        with open(os.path.join(self.path, f"{agent_name}_latest.json"), "w") as f:
            json.dump(version_data, f, indent=2, default=str)
        return version_hash
    
    def load(self, agent_name: str, version: str = "latest") -> dict | None:
        """Load agent version config."""
        if version == "latest":
            path = os.path.join(self.path, f"{agent_name}_latest.json")
        else:
            path = os.path.join(self.path, f"{agent_name}_{version}.json")
        if not os.path.exists(path): return None
        with open(path) as f: return json.load(f)
    
    def list_versions(self, agent_name: str) -> list[dict]:
        """List all versions of an agent."""
        versions = []
        for f in sorted(os.listdir(self.path)):
            if f.startswith(f"{agent_name}_") and f.endswith(".json") and "latest" not in f:
                with open(os.path.join(self.path, f)) as fh:
                    data = json.load(fh)
                    versions.append({"hash": data["hash"], "created_at": data["created_at"]})
        return versions
    
    def rollback(self, agent_name: str, version: str) -> dict | None:
        """Rollback to a specific version."""
        data = self.load(agent_name, version)
        if data:
            with open(os.path.join(self.path, f"{agent_name}_latest.json"), "w") as f:
                json.dump(data, f, indent=2, default=str)
        return data

class HotReloader:
    """Hot-reload agent configuration without restart."""
    def __init__(self, watch_path: str = "largestack.yaml"):
        self.watch_path = watch_path
        self._last_mtime = 0
        self._callbacks: list = []
    
    def on_reload(self, callback):
        self._callbacks.append(callback); return callback
    
    async def check(self) -> bool:
        """Check if config changed and trigger reload."""
        if not os.path.exists(self.watch_path): return False
        mtime = os.path.getmtime(self.watch_path)
        if mtime > self._last_mtime:
            self._last_mtime = mtime
            import asyncio
            for cb in self._callbacks:
                if asyncio.iscoroutinefunction(cb): await cb()
                else: cb()
            return True
        return False
