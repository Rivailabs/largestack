"""v0.8.0: Graph workflow DSL tests."""
from __future__ import annotations

import pytest

from largestack._workflow import Graph, START, END


# -------------------- Construction --------------------

def test_add_node_validates():
    g = Graph()
    with pytest.raises(ValueError, match="reserved"):
        g.add_node(START, lambda s: s)
    with pytest.raises(ValueError, match="reserved"):
        g.add_node(END, lambda s: s)
    with pytest.raises(ValueError, match="non-empty"):
        g.add_node("", lambda s: s)
    with pytest.raises(TypeError):
        g.add_node("x", "not_callable")


def test_add_node_rejects_duplicates():
    g = Graph()
    g.add_node("x", lambda s: s)
    with pytest.raises(ValueError, match="already exists"):
        g.add_node("x", lambda s: s)


def test_set_entry_validates():
    g = Graph()
    with pytest.raises(ValueError, match="not found"):
        g.set_entry("nonexistent")


def test_add_edge_validates():
    g = Graph().add_node("a", lambda s: s).add_node("b", lambda s: s)
    g.add_edge("a", "b")
    with pytest.raises(ValueError, match="already has an edge"):
        g.add_edge("a", "b")
    with pytest.raises(ValueError, match="not found"):
        g.add_edge("nonexistent", "b")


def test_compile_requires_entry():
    g = Graph().add_node("a", lambda s: s)
    g.add_edge("a", END)
    with pytest.raises(ValueError, match="entry node not set"):
        g.compile()


def test_compile_requires_outgoing_edges():
    g = Graph().add_node("a", lambda s: s).add_node("b", lambda s: s)
    g.set_entry("a").add_edge("a", "b")
    # b has no outgoing edge
    with pytest.raises(ValueError, match="no outgoing edge"):
        g.compile()


# -------------------- Sync nodes --------------------

@pytest.mark.asyncio
async def test_simple_linear_graph():
    """A → B → END"""
    g = Graph()
    g.add_node("a", lambda s: {"a_ran": True})
    g.add_node("b", lambda s: {"b_ran": True, "doubled_a": s.get("value", 0) * 2})
    g.set_entry("a")
    g.add_edge("a", "b")
    g.add_edge("b", END)

    result = await g.run({"value": 10})
    assert result.state["a_ran"] is True
    assert result.state["b_ran"] is True
    assert result.state["doubled_a"] == 20
    assert result.path == ["a", "b"]
    assert result.iterations == 2


@pytest.mark.asyncio
async def test_node_returning_none_keeps_state():
    """A node returning None means it mutated state in place (or no change)."""
    def noop(state):
        state["touched"] = True
        return None

    g = Graph()
    g.add_node("n", noop)
    g.set_entry("n")
    g.add_edge("n", END)
    result = await g.run({})
    assert result.state["touched"] is True


@pytest.mark.asyncio
async def test_node_returning_invalid_type_raises():
    g = Graph()
    g.add_node("bad", lambda s: 42)  # int, not dict
    g.set_entry("bad")
    g.add_edge("bad", END)
    with pytest.raises(TypeError, match="must return dict"):
        await g.run({})


# -------------------- Async nodes --------------------

@pytest.mark.asyncio
async def test_async_node_works():
    async def slow_node(state):
        return {"async_ran": True}
    g = Graph().add_node("s", slow_node)
    g.set_entry("s").add_edge("s", END)
    result = await g.run({})
    assert result.state["async_ran"] is True


# -------------------- Conditional edges --------------------

@pytest.mark.asyncio
async def test_conditional_edges_branch_a():
    g = Graph()
    g.add_node("classify", lambda s: {"intent": s["question"][:6]})
    g.add_node("answer_simple", lambda s: {"answer": "simple"})
    g.add_node("answer_complex", lambda s: {"answer": "complex"})

    g.set_entry("classify")
    g.add_conditional_edges(
        "classify",
        lambda s: "simple" if s["intent"] == "simple" else "complex",
        {"simple": "answer_simple", "complex": "answer_complex"},
    )
    g.add_edge("answer_simple", END)
    g.add_edge("answer_complex", END)

    result = await g.run({"question": "simple stuff"})
    assert result.state["answer"] == "simple"
    assert "answer_simple" in result.path


@pytest.mark.asyncio
async def test_conditional_edges_branch_b():
    g = Graph()
    g.add_node("classify", lambda s: {"intent": s["question"][:5]})
    g.add_node("answer_simple", lambda s: {"answer": "simple"})
    g.add_node("answer_complex", lambda s: {"answer": "complex"})

    g.set_entry("classify")
    g.add_conditional_edges(
        "classify",
        lambda s: "complex" if s["intent"] == "compl" else "simple",
        {"simple": "answer_simple", "complex": "answer_complex"},
    )
    g.add_edge("answer_simple", END)
    g.add_edge("answer_complex", END)

    result = await g.run({"question": "complex query"})
    assert result.state["answer"] == "complex"


@pytest.mark.asyncio
async def test_async_router():
    """Router function may be async."""
    async def router(state):
        return "yes" if state["x"] > 0 else "no"

    g = Graph()
    g.add_node("check", lambda s: {})
    g.add_node("pos", lambda s: {"sign": "positive"})
    g.add_node("neg", lambda s: {"sign": "negative"})
    g.set_entry("check")
    g.add_conditional_edges("check", router, {"yes": "pos", "no": "neg"})
    g.add_edge("pos", END)
    g.add_edge("neg", END)

    result = await g.run({"x": 5})
    assert result.state["sign"] == "positive"


@pytest.mark.asyncio
async def test_router_invalid_choice_raises():
    g = Graph()
    g.add_node("c", lambda s: {})
    g.add_node("a", lambda s: {})
    g.set_entry("c")
    g.add_conditional_edges("c", lambda s: "wrong_branch", {"a": "a"})
    g.add_edge("a", END)
    with pytest.raises(ValueError, match="router for 'c' returned 'wrong_branch'"):
        await g.run({})


def test_cant_have_both_edge_kinds():
    g = Graph().add_node("a", lambda s: {}).add_node("b", lambda s: {})
    g.add_edge("a", "b")
    with pytest.raises(ValueError, match="already has an edge"):
        g.add_conditional_edges("a", lambda s: "b", {"b": "b"})


# -------------------- Cycle protection --------------------

@pytest.mark.asyncio
async def test_max_iterations_prevents_runaway():
    """A cycle must terminate at max_iterations."""
    g = Graph(max_iterations=5)
    g.add_node("a", lambda s: {"count": s.get("count", 0) + 1})
    g.add_node("b", lambda s: {"count": s.get("count", 0) + 1})
    g.set_entry("a")
    g.add_edge("a", "b")
    g.add_edge("b", "a")  # cycle
    result = await g.run({"count": 0})
    assert result.truncated is True
    assert result.iterations == 6  # 5 + 1 over the cap


# -------------------- Subgraphs --------------------

@pytest.mark.asyncio
async def test_subgraph_composition():
    """A graph can be used as a node in another graph."""
    sub = Graph()
    sub.add_node("inner_a", lambda s: {"inner_a_ran": True})
    sub.add_node("inner_b", lambda s: {"inner_b_ran": True})
    sub.set_entry("inner_a")
    sub.add_edge("inner_a", "inner_b")
    sub.add_edge("inner_b", END)

    main = Graph()
    main.add_node("preprocess", lambda s: {"preprocessed": True})
    main.add_node("subroutine", sub.as_node())
    main.add_node("postprocess", lambda s: {"postprocessed": True})
    main.set_entry("preprocess")
    main.add_edge("preprocess", "subroutine")
    main.add_edge("subroutine", "postprocess")
    main.add_edge("postprocess", END)

    result = await main.run({})
    assert result.state["preprocessed"] is True
    assert result.state["inner_a_ran"] is True
    assert result.state["inner_b_ran"] is True
    assert result.state["postprocessed"] is True


# -------------------- Mermaid output --------------------

def test_mermaid_output_includes_nodes_and_edges():
    g = Graph()
    g.add_node("classify", lambda s: {})
    g.add_node("answer", lambda s: {})
    g.set_entry("classify")
    g.add_conditional_edges(
        "classify",
        lambda s: "yes",
        {"yes": "answer", "no": END},
    )
    g.add_edge("answer", END)

    out = g.to_mermaid()
    assert "graph TD" in out
    assert "classify" in out
    assert "answer" in out
    assert "START" in out


# -------------------- Misc --------------------

def test_repr_shows_counts():
    g = Graph()
    g.add_node("a", lambda s: {})
    assert "Graph(nodes=1" in repr(g)


def test_max_iterations_validates():
    with pytest.raises(ValueError):
        Graph(max_iterations=0)


def test_nodes_method_returns_list():
    g = Graph().add_node("a", lambda s: {}).add_node("b", lambda s: {})
    assert set(g.nodes()) == {"a", "b"}
