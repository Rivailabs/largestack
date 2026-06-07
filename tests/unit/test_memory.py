"""Tests for all memory types."""

import asyncio
from largestack._memory.buffer import ConversationMemory
from largestack._memory.episodic import EpisodicMemory
from largestack._memory.observational import ObservationalMemory
from largestack._memory.procedural import ProceduralMemory
from largestack._memory.semantic import SemanticMemory
from largestack._memory.graph import GraphMemory
from largestack._memory.shared import SharedMemorySpace


def test_buffer():
    m = ConversationMemory()
    asyncio.run(m.add_message({"role": "user", "content": "hi"}))
    assert len(m) == 1


def test_sliding_window():
    m = ConversationMemory(strategy="sliding_window", max_messages=3)
    asyncio.run(m.add_messages([{"role": "user", "content": f"msg{i}"} for i in range(5)]))
    assert len(m) == 3


def test_token_limited():
    m = ConversationMemory(strategy="token_limited", max_tokens=50)
    asyncio.run(m.add_messages([{"role": "user", "content": "x" * 200} for _ in range(5)]))
    assert m._est_tok() <= 60  # Some tolerance


def test_episodic():
    m = EpisodicMemory()
    asyncio.run(m.add("User prefers Python", importance=8))
    asyncio.run(m.add("Meeting at 3pm", importance=5))
    results = asyncio.run(m.retrieve("Python"))
    assert len(results) > 0


def test_episodic_importance():
    m = EpisodicMemory()
    asyncio.run(m.add("Low priority note", importance=2))
    asyncio.run(m.add("CRITICAL: server down", importance=10))
    results = asyncio.run(m.retrieve("server status", k=1))
    assert "CRITICAL" in results[0]["content"]


def test_observational():
    m = ObservationalMemory()
    asyncio.run(
        m.observe(
            [
                {
                    "role": "user",
                    "content": "I always prefer concise answers. This is critical for my workflow.",
                }
            ]
        )
    )
    assert len(m) > 0
    ctx = m.get_context()
    assert len(ctx) > 0


def test_procedural():
    m = ProceduralMemory()
    asyncio.run(m.add_skill("greet", "result = 'Hello!'", "Greet someone"))
    skills = asyncio.run(m.search_skills("greet someone"))
    assert len(skills) > 0


def test_semantic():
    m = SemanticMemory()
    asyncio.run(m.add("python", "A high-level programming language"))
    r = asyncio.run(m.get("python"))
    assert r is not None and "programming" in r["description"]


def test_graph():
    g = GraphMemory()
    asyncio.run(g.add_entity("Python", "language", {"year": 1991}))
    asyncio.run(g.add_entity("AI", "field"))
    asyncio.run(g.add_relation("Python", "AI", "used_in"))
    rels = asyncio.run(g.get_relations("Python"))
    assert len(rels) == 1 and rels[0]["relation"] == "used_in"


def test_shared():
    s = SharedMemorySpace()
    asyncio.run(s.put("key", "value"))
    assert asyncio.run(s.get("key")) == "value"
