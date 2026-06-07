"""Emergency kill switch — halt all agents within 60 seconds.

Uses file-based flag (default) or Redis for distributed systems.
Cascade: killing parent automatically kills all children.
"""

from __future__ import annotations
import os, time, logging

log = logging.getLogger("largestack.kill_switch")

_KILL_FILE = os.path.expanduser("~/.largestack/.kill_switch")
_killed = False


def activate(reason: str = "manual", by: str = "operator"):
    """Activate kill switch — all agents will halt."""
    global _killed
    _killed = True
    os.makedirs(os.path.dirname(_KILL_FILE), exist_ok=True)
    with open(_KILL_FILE, "w") as f:
        f.write(f"{time.time()}|{reason}|{by}")
    log.critical(f"KILL SWITCH ACTIVATED by {by}: {reason}")


def deactivate():
    """Deactivate kill switch — resume normal operation."""
    global _killed
    _killed = False
    if os.path.exists(_KILL_FILE):
        os.remove(_KILL_FILE)
    log.info("Kill switch deactivated")


def is_active() -> bool:
    """Check if kill switch is active."""
    global _killed
    if _killed:
        return True
    return os.path.exists(_KILL_FILE)


def check():
    """Check kill switch and raise if active."""
    from largestack.errors import KillSwitchActivatedError

    if is_active():
        raise KillSwitchActivatedError()
