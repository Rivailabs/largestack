import asyncio
from largestack._core.tools import tool, ToolRegistry


@tool
async def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


def test_decorator():
    assert greet._is_largestack_tool and greet._tool_schema["name"] == "greet"


def test_registry():
    r = ToolRegistry()
    r.register(greet)
    assert "greet" in r.list_names() and len(r.get_all_schemas()) == 1


def test_execution():
    assert asyncio.run(greet(name="World")) == "Hello, World!"
