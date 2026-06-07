"""Apache Tika loader for broad document extraction.

The default backend talks to a configured Apache Tika server over HTTP.
The optional ``python`` backend uses the PyPI ``tika`` package only when
requested explicitly.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger("largestack.loaders.tika")

DEFAULT_TIKA_SERVER_URL = "http://127.0.0.1:9998"
TIKA_SERVER_URL_ENV = "TIKA_SERVER_URL"
_TEXT_FALLBACK_EXTENSIONS = {"", ".txt", ".text", ".log", ".md", ".markdown"}


class TikaLoaderError(RuntimeError):
    """Raised when Apache Tika extraction fails."""


async def load_with_tika(
    path: str | Path,
    *,
    backend: str = "http",
    server_url: str | None = None,
    include_metadata: bool = True,
    timeout: float = 60.0,
    fallback_on_error: bool = True,
    output_format: str = "text",
) -> list[dict[str, Any]]:
    """Parse a document with Apache Tika.

    Args:
        path: Local file path to parse.
        backend: ``"http"`` for an Apache Tika server or ``"python"`` for
            the optional PyPI ``tika`` package.
        server_url: Tika server URL. Defaults to ``TIKA_SERVER_URL`` and then
            ``http://127.0.0.1:9998``.
        include_metadata: Use Tika's recursive metadata endpoint when true.
        timeout: HTTP timeout in seconds for the server backend.
        fallback_on_error: Fall back to Largestack's built-in loader on
            parser/server failures.
        output_format: Extracted output format. Currently ``"text"``.

    Returns:
        ``[{"content": str, "metadata": dict}, ...]``
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")

    backend = backend.lower().strip()
    if backend not in {"http", "python"}:
        raise ValueError("backend must be 'http' or 'python'")
    if output_format != "text":
        raise ValueError("output_format must be 'text'")

    try:
        if backend == "http":
            return await _load_with_http_tika(
                p,
                server_url=server_url,
                include_metadata=include_metadata,
                timeout=timeout,
            )
        return await _load_with_python_tika(
            p,
            include_metadata=include_metadata,
        )
    except Exception as exc:
        if not fallback_on_error:
            raise
        log.warning(
            "Apache Tika %s backend failed: %s; falling back to built-in loader",
            backend,
            exc,
        )
        reason = f"tika {backend} backend failed: {type(exc).__name__}"
        return await _fallback_load(p, reason=reason)


async def _load_with_http_tika(
    path: Path,
    *,
    server_url: str | None,
    include_metadata: bool,
    timeout: float,
) -> list[dict[str, Any]]:
    import httpx

    base_url = _resolve_server_url(server_url)
    data = path.read_bytes()

    async with httpx.AsyncClient(timeout=timeout) as client:
        if include_metadata:
            try:
                docs = await _request_rmeta_text(client, base_url, path, data)
                if docs:
                    return docs
            except Exception as exc:
                log.warning(
                    "Apache Tika /rmeta/text unavailable: %s; trying /tika/text",
                    exc,
                )
        return [await _request_tika_text(client, base_url, path, data)]


async def _request_rmeta_text(
    client: Any,
    base_url: str,
    path: Path,
    data: bytes,
) -> list[dict[str, Any]]:
    response = await client.put(
        _endpoint_url(base_url, "/rmeta/text"),
        content=data,
        headers=_headers(path, accept="application/json"),
    )
    if response.status_code >= 400:
        raise TikaLoaderError(f"Apache Tika /rmeta/text returned HTTP {response.status_code}")
    try:
        items = response.json()
    except Exception as exc:
        raise TikaLoaderError("Apache Tika /rmeta/text returned invalid JSON") from exc
    if not isinstance(items, list):
        raise TikaLoaderError("Apache Tika /rmeta/text returned a non-list response")

    docs: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        content = item.get("X-TIKA:content") or ""
        item_metadata = {str(k): v for k, v in item.items() if k != "X-TIKA:content"}
        metadata = item_metadata
        metadata.update(
            _base_metadata(
                path,
                backend="http",
                endpoint="/rmeta/text",
                server_url=base_url,
                index=index,
            )
        )
        docs.append({"content": str(content), "metadata": metadata})
    return docs


async def _request_tika_text(
    client: Any,
    base_url: str,
    path: Path,
    data: bytes,
) -> dict[str, Any]:
    response = await client.put(
        _endpoint_url(base_url, "/tika/text"),
        content=data,
        headers=_headers(path, accept="text/plain"),
    )
    if response.status_code >= 400:
        raise TikaLoaderError(f"Apache Tika /tika/text returned HTTP {response.status_code}")
    return {
        "content": response.text,
        "metadata": _base_metadata(
            path,
            backend="http",
            endpoint="/tika/text",
            server_url=base_url,
        ),
    }


async def _load_with_python_tika(
    path: Path,
    *,
    include_metadata: bool,
) -> list[dict[str, Any]]:
    parser = _import_python_tika_parser()

    parsed = await asyncio.to_thread(parser.from_file, str(path))
    if not isinstance(parsed, dict):
        raise TikaLoaderError("python tika returned a non-dict response")

    metadata = _base_metadata(path, backend="python", endpoint="parser.from_file")
    if include_metadata and isinstance(parsed.get("metadata"), dict):
        metadata.update(parsed["metadata"])
        metadata.update(
            _base_metadata(
                path,
                backend="python",
                endpoint="parser.from_file",
            )
        )
    content = parsed.get("content") or ""
    return [{"content": str(content), "metadata": metadata}]


def _import_python_tika_parser():
    try:
        from tika import parser  # type: ignore
    except ImportError as exc:
        raise ImportError(
            'Apache Tika Python backend not installed. Install with: pip install "largestack[tika]"'
        ) from exc
    return parser


async def _fallback_load(path: Path, *, reason: str) -> list[dict[str, Any]]:
    if path.suffix.lower() in _TEXT_FALLBACK_EXTENSIONS:
        docs = [_load_text_fallback(path)]
    else:
        docs = await _fallback_with_builtin_loader(path)

    for doc in docs:
        metadata = doc.setdefault("metadata", {})
        metadata["parser"] = "fallback"
        metadata["fallback_reason"] = reason
    return docs


async def _fallback_with_builtin_loader(path: Path) -> list[dict[str, Any]]:
    from largestack._loaders import load

    return await load(str(path))


def _load_text_fallback(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    return {
        "content": text,
        "metadata": {
            "source": str(path),
            "format": "text" if path.suffix.lower() not in {".md", ".markdown"} else "markdown",
        },
    }


def _resolve_server_url(server_url: str | None) -> str:
    """Resolve the Tika server URL.

    This must be TRUSTED configuration (your own Tika server), not untrusted user
    input. Non-HTTP(S) schemes are rejected as a basic SSRF guard (file://, etc.).
    """
    resolved = (
        server_url or os.environ.get(TIKA_SERVER_URL_ENV) or DEFAULT_TIKA_SERVER_URL
    ).rstrip("/")
    if not resolved.startswith(("http://", "https://")):
        raise ValueError(f"Tika server URL must be http(s), got {resolved!r}")
    return resolved


def _endpoint_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _headers(path: Path, *, accept: str) -> dict[str, str]:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "Accept": accept,
        "Content-Type": content_type,
        "resourceName": path.name,
    }


def _base_metadata(
    path: Path,
    *,
    backend: str,
    endpoint: str,
    server_url: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": str(path),
        "format": path.suffix.lower().lstrip(".") or "unknown",
        "parser": "tika",
        "backend": backend,
        "tika_endpoint": endpoint,
    }
    if server_url:
        metadata["tika_server_url"] = _safe_url(server_url)
    if index is not None:
        metadata["tika_index"] = index
    return metadata


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def load_with_tika_sync(
    path: str | Path,
    *,
    backend: str = "http",
    server_url: str | None = None,
    include_metadata: bool = True,
    timeout: float = 60.0,
    fallback_on_error: bool = True,
    output_format: str = "text",
) -> list[dict[str, Any]]:
    """Synchronous wrapper around ``load_with_tika``."""
    return asyncio.run(
        load_with_tika(
            path,
            backend=backend,
            server_url=server_url,
            include_metadata=include_metadata,
            timeout=timeout,
            fallback_on_error=fallback_on_error,
            output_format=output_format,
        )
    )


__all__ = [
    "DEFAULT_TIKA_SERVER_URL",
    "TIKA_SERVER_URL_ENV",
    "TikaLoaderError",
    "load_with_tika",
    "load_with_tika_sync",
]
