"""Public Memory convenience API."""

from __future__ import annotations
from largestack._memory.buffer import ConversationMemory
from largestack._memory.episodic import EpisodicMemory
from largestack._memory.observational import ObservationalMemory
from largestack._memory.procedural import ProceduralMemory
from largestack._memory.semantic import SemanticMemory
from largestack._memory.graph import GraphMemory
from largestack._memory.shared import SharedMemorySpace


def create_memory(strategy: str = "buffer", **kwargs):
    """Create a memory backend.

    Strategies: buffer, sliding_window, token_limited, episodic, observational, graph
    """
    if strategy in ("buffer", "sliding_window", "token_limited"):
        return ConversationMemory(strategy=strategy, **kwargs)
    elif strategy == "episodic":
        return EpisodicMemory(**kwargs)
    elif strategy == "observational":
        return ObservationalMemory(**kwargs)
    elif strategy == "procedural":
        return ProceduralMemory()
    elif strategy == "semantic":
        return SemanticMemory()
    elif strategy == "graph":
        return GraphMemory()
    return ConversationMemory(**kwargs)
