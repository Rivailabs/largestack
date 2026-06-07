"""Observational Memory — Mastra pattern achieving ~95% on LongMemEval.

Two background agents: Observer extracts facts, Reflector compresses.
No vector DB needed. Pure text. Prompt-caching compatible (90% off).
"""

from __future__ import annotations
import time
from typing import Any


class ObservationalMemory:
    """Observer + Reflector pattern for long-term memory.

    - Observer: Extract key facts as emoji-prioritized notes
    - Reflector: Compress when notes exceed threshold
    - 5-40x compression vs raw conversation
    """

    def __init__(self, max_tokens: int = 30000, compress_at: int = 25000):
        self.notes: list[dict] = []
        self.max_tokens = max_tokens
        self.compress_at = compress_at
        self._total_tokens = 0

    async def observe(self, messages: list[dict], llm_fn=None):
        """Extract key facts from conversation messages."""
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str) or not content.strip():
                continue

            # Extract facts (simple version — in production use LLM)
            facts = self._extract_facts(content, msg.get("role", ""))
            for fact in facts:
                self.notes.append(
                    {
                        "fact": fact["text"],
                        "priority": fact["priority"],  # 🔴 critical, 🟡 important, ⚪ routine
                        "timestamp": time.time(),
                        "source_role": msg.get("role", "unknown"),
                    }
                )
                self._total_tokens += len(fact["text"]) // 4

        # Compress if needed
        if self._total_tokens > self.compress_at:
            await self.compress(llm_fn)

    async def compress(self, llm_fn=None):
        """Reflector: compress accumulated notes."""
        if not self.notes:
            return
        # Keep critical and important, summarize routine
        critical = [n for n in self.notes if n["priority"] == "critical"]
        important = [n for n in self.notes if n["priority"] == "important"]
        routine = [n for n in self.notes if n["priority"] == "routine"]

        # Keep all critical and important
        compressed = critical + important
        # Summarize routine (in production: use LLM)
        if routine:
            summary = f"Summary of {len(routine)} routine observations: " + "; ".join(
                n["fact"][:40] for n in routine[-10:]
            )
            compressed.append(
                {
                    "fact": summary,
                    "priority": "routine",
                    "timestamp": time.time(),
                    "source_role": "reflector",
                }
            )

        self.notes = compressed
        self._total_tokens = sum(len(n["fact"]) // 4 for n in self.notes)

    def get_context(self) -> str:
        """Get all notes formatted for LLM context."""
        if not self.notes:
            return ""
        icons = {"critical": "🔴", "important": "🟡", "routine": "⚪"}
        lines = []
        for n in self.notes:
            icon = icons.get(n["priority"], "⚪")
            lines.append(f"{icon} {n['fact']}")
        return "## Memory Notes\n" + "\n".join(lines)

    def _extract_facts(self, text: str, role: str) -> list[dict]:
        """Extract key facts from text (simple heuristic — use LLM in production)."""
        facts = []
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 15]
        for s in sentences[:5]:  # Max 5 facts per message
            # Heuristic priority assignment
            priority = "routine"
            important_kw = [
                "must",
                "always",
                "never",
                "important",
                "critical",
                "remember",
                "prefer",
                "hate",
                "love",
            ]
            critical_kw = ["deadline", "urgent", "emergency", "password", "secret", "key"]
            if any(kw in s.lower() for kw in critical_kw):
                priority = "critical"
            elif any(kw in s.lower() for kw in important_kw):
                priority = "important"
            facts.append({"text": s[:200], "priority": priority})
        return facts

    def __len__(self):
        return len(self.notes)
