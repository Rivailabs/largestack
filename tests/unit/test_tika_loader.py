"""Apache Tika loader tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        text: str = "",
        json=None,
    ):
        self.status_code = status_code
        self.text = text
        self._json_data = json

    def json(self):
        if self._json_data is None:
            raise ValueError("no JSON body")
        return self._json_data


def _patch_httpx_client(monkeypatch, routes):
    calls = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def put(self, url, *, content=None, headers=None):
            calls.append(
                {
                    "url": str(url),
                    "content": content,
                    "headers": headers or {},
                }
            )
            response = routes[str(url)]
            return response() if callable(response) else response

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return calls


def test_module_imports_cleanly():
    from largestack._loaders import load_with_tika, load_with_tika_sync
    from largestack._loaders.tika import TikaLoaderError

    assert callable(load_with_tika)
    assert callable(load_with_tika_sync)
    assert issubclass(TikaLoaderError, RuntimeError)


@pytest.mark.asyncio
async def test_load_with_tika_raises_on_missing_file(tmp_path):
    from largestack._loaders.tika import load_with_tika

    with pytest.raises(FileNotFoundError):
        await load_with_tika(tmp_path / "missing.pdf")


@pytest.mark.asyncio
async def test_http_tika_text_extraction(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika

    path = tmp_path / "doc.txt"
    path.write_text("raw text", encoding="utf-8")

    calls = _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/tika/text": _FakeResponse(
                200,
                text="Parsed by Tika",
            ),
        },
    )
    docs = await load_with_tika(path, include_metadata=False)

    assert docs == [
        {
            "content": "Parsed by Tika",
            "metadata": {
                "source": str(path),
                "format": "txt",
                "parser": "tika",
                "backend": "http",
                "tika_endpoint": "/tika/text",
                "tika_server_url": "http://127.0.0.1:9998",
            },
        }
    ]
    assert calls[0]["headers"]["resourceName"] == "doc.txt"


@pytest.mark.asyncio
async def test_http_tika_rmeta_extraction(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika

    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 fake")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/rmeta/text": _FakeResponse(
                200,
                json=[
                    {
                        "X-TIKA:content": "Main body",
                        "Content-Type": "application/pdf",
                        "dc:title": "Quarterly report",
                    }
                ],
            ),
        },
    )
    docs = await load_with_tika(path)

    assert len(docs) == 1
    assert docs[0]["content"] == "Main body"
    assert docs[0]["metadata"]["parser"] == "tika"
    assert docs[0]["metadata"]["backend"] == "http"
    assert docs[0]["metadata"]["tika_endpoint"] == "/rmeta/text"
    assert docs[0]["metadata"]["tika_index"] == 0
    assert docs[0]["metadata"]["Content-Type"] == "application/pdf"
    assert docs[0]["metadata"]["dc:title"] == "Quarterly report"


@pytest.mark.asyncio
async def test_http_tika_rmeta_embedded_docs(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika

    path = tmp_path / "slides.pptx"
    path.write_bytes(b"fake pptx")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/rmeta/text": _FakeResponse(
                200,
                json=[
                    {
                        "X-TIKA:content": "Deck summary",
                        "Content-Type": "application/vnd.ms-powerpoint",
                    },
                    {"X-TIKA:content": "Embedded note", "resourceName": "notes.txt"},
                ],
            ),
        },
    )
    docs = await load_with_tika(path)

    assert len(docs) == 2
    assert [doc["content"] for doc in docs] == ["Deck summary", "Embedded note"]
    assert docs[0]["metadata"]["tika_index"] == 0
    assert docs[1]["metadata"]["tika_index"] == 1


@pytest.mark.asyncio
async def test_http_tika_uses_plain_text_when_rmeta_unavailable(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika

    path = tmp_path / "doc.html"
    path.write_text("<h1>Hello</h1>", encoding="utf-8")

    calls = _patch_httpx_client(
        monkeypatch,
        {
            "http://tika.local/rmeta/text": _FakeResponse(404),
            "http://tika.local/tika/text": _FakeResponse(200, text="Hello"),
        },
    )
    docs = await load_with_tika(path, server_url="http://tika.local")

    assert len(docs) == 1
    assert docs[0]["content"] == "Hello"
    assert docs[0]["metadata"]["tika_endpoint"] == "/tika/text"
    assert docs[0]["metadata"]["tika_server_url"] == "http://tika.local"
    assert [call["url"] for call in calls] == [
        "http://tika.local/rmeta/text",
        "http://tika.local/tika/text",
    ]


@pytest.mark.asyncio
async def test_http_tika_server_error_falls_back(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika

    path = tmp_path / "doc.txt"
    path.write_text("fallback text", encoding="utf-8")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/rmeta/text": _FakeResponse(500),
            "http://127.0.0.1:9998/tika/text": _FakeResponse(503),
        },
    )
    docs = await load_with_tika(path)

    assert len(docs) == 1
    assert docs[0]["content"] == "fallback text"
    assert docs[0]["metadata"]["parser"] == "fallback"
    assert "Tika" not in docs[0]["content"]
    assert "tika http backend failed" in docs[0]["metadata"]["fallback_reason"]


@pytest.mark.asyncio
async def test_http_tika_server_error_raises_when_fallback_disabled(tmp_path, monkeypatch):
    from largestack._loaders.tika import TikaLoaderError, load_with_tika

    path = tmp_path / "doc.txt"
    path.write_text("fallback text", encoding="utf-8")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/rmeta/text": _FakeResponse(500),
            "http://127.0.0.1:9998/tika/text": _FakeResponse(503),
        },
    )
    with pytest.raises(TikaLoaderError, match="Apache Tika"):
        await load_with_tika(path, fallback_on_error=False)


@pytest.mark.asyncio
async def test_python_backend_missing_package_falls_back(tmp_path):
    from largestack._loaders import tika

    path = tmp_path / "doc.txt"
    path.write_text("fallback text", encoding="utf-8")

    with patch.object(
        tika,
        "_import_python_tika_parser",
        side_effect=ImportError("missing tika"),
    ):
        docs = await tika.load_with_tika(path, backend="python")

    assert docs[0]["content"] == "fallback text"
    assert docs[0]["metadata"]["parser"] == "fallback"
    assert "tika python backend failed" in docs[0]["metadata"]["fallback_reason"]


@pytest.mark.asyncio
async def test_python_backend_missing_package_raises_when_fallback_disabled(tmp_path):
    from largestack._loaders import tika

    path = tmp_path / "doc.txt"
    path.write_text("fallback text", encoding="utf-8")

    with patch.object(
        tika,
        "_import_python_tika_parser",
        side_effect=ImportError("missing tika"),
    ):
        with pytest.raises(ImportError, match="missing tika"):
            await tika.load_with_tika(
                path,
                backend="python",
                fallback_on_error=False,
            )


@pytest.mark.asyncio
async def test_load_dispatcher_routes_to_tika(tmp_path, monkeypatch):
    from largestack._loaders import load

    path = tmp_path / "doc.txt"
    path.write_text("raw text", encoding="utf-8")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://tika.local/tika/text": _FakeResponse(200, text="dispatcher parsed"),
        },
    )
    docs = await load(
        str(path),
        parser="tika",
        server_url="http://tika.local",
        include_metadata=False,
    )

    assert docs[0]["content"] == "dispatcher parsed"
    assert docs[0]["metadata"]["parser"] == "tika"


@pytest.mark.asyncio
async def test_default_load_behavior_is_unchanged(tmp_path, monkeypatch):
    import largestack._loaders as loaders

    path = tmp_path / "doc.txt"
    path.write_text("plain loader", encoding="utf-8")

    async def fake_load_text(received_path):
        return [
            {
                "content": f"plain loader from {received_path}",
                "metadata": {"source": received_path, "format": "text"},
            }
        ]

    monkeypatch.setattr(loaders, "load_text", fake_load_text)
    docs = await loaders.load(str(path))

    assert docs[0]["content"] == f"plain loader from {path}"
    assert docs[0]["metadata"]["format"] == "text"
    assert "parser" not in docs[0]["metadata"]


@pytest.mark.asyncio
async def test_load_dispatcher_rejects_unknown_parser(tmp_path):
    from largestack._loaders import load

    path = tmp_path / "doc.txt"
    path.write_text("plain loader", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown loader parser"):
        await load(str(path), parser="unknown")


def test_sync_wrapper_works(tmp_path, monkeypatch):
    from largestack._loaders.tika import load_with_tika_sync

    path = tmp_path / "doc.txt"
    path.write_text("raw text", encoding="utf-8")

    _patch_httpx_client(
        monkeypatch,
        {
            "http://127.0.0.1:9998/tika/text": _FakeResponse(200, text="sync parsed"),
        },
    )
    docs = load_with_tika_sync(path, include_metadata=False)

    assert docs[0]["content"] == "sync parsed"
