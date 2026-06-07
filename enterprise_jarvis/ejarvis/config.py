"""Configuration."""

from __future__ import annotations

import os
from pathlib import Path

MODEL = os.environ.get("LARGESTACK_DEFAULT_MODEL", "deepseek/deepseek-chat")
DATA_DIR = Path(os.environ.get("EJARVIS_DATA_DIR", str(Path.home() / ".ejarvis")))
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
COST_BUDGET = float(os.environ.get("EJARVIS_COST_BUDGET", "0.50"))


def has_api_key() -> bool:
    if MODEL.startswith("deepseek/"):
        return bool(os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"))
    if MODEL.startswith("openai/"):
        return bool(os.environ.get("LARGESTACK_OPENAI_API_KEY"))
    if MODEL.startswith("anthropic/"):
        return bool(os.environ.get("LARGESTACK_ANTHROPIC_API_KEY"))
    return True
