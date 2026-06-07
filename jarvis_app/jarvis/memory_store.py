"""Persistent memory for Jarvis: notes (a list) and facts (a key/value store).

Stored as JSON on disk so it survives restarts. Deliberately simple and
dependency-free — this is the 'memory' layer a real assistant needs.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from .config import DATA_DIR

_LOCK = threading.Lock()
_NOTES_FILE = DATA_DIR / "notes.json"
_FACTS_FILE = DATA_DIR / "facts.json"
APPROVALS_FILE = DATA_DIR / "approvals.json"


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write(path, data) -> None:
    _ensure()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---- Notes -----------------------------------------------------------------


def add_note(text: str) -> int:
    """Append a note; returns the new note's 1-based index."""
    with _LOCK:
        notes = _read(_NOTES_FILE, [])
        notes.append({"text": text.strip(), "at": datetime.now().isoformat(timespec="seconds")})
        _write(_NOTES_FILE, notes)
        return len(notes)


def get_notes() -> list[dict[str, Any]]:
    with _LOCK:
        return _read(_NOTES_FILE, [])


# ---- Facts (key/value) -----------------------------------------------------


def set_fact(key: str, value: str) -> None:
    with _LOCK:
        facts = _read(_FACTS_FILE, {})
        facts[key.strip().lower()] = value.strip()
        _write(_FACTS_FILE, facts)


def get_fact(key: str) -> str | None:
    with _LOCK:
        facts = _read(_FACTS_FILE, {})
        return facts.get(key.strip().lower())


def all_facts() -> dict[str, str]:
    with _LOCK:
        return _read(_FACTS_FILE, {})


# ---- Approval queue (persisted) -------------------------------------------


def add_approval(action: str, details: str = "") -> int:
    """Record a risky action as a PENDING approval; returns its id. Never executes it."""
    with _LOCK:
        items = _read(APPROVALS_FILE, [])
        rid = len(items) + 1
        items.append(
            {
                "id": rid,
                "action": action.strip(),
                "details": details.strip(),
                "status": "pending",
                "at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        _write(APPROVALS_FILE, items)
        return rid


def get_approvals() -> list[dict[str, Any]]:
    with _LOCK:
        return _read(APPROVALS_FILE, [])
