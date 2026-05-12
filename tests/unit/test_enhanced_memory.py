"""Tests for enhanced memory modules."""
import asyncio, sys; sys.path.insert(0, ".")

def test_buffer_strategies():
    from largestack._memory.buffer import ConversationMemory
    # Test all strategies
    for s in ("buffer", "sliding", "sliding_window", "token_limited"):
        m = ConversationMemory(strategy=s, max_messages=5, max_tokens=100)
        asyncio.run(m.add_message({"role": "user", "content": "hello"}))
        assert len(m) == 1

def test_buffer_system_preservation():
    from largestack._memory.buffer import ConversationMemory
    m = ConversationMemory(strategy="sliding", max_messages=3, include_system=True)
    asyncio.run(m.add_message({"role": "system", "content": "You are helpful"}))
    for i in range(10):
        asyncio.run(m.add_message({"role": "user", "content": f"msg {i}"}))
    msgs = m.get_messages()
    # System message should be preserved
    assert msgs[0]["role"] == "system"

def test_buffer_token_limited():
    from largestack._memory.buffer import ConversationMemory
    m = ConversationMemory(strategy="token_limited", max_tokens=100)
    for i in range(20):
        asyncio.run(m.add_message({"role": "user", "content": "x" * 100}))  # ~25 tokens each
    assert m.token_count <= 125  # Some tolerance

def test_buffer_by_role():
    from largestack._memory.buffer import ConversationMemory
    m = ConversationMemory()
    asyncio.run(m.add_message({"role": "user", "content": "A"}))
    asyncio.run(m.add_message({"role": "assistant", "content": "B"}))
    asyncio.run(m.add_message({"role": "user", "content": "C"}))
    assert len(m.get_by_role("user")) == 2
    assert len(m.get_by_role("assistant")) == 1

def test_buffer_stats():
    from largestack._memory.buffer import ConversationMemory
    m = ConversationMemory(strategy="buffer")
    asyncio.run(m.add_message({"role": "user", "content": "test"}))
    s = m.stats
    assert s["strategy"] == "buffer"
    assert s["message_count"] == 1
    assert "roles" in s

def test_semantic_similarity():
    from largestack._memory.semantic import SemanticMemory, cosine_similarity
    # cosine similarity of identical vectors = 1
    assert abs(cosine_similarity([1,0,0], [1,0,0]) - 1.0) < 0.01
    # orthogonal = 0
    assert abs(cosine_similarity([1,0,0], [0,1,0])) < 0.01

def test_semantic_add_search():
    from largestack._memory.semantic import SemanticMemory
    m = SemanticMemory()
    asyncio.run(m.add("Python is a programming language"))
    asyncio.run(m.add("Cats are cute animals"))
    results = asyncio.run(m.search("what is python", k=1))
    assert len(results) == 1
    # Python fact should rank higher
    assert "python" in results[0]["content"].lower() or "programming" in results[0]["content"].lower()

def test_semantic_dedup():
    from largestack._memory.semantic import SemanticMemory
    m = SemanticMemory()
    asyncio.run(m.add("same content"))
    asyncio.run(m.add("same content"))
    assert len(m) == 1

def test_semantic_legacy_signature():
    from largestack._memory.semantic import SemanticMemory
    m = SemanticMemory()
    asyncio.run(m.add("python", "A programming language"))
    r = asyncio.run(m.get("python"))
    assert r is not None
    assert "programming" in r["description"]

def test_semantic_stats():
    from largestack._memory.semantic import SemanticMemory
    m = SemanticMemory()
    asyncio.run(m.add("fact 1"))
    asyncio.run(m.add("fact 2"))
    s = m.stats
    assert s["entry_count"] == 2

def test_procedural_skill_tracking():
    from largestack._memory.procedural import ProceduralMemory
    m = ProceduralMemory()
    asyncio.run(m.add_skill("greet", "say hello", "Greet someone"))
    m.record_usage("greet", success=True)
    m.record_usage("greet", success=True)
    m.record_usage("greet", success=False)
    skill = m.get_skill("greet")
    assert skill.usage_count == 3
    assert skill.success_count == 2
    assert abs(skill.success_rate - 0.667) < 0.01

def test_procedural_top_skills():
    from largestack._memory.procedural import ProceduralMemory
    m = ProceduralMemory()
    asyncio.run(m.add_skill("a", "proc_a", "Skill A"))
    asyncio.run(m.add_skill("b", "proc_b", "Skill B"))
    m.record_usage("a"); m.record_usage("a"); m.record_usage("a")
    m.record_usage("b")
    top = m.top_skills(k=2)
    assert top[0].name == "a"

def test_procedural_persistence():
    import tempfile, os
    from largestack._memory.procedural import ProceduralMemory
    path = os.path.join(tempfile.mkdtemp(), "skills.json")
    
    m1 = ProceduralMemory(storage_path=path, auto_save=True)
    asyncio.run(m1.add_skill("code_review", "review code", "Review code quality"))
    m1.record_usage("code_review")
    
    # Reload
    m2 = ProceduralMemory(storage_path=path, auto_save=False)
    skill = m2.get_skill("code_review")
    assert skill is not None
    assert skill.usage_count == 1

def test_graph_bidirectional():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    asyncio.run(g.add_entity("A"))
    asyncio.run(g.add_entity("B"))
    asyncio.run(g.add_relation("A", "B", "knows"))
    # Get outbound from A
    out = asyncio.run(g.get_relations("A", direction="out"))
    assert len(out) == 1
    # Get inbound to B
    inb = asyncio.run(g.get_relations("B", direction="in"))
    assert len(inb) == 1

def test_graph_path_finding():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    # A → B → C → D
    for name in ["A", "B", "C", "D"]:
        asyncio.run(g.add_entity(name))
    asyncio.run(g.add_relation("A", "B", "knows"))
    asyncio.run(g.add_relation("B", "C", "knows"))
    asyncio.run(g.add_relation("C", "D", "knows"))
    
    paths = asyncio.run(g.find_paths("A", "D"))
    assert len(paths) >= 1
    assert paths[0] == ["A", "B", "C", "D"]

def test_graph_shortest_path():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    for name in ["A", "B", "C", "D"]:
        asyncio.run(g.add_entity(name))
    asyncio.run(g.add_relation("A", "B", "knows", weight=1.0))
    asyncio.run(g.add_relation("A", "C", "knows", weight=3.0))
    asyncio.run(g.add_relation("B", "D", "knows", weight=1.0))
    asyncio.run(g.add_relation("C", "D", "knows", weight=1.0))
    # A → B → D (cost 2) shorter than A → C → D (cost 4)
    path = asyncio.run(g.shortest_path("A", "D"))
    assert path == ["A", "B", "D"]

def test_graph_subgraph():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    for name in ["A", "B", "C", "D", "E"]:
        asyncio.run(g.add_entity(name))
    asyncio.run(g.add_relation("A", "B", "knows"))
    asyncio.run(g.add_relation("B", "C", "knows"))
    # D and E are disconnected from A
    sub = asyncio.run(g.subgraph("A", depth=1))
    assert "A" in sub["entities"]
    assert "B" in sub["entities"]
    assert "D" not in sub["entities"]

def test_graph_stats():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    asyncio.run(g.add_entity("Alice", "person"))
    asyncio.run(g.add_entity("Bob", "person"))
    asyncio.run(g.add_entity("Acme", "company"))
    asyncio.run(g.add_relation("Alice", "Acme", "works_at"))
    s = g.stats
    assert s["entity_count"] == 3
    assert s["entity_types"]["person"] == 2
    assert s["entity_types"]["company"] == 1

def test_graph_search_entities():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    asyncio.run(g.add_entity("Alice Smith", "person", {"job": "engineer"}))
    asyncio.run(g.add_entity("Bob Jones", "person", {"job": "designer"}))
    results = asyncio.run(g.search_entities("engineer"))
    assert len(results) >= 1
    assert results[0]["name"] == "Alice Smith"

def test_graph_merge():
    from largestack._memory.graph import GraphMemory
    g = GraphMemory()
    asyncio.run(g.add_entity("A"))
    asyncio.run(g.add_entity("A_dup"))
    asyncio.run(g.add_entity("B"))
    asyncio.run(g.add_relation("A_dup", "B", "knows"))
    asyncio.run(g.merge_entities(keep="A", remove="A_dup"))
    assert "A_dup" not in g._entities
    # Relation should now come from A
    rels = asyncio.run(g.get_relations("A"))
    assert any(r["to"] == "B" for r in rels)
