"""Output parsers — convert LLM string output into typed Python values (v0.7.0).

LangChain's output parser collection is genuinely useful: instead of
asking the LLM for a JSON object then parsing it manually with regex,
you use a typed parser that validates and converts.

Parsers included:
- ``parse_json(text)`` — strict JSON (handles markdown fences)
- ``parse_xml(text)`` — XML to nested dict
- ``parse_yaml(text)`` — YAML to dict (requires pyyaml)
- ``parse_markdown_list(text)`` — bullets/numbers → list[str]
- ``parse_code_block(text, lang=None)`` — extract fenced code
- ``parse_csv_line(text)`` — comma-separated → list[str]
- ``parse_datetime(text)`` — natural language date → datetime
- ``parse_bool(text)`` — yes/no/true/false → bool
- ``parse_enum(text, choices)`` — match to one of allowed values

All parsers raise ``OutputParseError`` on failure, with a descriptive
message that can be fed back to the LLM for retry.
"""
from __future__ import annotations
import json
import logging
import re
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from datetime import datetime
from typing import Any

log = logging.getLogger("largestack.parsers")


class OutputParseError(Exception):
    """Raised when an output parser cannot produce a typed value."""


# -------------------- JSON --------------------

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)\n?```", re.DOTALL)


def parse_json(text: str) -> Any:
    """Parse text as JSON. Strips markdown fences if present.

    Raises OutputParseError with a clear message on failure.
    """
    if not isinstance(text, str):
        raise OutputParseError(f"expected string, got {type(text).__name__}")
    s = text.strip()

    # Strip ```json ... ``` fences
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    # Try direct parse
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        # Try to find the first { or [ and last } or ] (lenient extraction)
        start = -1
        for i, ch in enumerate(s):
            if ch in "{[":
                start = i
                break
        end = -1
        for i in range(len(s) - 1, -1, -1):
            if s[i] in "}]":
                end = i
                break
        if start >= 0 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise OutputParseError(
            f"invalid JSON: {e.msg} at line {e.lineno} col {e.colno}"
        ) from e


# -------------------- XML --------------------

def parse_xml(text: str) -> dict:
    """Parse XML to a nested dict.

    Element attributes are merged as keys with @ prefix.
    Element text becomes the value (or "#text" if there are children).
    """
    s = text.strip()
    # Strip ```xml fences
    m = re.search(r"```(?:xml|XML)?\s*\n?(.*?)\n?```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        root = ET.fromstring(s)
    except (ET.ParseError, DefusedXmlException) as e:
        raise OutputParseError(f"invalid XML: {e}") from e
    return {root.tag: _xml_to_dict(root)}


def _xml_to_dict(elem: ET.Element) -> Any:
    children = list(elem)
    if not children and not elem.attrib:
        return (elem.text or "").strip()
    d: dict[str, Any] = {}
    for k, v in elem.attrib.items():
        d[f"@{k}"] = v
    if (elem.text or "").strip():
        d["#text"] = (elem.text or "").strip()
    for child in children:
        sub = _xml_to_dict(child)
        if child.tag in d:
            existing = d[child.tag]
            if isinstance(existing, list):
                existing.append(sub)
            else:
                d[child.tag] = [existing, sub]
        else:
            d[child.tag] = sub
    return d


# -------------------- YAML --------------------

def parse_yaml(text: str) -> Any:
    """Parse text as YAML. Strips markdown fences."""
    try:
        import yaml  # type: ignore
    except ImportError:
        raise OutputParseError("YAML parsing needs: pip install pyyaml")
    s = text.strip()
    m = re.search(r"```(?:yaml|YAML|yml)?\s*\n?(.*?)\n?```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        return yaml.safe_load(s)
    except yaml.YAMLError as e:
        raise OutputParseError(f"invalid YAML: {e}") from e


# -------------------- Markdown list --------------------

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")


def parse_markdown_list(text: str) -> list[str]:
    """Extract bullet points or numbered list items as a list of strings.

    Supports ``-``, ``*``, ``+`` bullets and ``1.``, ``2.`` numbered items.
    Returns empty list if no list found (raises if input is not a string).
    """
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    items = []
    for line in text.splitlines():
        m = _LIST_ITEM_RE.match(line)
        if m:
            items.append(m.group(1).strip())
    return items


# -------------------- Code block --------------------

def parse_code_block(text: str, lang: str | None = None) -> str:
    """Extract code from a fenced ``\\`\\`\\``` block.

    Args:
        text: full LLM output
        lang: if specified, only match blocks with this language tag
            (e.g. ``"python"``). If None, match any block.

    Returns the code content (without fences). Raises if not found.
    """
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    if lang:
        pattern = rf"```{re.escape(lang)}\s*\n(.*?)\n```"
    else:
        pattern = r"```(?:[a-zA-Z0-9_+-]*)?\s*\n(.*?)\n```"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        raise OutputParseError(
            f"no fenced code block found{f' (lang={lang!r})' if lang else ''}"
        )
    return m.group(1)


# -------------------- CSV line --------------------

def parse_csv_line(text: str, separator: str = ",") -> list[str]:
    """Split a single line into fields. Trims whitespace."""
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    return [s.strip() for s in text.split(separator)]


# -------------------- Datetime --------------------

_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%d %b %Y",
]


def parse_datetime(text: str) -> datetime:
    """Parse a date string against multiple formats. Raises if all fail."""
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    s = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Try ISO format via fromisoformat as last resort (handles many cases)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    raise OutputParseError(
        f"could not parse {s!r} as datetime; "
        f"expected one of: {', '.join(_DATE_FORMATS[:5])} or ISO 8601"
    )


# -------------------- Boolean --------------------

_TRUE_VALUES = {"true", "yes", "y", "1", "on", "enable", "enabled", "agree", "ok", "correct"}
_FALSE_VALUES = {"false", "no", "n", "0", "off", "disable", "disabled", "disagree", "incorrect"}


def parse_bool(text: str) -> bool:
    """Parse natural-language boolean. Case-insensitive.

    True: yes, true, y, 1, on, enable, enabled, agree, ok, correct
    False: no, false, n, 0, off, disable, disabled, disagree, incorrect
    """
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    s = text.strip().lower()
    if s in _TRUE_VALUES:
        return True
    if s in _FALSE_VALUES:
        return False
    raise OutputParseError(
        f"could not parse {text!r} as boolean. "
        f"Expected one of: {sorted(_TRUE_VALUES | _FALSE_VALUES)}"
    )


# -------------------- Enum --------------------

def parse_enum(text: str, choices: list[str], *, case_sensitive: bool = False) -> str:
    """Match text to one of the allowed choices.

    Args:
        text: LLM output
        choices: allowed values
        case_sensitive: if False (default), match case-insensitively

    Returns the canonical (original-case) choice that matched. Raises
    if no match.
    """
    if not isinstance(text, str):
        raise OutputParseError("expected string input")
    if not choices:
        raise OutputParseError("choices must be non-empty")
    s = text.strip()
    if not case_sensitive:
        s_lower = s.lower()
        for c in choices:
            if c.lower() == s_lower:
                return c  # return original case
    else:
        if s in choices:
            return s
    raise OutputParseError(f"{text!r} is not one of {choices}")
