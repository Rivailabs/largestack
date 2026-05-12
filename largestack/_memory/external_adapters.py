"""Memory adapters: Mem0 + Zep Graphiti.

Usage:
    from largestack._memory.mem0_adapter import Mem0Memory
    from largestack._memory.zep_adapter import ZepMemory
    
    mem = Mem0Memory(api_key="...")
    await mem.add("User likes coffee", user_id="u1")
    results = await mem.search("preferences", user_id="u1")
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("largestack.memory.external")


@dataclass
class MemoryResult:
    content: str
    score: float = 0.0
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Mem0Memory:
    """Mem0 cloud or self-hosted memory."""
    
    def __init__(self, api_key: str | None = None, user_id: str = "default"):
        self.api_key = api_key or os.environ.get("MEM0_API_KEY") or os.environ.get("LARGESTACK_MEM0_API_KEY")
        self.default_user_id = user_id
        self._available = False
        self._client = None
        try:
            from mem0 import MemoryClient
            self._client = MemoryClient(api_key=self.api_key) if self.api_key else None
            self._available = bool(self.api_key)
        except ImportError:
            log.warning("mem0ai not installed. pip install mem0ai")
    
    async def add(self, content: str, user_id: str | None = None, metadata: dict | None = None) -> bool:
        if not self._available:
            return False
        try:
            self._client.add(content, user_id=user_id or self.default_user_id, metadata=metadata or {})
            return True
        except Exception as e:
            log.error(f"Mem0 add failed: {e}")
            return False
    
    async def search(self, query: str, user_id: str | None = None, limit: int = 5) -> list[MemoryResult]:
        if not self._available:
            return []
        try:
            results = self._client.search(query, user_id=user_id or self.default_user_id, limit=limit)
            return [MemoryResult(content=r.get("memory", ""), score=r.get("score", 0.0),
                                  metadata=r.get("metadata", {}))
                    for r in results]
        except Exception as e:
            log.error(f"Mem0 search failed: {e}")
            return []


class ZepMemory:
    """Zep temporal knowledge graph memory."""
    
    def __init__(self, api_key: str | None = None, base_url: str = "https://api.getzep.com"):
        self.api_key = api_key or os.environ.get("ZEP_API_KEY") or os.environ.get("LARGESTACK_ZEP_API_KEY")
        self.base_url = base_url
        self._available = False
        self._client = None
        try:
            from zep_cloud.client import AsyncZep
            self._client = AsyncZep(api_key=self.api_key) if self.api_key else None
            self._available = bool(self.api_key)
        except ImportError:
            log.warning("zep-cloud not installed. pip install zep-cloud")
    
    async def add_message(self, session_id: str, role: str, content: str) -> bool:
        if not self._available:
            return False
        try:
            await self._client.memory.add(session_id=session_id, messages=[{"role": role, "content": content}])
            return True
        except Exception as e:
            log.error(f"Zep add failed: {e}")
            return False
    
    async def search(self, query: str, user_id: str | None = None, limit: int = 5) -> list[MemoryResult]:
        if not self._available:
            return []
        try:
            results = await self._client.memory.search(text=query, user_id=user_id, limit=limit)
            return [MemoryResult(content=r.message.content if r.message else "",
                                  score=r.score or 0.0,
                                  metadata={"role": r.message.role if r.message else ""})
                    for r in results.results]
        except Exception as e:
            log.error(f"Zep search failed: {e}")
            return []
