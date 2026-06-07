"""Deep tests for core modules."""

import asyncio, sys, os

sys.path.insert(0, ".")


def test_config_defaults():
    from largestack._core.config import get_config

    cfg = get_config()
    assert cfg.max_turns > 0
    assert cfg.cost_budget > 0


def test_context_data():
    from largestack._core.context import AgentContext

    ctx = AgentContext()
    ctx.set("k", "v")
    assert ctx.get("k") == "v"


def test_context_missing():
    from largestack._core.context import AgentContext

    ctx = AgentContext()
    assert ctx.get("missing") is None


def test_feature_flags_toggle():
    from largestack._core.feature_flags import FeatureFlags

    ff = FeatureFlags()
    ff.set("test_flag", True)
    assert ff.is_enabled("test_flag")
    ff.set("test_flag", False)
    assert not ff.is_enabled("test_flag")


def test_feature_flags_default():
    from largestack._core.feature_flags import FeatureFlags

    ff = FeatureFlags()
    assert not ff.is_enabled("nonexistent")


def test_event_bus_emit():
    from largestack._core.events import EventBus

    bus = EventBus()
    received = []
    bus.on("test", lambda e: received.append(e))
    asyncio.run(bus.emit("test", {"x": 1}))
    assert len(received) == 1


def test_event_bus_wildcard():
    from largestack._core.events import EventBus

    bus = EventBus()
    all_events = []
    bus.on("*", lambda e: all_events.append(e))
    asyncio.run(bus.emit("a", {}))
    asyncio.run(bus.emit("b", {}))
    assert len(all_events) == 2


def test_registry_register():
    from largestack._core.registry import AgentRegistry

    reg = AgentRegistry()

    class MockAgent:
        name = "bot1"
        instructions = "test"
        tools = []
        llm = "test/model"

    reg.register(MockAgent(), capabilities=["search"])
    assert "bot1" in reg


def test_smart_router_select():
    from largestack._core.smart_router import SmartRouter

    router = SmartRouter()
    choice = router.select(tier="moderate")
    assert isinstance(choice, str)


def test_smart_router_update():
    from largestack._core.smart_router import SmartRouter

    router = SmartRouter()
    router.update("gpt-4o", success=True, latency_ms=100, cost=0.01)
    stats = router.get_stats()
    assert "gpt-4o" in stats


def test_semantic_cache_exact():
    from largestack._core.semantic_cache import SemanticCache

    cache = SemanticCache()
    msgs = [{"role": "user", "content": "What is Python?"}]
    cache.put_exact(msgs, "gpt-4o", {"content": "Python is a language"})
    result = cache.get_exact(msgs, "gpt-4o")
    assert result is not None


def test_tool_decorator_creates_schema():
    from largestack._core.tools import ToolRegistry

    reg = ToolRegistry()

    async def my_tool(query: str) -> str:
        """Search for things."""
        return f"result for {query}"

    reg.register(my_tool)
    schema = reg.get_schema("my_tool")
    assert schema is not None
    assert schema["name"] == "my_tool"


def test_tool_registry_list():
    from largestack._core.tools import ToolRegistry

    reg = ToolRegistry()

    async def tool_a(x: str) -> str:
        """Tool A."""
        return x

    async def tool_b(y: int) -> str:
        """Tool B."""
        return str(y)

    reg.register(tool_a)
    reg.register(tool_b)
    names = reg.list_names()
    assert "tool_a" in names
    assert "tool_b" in names


def test_gateway_creates():
    from largestack._core.gateway import LLMGateway

    gw = LLMGateway()
    assert gw is not None
