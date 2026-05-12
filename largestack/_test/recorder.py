"""Record LLM interactions to JSON fixtures for replay testing."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

class Recorder:
    """Record LLM calls for deterministic replay in tests."""
    def __init__(self, path: str):
        self.path = Path(path)
        self.interactions: list[dict[str, Any]] = []
        self._recording = False

    def start(self):
        self.interactions = []; self._recording = True

    def record(self, messages: list[dict], response: dict, model: str):
        if self._recording:
            self.interactions.append({
                "messages": messages, "response": response, "model": model
            })

    def stop(self):
        self._recording = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.interactions, f, indent=2, default=str)

    def __enter__(self): self.start(); return self
    def __exit__(self, *args): self.stop()
