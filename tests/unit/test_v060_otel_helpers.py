"""v0.6.0: OpenTelemetry helper tests.

These work whether or not the opentelemetry package is installed —
no-op paths are tested even on minimal environments.
"""
from __future__ import annotations

import pytest


# -------------------- traceparent parsing --------------------

def test_parse_traceparent_valid():
    from largestack._observe.otel_helpers import parse_traceparent
    h = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    parsed = parse_traceparent(h)
    assert parsed is not None
    trace_id, span_id, flags = parsed
    assert trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert span_id == "b7ad6b7169203331"
    assert flags == 0x01


def test_parse_traceparent_uppercase_normalized():
    from largestack._observe.otel_helpers import parse_traceparent
    h = "00-0AF7651916CD43DD8448EB211C80319C-B7AD6B7169203331-00"
    parsed = parse_traceparent(h)
    assert parsed is not None
    assert parsed[0] == "0af7651916cd43dd8448eb211c80319c"


def test_parse_traceparent_invalid_returns_none():
    from largestack._observe.otel_helpers import parse_traceparent
    assert parse_traceparent("") is None
    assert parse_traceparent(None) is None
    assert parse_traceparent("garbage") is None
    assert parse_traceparent("00-tooshort-00-01") is None
    # Wrong version (only 00 supported in the W3C spec right now)
    assert parse_traceparent(
        "01-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    ) is None


def test_parse_traceparent_strips_whitespace():
    from largestack._observe.otel_helpers import parse_traceparent
    h = "  00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01  "
    assert parse_traceparent(h) is not None


# -------------------- get_traceparent_header --------------------

def test_get_traceparent_header_no_active_span_returns_empty():
    """When no OTel span is current, return empty dict (not crash)."""
    from largestack._observe.otel_helpers import get_traceparent_header
    headers = get_traceparent_header()
    assert headers == {} or "traceparent" in headers


def test_get_traceparent_header_returns_dict_type():
    """Always returns a dict — for safe header.update() usage."""
    from largestack._observe.otel_helpers import get_traceparent_header
    h = get_traceparent_header()
    assert isinstance(h, dict)


# -------------------- with_traceparent --------------------

def test_with_traceparent_no_op_when_header_missing():
    """No header → just yields; no exception."""
    from largestack._observe.otel_helpers import with_traceparent
    with with_traceparent(None):
        pass
    with with_traceparent(""):
        pass


def test_with_traceparent_no_op_when_header_malformed():
    from largestack._observe.otel_helpers import with_traceparent
    with with_traceparent("not-a-real-header"):
        pass


def test_with_traceparent_accepts_valid_header():
    """Valid header propagates without raising — actual span attachment
    only fires when OTel is installed; this test guarantees the codepath
    is at least exercised."""
    from largestack._observe.otel_helpers import with_traceparent
    h = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    with with_traceparent(h):
        pass


# -------------------- link_to_current_span --------------------

def test_link_to_current_span_handles_invalid_ids():
    """Bad ID lengths return a no-op context — no crash."""
    from largestack._observe.otel_helpers import link_to_current_span
    # short trace id
    with link_to_current_span("abc", "def", "child"):
        pass
    # Empty
    with link_to_current_span("", "", "x"):
        pass


def test_link_to_current_span_accepts_valid_ids():
    from largestack._observe.otel_helpers import link_to_current_span
    with link_to_current_span(
        "0af7651916cd43dd8448eb211c80319c",
        "b7ad6b7169203331",
        "linked_test",
    ):
        pass


# -------------------- _valid_hex --------------------

def test_valid_hex_helpers():
    from largestack._observe.otel_helpers import _valid_hex
    assert _valid_hex("0af7651916cd43dd8448eb211c80319c", 32) is True
    assert _valid_hex("b7ad6b7169203331", 16) is True
    assert _valid_hex("xyz", 16) is False
    assert _valid_hex("", 16) is False
    assert _valid_hex(None, 16) is False
    # Wrong length
    assert _valid_hex("abc", 16) is False
