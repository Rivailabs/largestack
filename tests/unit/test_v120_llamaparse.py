"""v0.12.0: Tests for LlamaParse loader (multi-modal RAG integration)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_module_imports_cleanly():
    """The module should import even without llama_parse installed."""
    from largestack._loaders import llamaparse
    assert hasattr(llamaparse, "load_with_llamaparse")
    assert hasattr(llamaparse, "load_with_llamaparse_sync")


def test_llama_parse_available_returns_bool():
    from largestack._loaders.llamaparse import _llama_parse_available
    # Returns False on this clean machine — that's the expected baseline
    assert isinstance(_llama_parse_available(), bool)


@pytest.mark.asyncio
async def test_load_raises_on_missing_file(tmp_path):
    from largestack._loaders.llamaparse import load_with_llamaparse
    with pytest.raises(FileNotFoundError):
        await load_with_llamaparse(tmp_path / "no.pdf")


@pytest.mark.asyncio
async def test_load_falls_back_when_llama_parse_missing(tmp_path):
    """If llama_parse isn't available, fallback to load_pdf (or text)."""
    from largestack._loaders import llamaparse

    # Create a fake text file (PDF fallback would need real PDF bytes)
    f = tmp_path / "doc.txt"
    f.write_text("Hello multi-modal world")

    # Force llama_parse to appear unavailable
    with patch.object(
        llamaparse, "_llama_parse_available", return_value=False,
    ):
        docs = await llamaparse.load_with_llamaparse(
            f, fallback_on_error=True,
        )

    assert len(docs) >= 1
    # Fallback marker should be set
    assert docs[0]["metadata"]["parser"] == "fallback"


@pytest.mark.asyncio
async def test_load_raises_when_unavailable_and_no_fallback(tmp_path):
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.txt"
    f.write_text("test")

    with patch.object(
        llamaparse, "_llama_parse_available", return_value=False,
    ):
        with pytest.raises(ImportError, match="llama_parse"):
            await llamaparse.load_with_llamaparse(
                f, fallback_on_error=False,
            )


@pytest.mark.asyncio
async def test_load_raises_when_no_api_key(tmp_path, monkeypatch):
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    # Pretend llama_parse is available, but no API key
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ):
        with pytest.raises(ValueError, match="api_key"):
            await llamaparse.load_with_llamaparse(
                f, api_key=None, fallback_on_error=False,
            )


@pytest.mark.asyncio
async def test_load_falls_back_on_no_api_key(tmp_path, monkeypatch):
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.txt"
    f.write_text("hi")

    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ):
        docs = await llamaparse.load_with_llamaparse(
            f, api_key=None, fallback_on_error=True,
        )
    assert len(docs) >= 1
    assert docs[0]["metadata"]["parser"] == "fallback"


@pytest.mark.asyncio
async def test_load_uses_env_var_for_api_key(tmp_path, monkeypatch):
    """If LLAMA_CLOUD_API_KEY env var is set, it should be used."""
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 fake content")

    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "llx-test-key")

    fake_doc = SimpleNamespace(
        text="parsed markdown content",
        metadata={"page": 1},
    )
    fake_parser = MagicMock()
    fake_parser.aload_data = AsyncMock(return_value=[fake_doc])

    fake_LlamaParse = MagicMock(return_value=fake_parser)

    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ), patch.object(
        llamaparse, "_import_llama_parse", return_value=fake_LlamaParse,
    ):
        docs = await llamaparse.load_with_llamaparse(f)

    # Verify the parser was called with the env-var API key
    fake_LlamaParse.assert_called_once()
    kwargs = fake_LlamaParse.call_args.kwargs
    assert kwargs["api_key"] == "llx-test-key"


@pytest.mark.asyncio
async def test_load_returns_normalized_docs(tmp_path):
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF fake")

    fake_doc1 = SimpleNamespace(
        text="page 1 content",
        metadata={"page": 1, "title": "doc"},
    )
    fake_doc2 = SimpleNamespace(
        text="page 2 with table",
        metadata={"page": 2},
    )
    fake_parser = MagicMock()
    fake_parser.aload_data = AsyncMock(
        return_value=[fake_doc1, fake_doc2],
    )

    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ), patch.object(
        llamaparse, "_import_llama_parse",
        return_value=MagicMock(return_value=fake_parser),
    ):
        docs = await llamaparse.load_with_llamaparse(
            f, api_key="llx-test",
        )

    assert len(docs) == 2
    assert docs[0]["content"] == "page 1 content"
    assert docs[0]["metadata"]["page"] == 1
    # source + parser tags injected
    assert docs[0]["metadata"]["parser"] == "llamaparse"
    assert "doc.pdf" in docs[0]["metadata"]["source"]


@pytest.mark.asyncio
async def test_load_falls_back_when_parser_raises(tmp_path):
    """If LlamaParse itself raises during parsing, fallback path engages."""
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.txt"
    f.write_text("hello")

    fake_parser = MagicMock()
    fake_parser.aload_data = AsyncMock(side_effect=RuntimeError("API down"))

    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ), patch.object(
        llamaparse, "_import_llama_parse",
        return_value=MagicMock(return_value=fake_parser),
    ):
        docs = await llamaparse.load_with_llamaparse(
            f, api_key="x", fallback_on_error=True,
        )
    assert len(docs) >= 1
    assert docs[0]["metadata"]["parser"] == "fallback"


@pytest.mark.asyncio
async def test_load_re_raises_when_fallback_disabled(tmp_path):
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")

    fake_parser = MagicMock()
    fake_parser.aload_data = AsyncMock(side_effect=RuntimeError("API down"))

    with patch.object(
        llamaparse, "_llama_parse_available", return_value=True,
    ), patch.object(
        llamaparse, "_import_llama_parse",
        return_value=MagicMock(return_value=fake_parser),
    ):
        with pytest.raises(RuntimeError, match="API down"):
            await llamaparse.load_with_llamaparse(
                f, api_key="x", fallback_on_error=False,
            )


def test_sync_wrapper_works(tmp_path, monkeypatch):
    """The sync wrapper should run the coroutine."""
    from largestack._loaders import llamaparse

    f = tmp_path / "doc.txt"
    f.write_text("sync test")

    # Force fallback path (no llama_parse)
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    with patch.object(
        llamaparse, "_llama_parse_available", return_value=False,
    ):
        docs = llamaparse.load_with_llamaparse_sync(f)

    assert len(docs) >= 1
