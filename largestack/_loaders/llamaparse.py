"""LlamaParse loader (v0.12.0) — multi-modal RAG via LlamaCloud.

Closes (via integration) the multi-modal RAG gap. LlamaParse is the
industry-leading document parser — VLM-powered, handles nested tables,
embedded images, charts, handwritten notes across 50+ formats.

**Strategy: integrate, don't compete.** LARGESTACK's pure-text loaders
(pypdf, python-docx, beautifulsoup) work for 80% of cases. For the
remaining 20% — complex enterprise PDFs with tables/charts/scans —
delegate to LlamaParse.

Output format matches the existing LARGESTACK loader contract:
``list[dict[str, Any]]`` where each dict has ``content`` (str) and
``metadata`` (dict).

Usage::

    from largestack._loaders.llamaparse import load_with_llamaparse
    docs = await load_with_llamaparse(
        "balance_sheet.pdf",
        api_key="llx-...",
        result_type="markdown",
    )

If ``llama_parse`` isn't installed, falls back to ``load_pdf`` from the
existing loaders. Tells the user to ``pip install llama-parse`` for
multi-modal features.

Note: as of LlamaIndex v0.13+, ``llama_parse`` is being migrated to
``llama_cloud_services``. This module probes both import paths.
"""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("largestack.loaders.llamaparse")


# Whether llama_parse is importable
def _llama_parse_available() -> bool:
    """Check if llama_parse (or its successor) is installed."""
    try:
        import llama_parse  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        from llama_cloud_services import LlamaParse  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def _import_llama_parse():
    """Import LlamaParse from either package path (legacy or current)."""
    try:
        from llama_parse import LlamaParse
        return LlamaParse
    except ImportError:
        pass
    try:
        from llama_cloud_services import LlamaParse
        return LlamaParse
    except ImportError:
        raise ImportError(
            "llama_parse not installed. Install with: "
            "pip install llama-parse  # or: pip install llama-cloud-services"
        )


# -------------------- Public API --------------------

async def load_with_llamaparse(
    path: str | Path,
    *,
    api_key: str | None = None,
    result_type: str = "markdown",
    language: str = "en",
    num_workers: int = 1,
    fallback_on_error: bool = True,
    extra_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse a document using LlamaParse.

    Args:
        path: file path
        api_key: LlamaCloud API key. Falls back to ``LLAMA_CLOUD_API_KEY``
            env var if not provided.
        result_type: ``"markdown"`` (default) or ``"text"``
        language: source language code (``"en"``, ``"hi"``, etc.)
        num_workers: parallelism for batch parsing
        fallback_on_error: if True and llama_parse fails, fall back to
            the built-in ``load_pdf``
        extra_kwargs: additional kwargs to pass to ``LlamaParse(...)``

    Returns:
        ``[{"content": str, "metadata": dict}, ...]``

    Raises:
        ImportError if llama_parse not installed and fallback disabled
        ValueError if no API key available
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")

    api_key = api_key or os.environ.get("LLAMA_CLOUD_API_KEY", "")

    if not _llama_parse_available():
        if fallback_on_error:
            log.warning(
                "llama_parse not installed; falling back to load_pdf"
            )
            return await _fallback_load(p)
        raise ImportError(
            "llama_parse not installed. Install with: "
            "pip install llama-parse"
        )

    if not api_key:
        if fallback_on_error:
            log.warning(
                "no LLAMA_CLOUD_API_KEY; falling back to load_pdf"
            )
            return await _fallback_load(p)
        raise ValueError(
            "api_key required (or set LLAMA_CLOUD_API_KEY env var)"
        )

    LlamaParse = _import_llama_parse()
    parser_kwargs = dict(
        api_key=api_key,
        result_type=result_type,
        language=language,
        num_workers=num_workers,
    )
    if extra_kwargs:
        parser_kwargs.update(extra_kwargs)

    try:
        parser = LlamaParse(**parser_kwargs)
    except Exception as e:
        if fallback_on_error:
            log.warning(f"LlamaParse init failed: {e}; falling back")
            return await _fallback_load(p)
        raise

    try:
        # llama_parse exposes either aload_data or load_data
        if hasattr(parser, "aload_data"):
            docs = await parser.aload_data(str(p))
        else:
            docs = await asyncio.to_thread(parser.load_data, str(p))
    except Exception as e:
        if fallback_on_error:
            log.warning(f"LlamaParse failed: {e}; falling back")
            return await _fallback_load(p)
        raise

    return _normalize_docs(docs, source=str(p))


def _normalize_docs(docs: Iterable, source: str) -> list[dict[str, Any]]:
    """Convert LlamaParse Document objects → LARGESTACK loader format."""
    out: list[dict[str, Any]] = []
    for d in docs:
        # LlamaParse's Document has .text and .metadata
        content = (
            getattr(d, "text", None)
            or getattr(d, "content", None)
            or str(d)
        )
        metadata = dict(getattr(d, "metadata", {}) or {})
        metadata.setdefault("source", source)
        metadata.setdefault("parser", "llamaparse")
        out.append({"content": content, "metadata": metadata})
    return out


async def _fallback_load(path: Path) -> list[dict[str, Any]]:
    """Fall back to LARGESTACK's built-in PDF loader."""
    suffix = path.suffix.lower()
    try:
        from largestack._loaders import load_pdf, load_text
    except ImportError:
        log.warning(
            "largestack._loaders.load_pdf unavailable; reading as text",
        )
        try:
            return [{
                "content": path.read_text(encoding="utf-8", errors="replace"),
                "metadata": {"source": str(path), "parser": "fallback_text"},
            }]
        except Exception as e:
            return [{"content": "", "metadata": {
                "source": str(path), "error": str(e),
            }}]

    if suffix == ".pdf":
        try:
            docs = await load_pdf(str(path))
        except Exception as e:
            log.warning(f"load_pdf failed: {e}")
            return []
    else:
        try:
            docs = await load_text(str(path))
        except Exception as e:
            log.warning(f"load_text failed: {e}")
            return []

    # Tag with parser=fallback so caller can detect
    for d in docs:
        d.setdefault("metadata", {})
        d["metadata"]["parser"] = "fallback"
    return docs


# -------------------- Sync wrapper --------------------

def load_with_llamaparse_sync(
    path: str | Path,
    *,
    api_key: str | None = None,
    result_type: str = "markdown",
    language: str = "en",
    num_workers: int = 1,
    fallback_on_error: bool = True,
    extra_kwargs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Synchronous wrapper around ``load_with_llamaparse``."""
    return asyncio.run(load_with_llamaparse(
        path, api_key=api_key, result_type=result_type,
        language=language, num_workers=num_workers,
        fallback_on_error=fallback_on_error, extra_kwargs=extra_kwargs,
    ))


__all__ = [
    "load_with_llamaparse",
    "load_with_llamaparse_sync",
]
