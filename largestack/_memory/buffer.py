"""Conversation memory — buffer, sliding window, and token-limited strategies.

- Buffer: Keep all messages (for short conversations)
- Sliding window: Keep last N messages (default 20)
- Token-limited: Keep messages until token budget hit (default 4000)
"""

from __future__ import annotations
import logging
from typing import Any
from collections import deque

log = logging.getLogger("largestack.memory")


def estimate_tokens(text: str) -> int:
    """Quick token estimate: ~4 chars per token for English."""
    return len(text) // 4


class ConversationMemory:
    """Stores conversation messages with configurable eviction strategy.

    mem = ConversationMemory(strategy="sliding", max_messages=10)
    await mem.add_message({"role": "user", "content": "Hello"})
    msgs = mem.get_messages()
    """

    def __init__(
        self,
        strategy: str = "buffer",
        max_messages: int = 20,
        max_tokens: int = 4000,
        include_system: bool = True,
    ):
        if strategy not in ("buffer", "sliding", "sliding_window", "token_limited"):
            raise ValueError(f"Unknown strategy: {strategy}")
        self.strategy = strategy
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.include_system = include_system
        self._messages: list[dict] = []

    async def add_message(self, message: dict):
        """Add message with strategy-based eviction."""
        if not isinstance(message, dict) or "role" not in message:
            raise ValueError("Message must be dict with 'role' key")
        self._messages.append(message)
        self._evict()

    async def add_messages(self, messages: list[dict]):
        """Batch add multiple messages."""
        for m in messages:
            await self.add_message(m)

    def _evict(self):
        """Apply eviction strategy. Preserves system messages if include_system."""
        if self.strategy == "buffer":
            return  # Keep everything

        # Separate system messages from conversation
        system = (
            [m for m in self._messages if m.get("role") == "system"] if self.include_system else []
        )
        conv = [m for m in self._messages if m.get("role") != "system"]

        if self.strategy in ("sliding", "sliding_window"):
            conv = conv[-self.max_messages :]
        elif self.strategy == "token_limited":
            # Keep recent messages within token budget
            budget = self.max_tokens
            kept = []
            for m in reversed(conv):
                cost = estimate_tokens(str(m.get("content", "")))
                if cost > budget and kept:
                    break
                budget -= cost
                kept.insert(0, m)
            conv = kept

        # Reassemble: system first, then conversation in order
        self._messages = system + conv

    def get_messages(self) -> list[dict]:
        """Get current message list (defensive copy)."""
        return list(self._messages)

    def clear(self):
        """Clear all messages."""
        self._messages = []

    def get_by_role(self, role: str) -> list[dict]:
        """Get messages filtered by role."""
        return [m for m in self._messages if m.get("role") == role]

    def prune_older_than(self, keep_last: int):
        """Keep only the last N messages regardless of strategy."""
        if len(self._messages) > keep_last:
            self._messages = self._messages[-keep_last:]

    def _est_tok(self) -> int:
        """Legacy token count method (for test compatibility)."""
        return self.token_count

    @property
    def token_count(self) -> int:
        """Estimate total tokens in memory."""
        return sum(estimate_tokens(str(m.get("content", ""))) for m in self._messages)

    @property
    def stats(self) -> dict:
        return {
            "strategy": self.strategy,
            "message_count": len(self._messages),
            "estimated_tokens": self.token_count,
            "roles": {r: len(self.get_by_role(r)) for r in ("system", "user", "assistant", "tool")},
        }

    def __len__(self):
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)


def create_memory(strategy: str = "buffer", **kwargs) -> ConversationMemory:
    """Factory function for creating conversation memory."""
    return ConversationMemory(strategy=strategy, **kwargs)
