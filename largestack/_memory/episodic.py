"""Episodic memory — Stanford Generative Agents pattern.
score = α_r × recency + α_i × importance + α_rel × relevance
"""
from __future__ import annotations
import time, hashlib, json
from typing import Any

class EpisodicMemory:
    """Timestamped events with importance scoring and decay."""
    def __init__(self, decay_rate: float = 0.995, weights: tuple = (0.3, 0.3, 0.4)):
        self.decay = decay_rate  # half-life ~138 hours
        self.w_recency, self.w_importance, self.w_relevance = weights
        self._memories: list[dict] = []
    
    async def add(self, content: str, importance: float = 5.0, metadata: dict = None):
        """Store an episodic memory with timestamp and importance."""
        self._memories.append({
            "content": content,
            "importance": importance,  # 1-10 scale
            "timestamp": time.time(),
            "metadata": metadata or {},
            "id": hashlib.sha256(f"{content}{time.time()}".encode()).hexdigest()[:12],
        })
    
    async def retrieve(self, query: str, k: int = 5) -> list[dict]:
        """Retrieve top-k memories by tri-score."""
        if not self._memories: return []
        now = time.time()
        scored = []
        for mem in self._memories:
            hours = (now - mem["timestamp"]) / 3600
            recency = self.decay ** hours
            importance = mem["importance"] / 10.0
            # Simple relevance: word overlap
            q_words = set(query.lower().split())
            m_words = set(mem["content"].lower().split())
            relevance = len(q_words & m_words) / max(len(q_words), 1)
            score = self.w_recency * recency + self.w_importance * importance + self.w_relevance * relevance
            scored.append({**mem, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]
    
    async def reflect(self, threshold: int = 100) -> str | None:
        """Generate reflections when memory count exceeds threshold."""
        if len(self._memories) < threshold: return None
        # In production: use LLM to generate higher-level insights
        recent = self._memories[-20:]
        return f"Reflection over {len(recent)} recent memories: " + "; ".join(m["content"][:30] for m in recent[:5])
    
    def __len__(self): return len(self._memories)
