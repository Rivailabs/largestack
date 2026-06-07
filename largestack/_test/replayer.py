"""Replay recorded interactions for deterministic testing."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from largestack.types import LLMResponse


class Replayer:
    """Replay recorded LLM interactions from fixture files."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.interactions: list[dict] = []
        self._index = 0

    def load(self):
        with open(self.path) as f:
            self.interactions = json.load(f)
        self._index = 0

    def next_response(self) -> LLMResponse:
        if self._index >= len(self.interactions):
            raise RuntimeError("No more recorded interactions")
        interaction = self.interactions[self._index]
        self._index += 1
        resp = interaction["response"]
        return LLMResponse(
            content=resp.get("content", ""),
            model=resp.get("model", "recorded"),
            input_tokens=resp.get("input_tokens", 0),
            output_tokens=resp.get("output_tokens", 0),
        )

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, *args):
        pass
