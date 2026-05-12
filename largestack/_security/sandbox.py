"""Agent sandboxing — restrict what tools can do."""
from __future__ import annotations
from dataclasses import dataclass, field
import tempfile

@dataclass
class Sandbox:
    """Execution sandbox configuration.
    
    Controls: network access, file system, memory, CPU, timeout.
    Backends: subprocess (default), docker, gvisor (recommended).
    """
    backend: str = "subprocess"
    network_allow: list[str] = field(default_factory=list)
    network_deny: list[str] = field(default_factory=lambda: ["*"])
    allowed_paths: list[str] = field(default_factory=lambda: [tempfile.gettempdir()])
    max_memory_mb: int = 512
    max_cpu_seconds: int = 60
    timeout_seconds: float = 30.0

    def check_network(self, url: str) -> bool:
        """Check if URL is allowed."""
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        # Check deny first
        for pattern in self.network_deny:
            if pattern == "*" and self.network_allow:
                # Deny all except allowed
                for allow in self.network_allow:
                    if host.endswith(allow.lstrip("*.")):
                        return True
                return False
            if host.endswith(pattern.lstrip("*.")):
                return False
        return True

    def check_path(self, path: str) -> bool:
        """Check if file path is allowed."""
        import os
        abs_path = os.path.abspath(path)
        return any(abs_path.startswith(os.path.abspath(p)) for p in self.allowed_paths)
