"""Tests for TestModel and FunctionModel."""

import asyncio, sys

sys.path.insert(0, ".")


def test_test_model_basic():
    from largestack.testing import TestModel

    m = TestModel(custom_output_text="canned response")
    result = asyncio.run(m.chat([{"role": "user", "content": "hi"}]))
    assert result["content"] == "canned response"


def test_test_model_calls_tools():
    from largestack.testing import TestModel

    m = TestModel(call_tools="all")
    tools = [{"name": "search", "parameters": {"properties": {"q": {"type": "string"}}}}]
    result = asyncio.run(m.chat([{"role": "user", "content": "search please"}], tools=tools))
    assert "search" in m.tool_calls_made


def test_function_model():
    from largestack.testing import FunctionModel

    def my_logic(messages, info):
        return {"content": f"echo: {messages[-1]['content']}"}

    m = FunctionModel(my_logic)
    result = asyncio.run(m.chat([{"role": "user", "content": "hello"}]))
    assert result["content"] == "echo: hello"


def test_function_model_async():
    from largestack.testing import FunctionModel

    async def my_logic(messages, info):
        return f"async: {len(messages)}"

    m = FunctionModel(my_logic)
    result = asyncio.run(m.chat([{"role": "user", "content": "x"}]))
    assert "async: 1" in result["content"]


def test_capture_run_messages():
    from largestack.testing import capture_run_messages

    with capture_run_messages() as captured:
        captured.messages.append({"role": "user", "content": "hi"})
        captured.messages.append({"role": "assistant", "content": "hello"})
    assert len(captured) == 2
    assert len(captured.user_messages) == 1
    assert len(captured.assistant_messages) == 1


def test_block_model_requests():
    from largestack.testing import block_model_requests, ALLOW_MODEL_REQUESTS
    import largestack.testing as t

    assert t.ALLOW_MODEL_REQUESTS is True
    with block_model_requests():
        assert t.ALLOW_MODEL_REQUESTS is False
    assert t.ALLOW_MODEL_REQUESTS is True
