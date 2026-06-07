"""Integration tests need network and/or external services (live providers, A2A/MCP
HTTP servers, Redis, etc.). To keep the release gate (`pytest tests/`) green and
hang-free on a sandboxed/offline machine, these are auto-skipped when no network is
available — and always run in networked CI.

Force-run them anywhere with: LARGESTACK_RUN_INTEGRATION=1
"""

from __future__ import annotations
import os
import socket

import pytest


def _network_available() -> bool:
    if os.environ.get("LARGESTACK_RUN_INTEGRATION", "").lower() in ("1", "true", "yes"):
        return True
    # quick, bounded reachability probe (DNS port); fails fast in restricted sandboxes
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 53), timeout=1.5):
                return True
        except OSError:
            continue
    return False


_NET_OK = _network_available()


def pytest_collection_modifyitems(config, items):
    if _NET_OK:
        return
    skip = pytest.mark.skip(
        reason="integration test needs network/services; offline. "
        "Set LARGESTACK_RUN_INTEGRATION=1 or run on a networked machine."
    )
    for item in items:
        if "tests/integration/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(pytest.mark.integration)
            item.add_marker(skip)
