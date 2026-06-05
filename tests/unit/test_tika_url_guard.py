"""The Tika server URL must reject non-HTTP(S) schemes (basic SSRF guard)."""
from __future__ import annotations

import pytest

from largestack._loaders.tika import _resolve_server_url


def test_rejects_non_http_scheme():
    for bad in ("file:///etc/passwd", "gopher://x", "ftp://host"):
        with pytest.raises(ValueError):
            _resolve_server_url(bad)


def test_accepts_http_and_https():
    assert _resolve_server_url("http://localhost:9998") == "http://localhost:9998"
    assert _resolve_server_url("https://tika.internal/") == "https://tika.internal"
