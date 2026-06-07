"""v0.7.0: Output parser tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from largestack._core.parsers import (
    OutputParseError,
    parse_bool,
    parse_code_block,
    parse_csv_line,
    parse_datetime,
    parse_enum,
    parse_json,
    parse_markdown_list,
    parse_xml,
    parse_yaml,
)


# -------------------- JSON --------------------


def test_parse_json_plain():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_strips_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_strips_plain_fences():
    assert parse_json('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_lenient_extraction():
    """When LLM adds preamble/postamble, extract the JSON anyway."""
    text = 'Here is the JSON:\n{"a": 1, "b": 2}\nHope that helps!'
    assert parse_json(text) == {"a": 1, "b": 2}


def test_parse_json_array():
    assert parse_json("[1, 2, 3]") == [1, 2, 3]


def test_parse_json_invalid():
    with pytest.raises(OutputParseError, match="invalid JSON"):
        parse_json("not json at all !@#$")


def test_parse_json_non_string():
    with pytest.raises(OutputParseError):
        parse_json(123)  # type: ignore


# -------------------- XML --------------------


def test_parse_xml_simple():
    result = parse_xml("<root><name>LARGESTACK</name></root>")
    assert "root" in result
    assert result["root"]["name"] == "LARGESTACK"


def test_parse_xml_with_attributes():
    result = parse_xml('<config version="1.0"><key>value</key></config>')
    assert result["config"]["@version"] == "1.0"
    assert result["config"]["key"] == "value"


def test_parse_xml_repeated_elements():
    result = parse_xml("<list><item>a</item><item>b</item></list>")
    assert isinstance(result["list"]["item"], list)
    assert result["list"]["item"] == ["a", "b"]


def test_parse_xml_strips_fences():
    result = parse_xml("```xml\n<root>x</root>\n```")
    assert result == {"root": "x"}


def test_parse_xml_invalid():
    with pytest.raises(OutputParseError):
        parse_xml("<unclosed>")


# -------------------- YAML --------------------


def test_parse_yaml_basic():
    pytest.importorskip("yaml")
    assert parse_yaml("name: LARGESTACK\nversion: 0.7") == {"name": "LARGESTACK", "version": 0.7}


def test_parse_yaml_with_fences():
    pytest.importorskip("yaml")
    assert parse_yaml("```yaml\nfoo: bar\n```") == {"foo": "bar"}


def test_parse_yaml_invalid():
    pytest.importorskip("yaml")
    with pytest.raises(OutputParseError):
        parse_yaml("[unclosed:")


# -------------------- Markdown list --------------------


def test_parse_md_list_dashes():
    text = "- apple\n- banana\n- cherry"
    assert parse_markdown_list(text) == ["apple", "banana", "cherry"]


def test_parse_md_list_asterisks():
    text = "* one\n* two"
    assert parse_markdown_list(text) == ["one", "two"]


def test_parse_md_list_numbered():
    text = "1. first\n2. second\n3. third"
    assert parse_markdown_list(text) == ["first", "second", "third"]


def test_parse_md_list_mixed_with_prose():
    text = "Here are some items:\n- one\nSome explanation.\n- two\n"
    assert parse_markdown_list(text) == ["one", "two"]


def test_parse_md_list_empty_when_no_items():
    assert parse_markdown_list("just prose, no list") == []


# -------------------- Code block --------------------


def test_parse_code_block_any_lang():
    text = "Here:\n```python\nprint(1)\n```\nDone."
    assert parse_code_block(text) == "print(1)"


def test_parse_code_block_specific_lang():
    text = "```python\npy code\n```\nNot this:\n```js\njs code\n```"
    assert parse_code_block(text, lang="python") == "py code"
    assert parse_code_block(text, lang="js") == "js code"


def test_parse_code_block_no_block():
    with pytest.raises(OutputParseError, match="no fenced code"):
        parse_code_block("just text")


# -------------------- CSV line --------------------


def test_parse_csv_line():
    assert parse_csv_line("a, b ,c") == ["a", "b", "c"]


def test_parse_csv_line_custom_sep():
    assert parse_csv_line("a|b|c", separator="|") == ["a", "b", "c"]


# -------------------- Datetime --------------------


def test_parse_datetime_iso():
    dt = parse_datetime("2026-05-02T14:30:00")
    assert dt == datetime(2026, 5, 2, 14, 30, 0)


def test_parse_datetime_date_only():
    dt = parse_datetime("2026-05-02")
    assert dt.year == 2026 and dt.month == 5 and dt.day == 2


def test_parse_datetime_indian_format():
    dt = parse_datetime("02/05/2026")
    assert dt.day == 2 and dt.month == 5


def test_parse_datetime_human_readable():
    dt = parse_datetime("May 2, 2026")
    assert dt.month == 5 and dt.day == 2


def test_parse_datetime_iso_with_z():
    dt = parse_datetime("2026-05-02T14:30:00Z")
    assert dt.year == 2026


def test_parse_datetime_invalid():
    with pytest.raises(OutputParseError, match="could not parse"):
        parse_datetime("yesterday at noon")


# -------------------- Boolean --------------------


def test_parse_bool_true_variants():
    for v in ("yes", "Yes", "YES", "true", "True", "y", "1", "ok", "agree", "correct"):
        assert parse_bool(v) is True, f"expected True for {v!r}"


def test_parse_bool_false_variants():
    for v in ("no", "No", "false", "False", "n", "0", "disagree", "incorrect"):
        assert parse_bool(v) is False, f"expected False for {v!r}"


def test_parse_bool_invalid():
    with pytest.raises(OutputParseError):
        parse_bool("maybe")


def test_parse_bool_strips_whitespace():
    assert parse_bool("  YES  ") is True


# -------------------- Enum --------------------


def test_parse_enum_match():
    assert parse_enum("approve", choices=["approve", "deny", "review"]) == "approve"


def test_parse_enum_case_insensitive_default():
    """Default behavior: case insensitive — returns canonical form."""
    assert parse_enum("APPROVE", choices=["approve", "deny"]) == "approve"


def test_parse_enum_case_sensitive():
    with pytest.raises(OutputParseError):
        parse_enum("APPROVE", choices=["approve", "deny"], case_sensitive=True)


def test_parse_enum_no_match():
    with pytest.raises(OutputParseError, match="not one of"):
        parse_enum("escalate", choices=["approve", "deny"])


def test_parse_enum_empty_choices():
    with pytest.raises(OutputParseError):
        parse_enum("x", choices=[])
