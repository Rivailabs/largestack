"""Gemini function-calling translation: OpenAI-style tool messages -> Gemini contents,
and JSON-schema cleaning. (Live tool-calling is exercised via test_live_deepseek_e2e-style
keyed tests; these cover the pure translation logic offline.)
"""

from __future__ import annotations

from largestack._core.providers.google_prov import _clean_schema, _to_gemini_contents


def test_clean_schema_strips_unsupported_keys():
    s = {
        "type": "object",
        "properties": {"a": {"type": "integer", "title": "A", "default": 0}},
        "required": ["a"],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
    }
    out = _clean_schema(s)
    assert "additionalProperties" not in out and "$schema" not in out
    assert "title" not in out["properties"]["a"] and "default" not in out["properties"]["a"]
    assert out["properties"]["a"]["type"] == "integer"
    assert out["required"] == ["a"]


def test_tool_roundtrip_maps_id_to_name():
    msgs = [
        {"role": "user", "content": "add 1 and 2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "3"},
    ]
    contents, sys_i = _to_gemini_contents(msgs)
    assert contents[0]["role"] == "user"
    # assistant tool_call -> model functionCall
    fc = contents[1]["parts"][0]["functionCall"]
    assert fc["name"] == "add" and fc["args"] == {"a": 1, "b": 2}
    # tool result -> functionResponse with the NAME recovered from tool_call_id
    fr = contents[2]["parts"][0]["functionResponse"]
    assert fr["name"] == "add"
    assert fr["response"]["result"] == "3"


def test_system_message_becomes_instruction():
    contents, sys_i = _to_gemini_contents(
        [
            {"role": "system", "content": "Be terse."},
            {"role": "user", "content": "hi"},
        ]
    )
    assert sys_i == "Be terse."
    assert all(c["role"] != "system" for c in contents)
