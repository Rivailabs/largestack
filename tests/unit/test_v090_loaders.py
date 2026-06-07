"""v0.9.0: Tests for 8 high-value document loaders."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

respx = pytest.importorskip("respx")


# -------------------- Notion database --------------------


@pytest.mark.asyncio
async def test_load_notion_database_no_token(monkeypatch):
    monkeypatch.delenv("LARGESTACK_NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    from largestack._loaders import load_notion_database

    docs = await load_notion_database("xxx")
    assert "LARGESTACK_NOTION_TOKEN" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_notion_database_paginated(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOTION_TOKEN", "fake")
    from largestack._loaders import load_notion_database

    page1 = {
        "results": [
            {
                "id": "page-uuid-1",
                "url": "https://notion.so/p1",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": "Page 1"}]},
                    "Status": {"type": "select", "select": {"name": "Active"}},
                },
            },
        ],
        "has_more": False,
    }
    blocks_resp = {
        "results": [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Hello world."}]}},
        ]
    }

    with respx.mock() as mock:
        mock.post("https://api.notion.com/v1/databases/db1/query").respond(200, json=page1)
        mock.get("https://api.notion.com/v1/blocks/page-uuid-1/children").respond(
            200, json=blocks_resp
        )
        docs = await load_notion_database("db1")

    assert len(docs) == 1
    assert "Hello world" in docs[0]["content"]
    assert docs[0]["metadata"]["Name"] == "Page 1"
    assert docs[0]["metadata"]["Status"] == "Active"


@pytest.mark.asyncio
async def test_load_notion_database_http_error(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOTION_TOKEN", "fake")
    from largestack._loaders import load_notion_database

    with respx.mock() as mock:
        mock.post("https://api.notion.com/v1/databases/x/query").respond(401)
        docs = await load_notion_database("x")
    assert "401" in docs[0]["metadata"]["error"]


# -------------------- Confluence --------------------


@pytest.mark.asyncio
async def test_load_confluence_missing_creds(monkeypatch):
    monkeypatch.delenv("LARGESTACK_CONFLUENCE_USER", raising=False)
    monkeypatch.delenv("LARGESTACK_CONFLUENCE_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_USER", raising=False)
    monkeypatch.delenv("CONFLUENCE_TOKEN", raising=False)
    from largestack._loaders import load_confluence

    docs = await load_confluence("https://x.atlassian.net/wiki", "SPC")
    assert "creds missing" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_confluence_strips_html():
    from largestack._loaders import load_confluence

    fake_resp = {
        "results": [
            {
                "id": "123",
                "title": "Page Title",
                "body": {"storage": {"value": "<p>Hello <b>world</b>!</p>"}},
                "version": {"number": 5},
            }
        ]
    }
    with respx.mock() as mock:
        mock.get("https://x.atlassian.net/wiki/rest/api/content").respond(200, json=fake_resp)
        docs = await load_confluence(
            "https://x.atlassian.net/wiki",
            "SPC",
            username="u@e.com",
            api_token="t",
        )
    assert "Hello world" in docs[0]["content"]
    assert "<p>" not in docs[0]["content"]
    assert docs[0]["metadata"]["title"] == "Page Title"
    assert docs[0]["metadata"]["version"] == 5


# -------------------- GitHub repo --------------------


@pytest.mark.asyncio
async def test_load_github_repo_lists_and_fetches():
    from largestack._loaders import load_github_repo
    import base64 as _b64

    tree_resp = {
        "tree": [
            {"path": "README.md", "type": "blob", "size": 100, "sha": "abc"},
            {"path": "src/main.py", "type": "blob", "size": 500, "sha": "def"},
            {"path": "data.bin", "type": "blob", "size": 5000000, "sha": "xyz"},  # too big
            {"path": "src/", "type": "tree", "size": 0},  # not a blob
        ]
    }
    readme_resp = {
        "html_url": "https://github.com/o/r/blob/main/README.md",
        "encoding": "base64",
        "content": _b64.b64encode(b"# Hello").decode(),
        "sha": "abc",
    }
    main_resp = {
        "html_url": "https://github.com/o/r/blob/main/src/main.py",
        "encoding": "base64",
        "content": _b64.b64encode(b"print('hi')").decode(),
        "sha": "def",
    }

    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/o/r/git/trees/main").respond(200, json=tree_resp)
        mock.get("https://api.github.com/repos/o/r/contents/README.md").respond(
            200, json=readme_resp
        )
        mock.get("https://api.github.com/repos/o/r/contents/src/main.py").respond(
            200, json=main_resp
        )
        docs = await load_github_repo("o", "r", api_token="x")

    assert len(docs) == 2
    paths = {d["metadata"]["path"] for d in docs}
    assert "README.md" in paths
    assert "src/main.py" in paths
    assert any("# Hello" in d["content"] for d in docs)


@pytest.mark.asyncio
async def test_load_github_repo_skips_unknown_extensions():
    from largestack._loaders import load_github_repo

    tree_resp = {
        "tree": [
            {"path": "data.csv", "type": "blob", "size": 100},
            {"path": "image.png", "type": "blob", "size": 100},
        ]
    }
    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/o/r/git/trees/main").respond(200, json=tree_resp)
        docs = await load_github_repo("o", "r")
    # No matching extensions, so error doc returned
    assert "no matching files" in docs[0]["metadata"]["error"]


# -------------------- Google Drive --------------------


@pytest.mark.asyncio
async def test_load_google_drive_missing_sdk(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if "googleapiclient" in name:
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._loaders import load_google_drive

    docs = await load_google_drive("folder123")
    assert "google-api-python-client" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_google_drive_missing_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    fake_googleapi = MagicMock()
    fake_googleapi.discovery.build = MagicMock()
    fake_oauth2 = MagicMock()
    fake_oauth2.service_account.Credentials.from_service_account_file = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "googleapiclient": fake_googleapi,
            "googleapiclient.discovery": fake_googleapi.discovery,
            "google": MagicMock(),
            "google.oauth2": fake_oauth2,
            "google.oauth2.service_account": fake_oauth2.service_account,
        },
    ):
        from largestack._loaders import load_google_drive

        docs = await load_google_drive("folder1")
    assert "GOOGLE_APPLICATION_CREDENTIALS" in docs[0]["metadata"]["error"]


# -------------------- Email IMAP --------------------


@pytest.mark.asyncio
async def test_load_email_imap_connection_error():
    """Bad server returns error doc, not exception."""
    from largestack._loaders import load_email_imap

    docs = await load_email_imap(
        server="invalid.host.local",
        username="x@x.com",
        password="x",
        port=99999,  # invalid port
    )
    assert isinstance(docs, list)
    assert len(docs) > 0
    # First doc should be error doc
    assert "error" in docs[0]["metadata"] or docs[0]["content"]


# -------------------- Gmail --------------------


@pytest.mark.asyncio
async def test_load_gmail_missing_token(monkeypatch):
    monkeypatch.delenv("GMAIL_TOKEN_PATH", raising=False)
    fake_googleapi = MagicMock()
    fake_googleapi.discovery.build = MagicMock()
    fake_oauth2 = MagicMock()
    fake_oauth2.credentials.Credentials.from_authorized_user_file = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "googleapiclient": fake_googleapi,
            "googleapiclient.discovery": fake_googleapi.discovery,
            "google": MagicMock(),
            "google.oauth2": fake_oauth2,
            "google.oauth2.credentials": fake_oauth2.credentials,
        },
    ):
        from largestack._loaders import load_gmail

        docs = await load_gmail("test")
    assert "GMAIL_TOKEN_PATH" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_gmail_missing_sdk(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if "googleapiclient" in name:
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._loaders import load_gmail

    docs = await load_gmail("test")
    assert "google-api-python-client" in docs[0]["metadata"]["error"]


# -------------------- Web scraping --------------------


@pytest.mark.asyncio
async def test_load_web_scrape_missing_playwright(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._loaders import load_web_scrape

    docs = await load_web_scrape("https://example.com")
    assert "playwright" in docs[0]["metadata"]["error"].lower()


# -------------------- OCR --------------------


@pytest.mark.asyncio
async def test_load_ocr_missing_pytesseract(monkeypatch):
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def fake_import(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    from largestack._loaders import load_ocr

    docs = await load_ocr("/tmp/nope.png")
    assert "pytesseract" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_ocr_missing_file(tmp_path):
    """If pytesseract isn't installed we get the dep error first.
    Otherwise we get the missing-file error. Both are valid responses."""
    from largestack._loaders import load_ocr

    docs = await load_ocr(str(tmp_path / "nonexistent.png"))
    err = docs[0]["metadata"]["error"]
    assert "not found" in err or "pytesseract" in err


@pytest.mark.asyncio
async def test_load_ocr_unsupported_extension(tmp_path):
    """Unknown extension returns clear error (or pytesseract missing)."""
    p = tmp_path / "x.xyz"
    p.write_bytes(b"fake")
    from largestack._loaders import load_ocr

    docs = await load_ocr(str(p))
    err = docs[0]["metadata"]["error"]
    assert "unsupported" in err.lower() or "pytesseract" in err
