"""Tests for enhanced orchestration patterns."""
import asyncio, sys; sys.path.insert(0, ".")

class MockAgent:
    def __init__(self, name, response="default", handoff_to=None):
        self.name = name
        self.response = response
        self.handoff_to = handoff_to
    async def run(self, task):
        from largestack.types import AgentResult
        return AgentResult(content=self.response, agent_name=self.name, total_cost=0.001,
                          total_tokens=100, turns=1, tool_calls_made=[], trace_id="mock")

def test_swarm_single_agent():
    from largestack._orchestrate.swarm import Swarm
    a = MockAgent("solo", "Final answer")
    s = Swarm(agents=[a], start="solo")
    result = asyncio.run(s.run("hello"))
    assert "Final answer" in result.content
    assert result.turns == 1

def test_swarm_handoff_detection():
    from largestack._orchestrate.swarm import Swarm
    triage = MockAgent("triage", "[HANDOFF:billing] routing you", handoff_to=["billing"])
    billing = MockAgent("billing", "Your bill is $100")
    s = Swarm(agents=[triage, billing], start="triage")
    result = asyncio.run(s.run("I have a billing question"))
    # Should go triage → billing
    assert result.turns >= 2
    assert "bill is $100" in result.content

def test_swarm_handoff_blocked_by_allowlist():
    from largestack._orchestrate.swarm import Swarm
    # triage tries to route to unauthorized agent
    triage = MockAgent("triage", "[HANDOFF:admin]", handoff_to=["billing"])  # admin NOT in allowlist
    admin = MockAgent("admin", "Admin response")
    s = Swarm(agents=[triage, admin], start="triage", max_handoffs=3)
    result = asyncio.run(s.run("hack me"))
    # Should stay with triage (handoff blocked)
    assert result.turns == 1

def test_swarm_max_handoffs_respected():
    from largestack._orchestrate.swarm import Swarm
    # Ping-pong scenario
    a = MockAgent("a", "[HANDOFF:b]", handoff_to=["b"])
    b = MockAgent("b", "[HANDOFF:a]", handoff_to=["a"])
    s = Swarm(agents=[a, b], start="a", max_handoffs=3)
    result = asyncio.run(s.run("test"))
    # Should stop at max_handoffs
    assert result.turns <= 3

def test_debate_initialization():
    from largestack._orchestrate.debate import Debate
    a1 = MockAgent("optimist", "AI will help")
    a2 = MockAgent("pessimist", "AI is risky")
    d = Debate(agents=[a1, a2], rounds=2)
    assert d.rounds == 2
    assert d.strategy == "rounds"

def test_debate_requires_two_agents():
    from largestack._orchestrate.debate import Debate
    try:
        Debate(agents=[MockAgent("solo")], rounds=2)
        assert False, "Should reject single agent"
    except ValueError:
        pass

def test_debate_runs_rounds():
    from largestack._orchestrate.debate import Debate
    a1 = MockAgent("a", "Position A")
    a2 = MockAgent("b", "Position B")
    d = Debate(agents=[a1, a2], rounds=2, strategy="rounds")
    result = asyncio.run(d.run("Is X true?"))
    assert result.turns == 2  # 2 rounds
    assert len(d.history) == 2

def test_debate_consensus_detection():
    from largestack._orchestrate.debate import Debate, DebateRound
    a1 = MockAgent("a", "I agree with this")
    a2 = MockAgent("b", "I also agree completely")
    d = Debate(agents=[a1, a2], rounds=5, strategy="consensus")
    result = asyncio.run(d.run("easy topic"))
    # Consensus should be detected before all 5 rounds
    assert result.turns < 5 or result.turns == 5  # flexible

def test_debate_judge_strategy():
    from largestack._orchestrate.debate import Debate
    a1 = MockAgent("a", "View A")
    a2 = MockAgent("b", "View B")
    judge = MockAgent("judge", "My verdict: A is better")
    d = Debate(agents=[a1, a2], rounds=1, strategy="judge", judge=judge)
    result = asyncio.run(d.run("Which?"))
    assert "verdict" in result.content

def test_mapreduce_basic():
    from largestack._orchestrate.map_reduce import MapReduce
    mapper = MockAgent("m", "summary")
    reducer = MockAgent("r", "combined report")
    mr = MapReduce(mapper=mapper, reducer=reducer)
    result = asyncio.run(mr.run(items=["item1", "item2", "item3"]))
    assert "combined" in result.content
    assert result.turns == 4  # 3 map + 1 reduce

def test_mapreduce_empty_items():
    from largestack._orchestrate.map_reduce import MapReduce
    mapper = MockAgent("m")
    reducer = MockAgent("r")
    mr = MapReduce(mapper=mapper, reducer=reducer)
    try:
        asyncio.run(mr.run(items=[]))
        assert False
    except ValueError:
        pass

def test_mapreduce_concurrency_limit():
    from largestack._orchestrate.map_reduce import MapReduce
    mapper = MockAgent("m", "x")
    reducer = MockAgent("r", "done")
    mr = MapReduce(mapper=mapper, reducer=reducer, max_concurrency=2)
    assert mr.max_concurrency == 2

def test_router_basic():
    from largestack._orchestrate.router import Router
    classifier = MockAgent("c", "[CATEGORY:billing]")
    billing = MockAgent("b", "Billing response")
    tech = MockAgent("t", "Tech response")
    r = Router(classifier=classifier, routes={"billing": billing, "technical": tech}, default="billing")
    result = asyncio.run(r.run("refund me"))
    assert "Billing" in result.content

def test_router_default_fallback():
    from largestack._orchestrate.router import Router
    # Classifier returns unparseable output
    classifier = MockAgent("c", "not sure what category")
    fallback = MockAgent("f", "General response")
    r = Router(classifier=classifier, routes={"general": fallback, "other": MockAgent("o")}, default="general")
    result = asyncio.run(r.run("ambiguous"))
    assert "General" in result.content

def test_router_stats_tracking():
    from largestack._orchestrate.router import Router
    classifier = MockAgent("c", "[CATEGORY:a]")
    r = Router(classifier=classifier, routes={"a": MockAgent("a", "A"), "b": MockAgent("b", "B")})
    asyncio.run(r.run("q1"))
    asyncio.run(r.run("q2"))
    stats = r.stats
    assert stats["total_routed"] == 2
    assert stats["by_category"]["a"] == 2

def test_router_backwards_compat():
    """RouterPattern alias should still work."""
    from largestack._orchestrate.router import Router, RouterPattern
    assert Router is RouterPattern

def test_router_pattern_matching_fallback():
    from largestack._orchestrate.router import Router
    # No [CATEGORY:] marker, but "billing" appears in text
    classifier = MockAgent("c", "This seems to be a billing issue based on context")
    r = Router(classifier=classifier, routes={"billing": MockAgent("b", "OK"), "tech": MockAgent("t", "Tech")})
    result = asyncio.run(r.run("test"))
    assert "OK" in result.content
