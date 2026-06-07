"""Configuration for Jarvis."""

from __future__ import annotations

import os
from pathlib import Path

# LLM provider. Defaults to DeepSeek (cheap, good tool-calling).
# Override with LARGESTACK_DEFAULT_MODEL, e.g. "openai/gpt-4o-mini".
MODEL = os.environ.get("LARGESTACK_DEFAULT_MODEL", "deepseek/deepseek-chat")

# Where Jarvis stores its persistent memory (notes + facts). Survives restarts.
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", str(Path.home() / ".jarvis")))

# Folder of local documents Jarvis can answer questions about (simple RAG).
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

# Jarvis may only list files INSIDE this workspace (default: the launch directory).
# Anything outside is refused, so the assistant can't enumerate the host filesystem.
WORKSPACE_ROOT = Path(os.environ.get("JARVIS_WORKSPACE", os.getcwd())).resolve()

# Spend ceiling per single user request (USD). Stops runaway tool loops.
COST_BUDGET = float(os.environ.get("JARVIS_COST_BUDGET", "0.50"))

# Max reasoning/tool turns per request.
MAX_TURNS = int(os.environ.get("JARVIS_MAX_TURNS", "8"))


def has_api_key() -> bool:
    """True if a usable provider key is configured for the selected model."""
    if MODEL.startswith("deepseek/"):
        return bool(os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"))
    if MODEL.startswith("openai/"):
        return bool(os.environ.get("LARGESTACK_OPENAI_API_KEY"))
    if MODEL.startswith("anthropic/"):
        return bool(os.environ.get("LARGESTACK_ANTHROPIC_API_KEY"))
    # Local / ollama / others: assume reachable.
    return True
