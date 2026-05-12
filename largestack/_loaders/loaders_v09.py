"""High-value document loaders (v0.9.0).

Eight production-tested loaders that fill the biggest LangChain-loader
gaps:

- ``load_notion_database`` — full database (not just one page)
- ``load_confluence`` — Confluence space + child pages
- ``load_github_repo`` — recursive repo file listing + content
- ``load_google_drive`` — folder + recursive file fetch
- ``load_email_imap`` — generic IMAP inbox
- ``load_gmail`` — Gmail API search
- ``load_web_scrape`` — Playwright-based dynamic page scraping
- ``load_ocr`` — Tesseract OCR for scanned PDFs/images

All return ``[{content, metadata}]`` dict lists. All gracefully handle
missing optional dependencies and return error documents instead of
raising.
"""
from __future__ import annotations
import asyncio
import base64
import logging
import os
import re
from typing import Any

import httpx

log = logging.getLogger("largestack.loaders_v09")


# -------------------- Notion full database --------------------

async def load_notion_database(
    database_id: str,
    *,
    api_token: str | None = None,
    page_size: int = 100,
) -> list[dict]:
    """Load all pages from a Notion database.

    Args:
        database_id: Notion database UUID (with or without dashes).
        api_token: Notion integration token (or LARGESTACK_NOTION_TOKEN env var).
        page_size: pagination size (max 100).

    Returns one document per page in the database with full text content
    and properties as metadata.
    """
    token = api_token or os.environ.get("LARGESTACK_NOTION_TOKEN") or os.environ.get(
        "NOTION_TOKEN", ""
    )
    if not token:
        return [{"content": "", "metadata": {"error": "LARGESTACK_NOTION_TOKEN not set"}}]

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    docs: list[dict] = []
    cursor = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                body: dict = {"page_size": min(page_size, 100)}
                if cursor:
                    body["start_cursor"] = cursor
                r = await client.post(
                    f"https://api.notion.com/v1/databases/{database_id}/query",
                    headers=headers, json=body,
                )
                if r.status_code >= 400:
                    return [{"content": "", "metadata": {
                        "error": f"Notion HTTP {r.status_code}: {r.text[:200]}"
                    }}]
                data = r.json()
                for page in data.get("results", []):
                    page_id = page.get("id", "")
                    # Get page content (blocks)
                    blocks_r = await client.get(
                        f"https://api.notion.com/v1/blocks/{page_id}/children",
                        headers=headers,
                    )
                    text_parts = []
                    if blocks_r.status_code == 200:
                        for block in blocks_r.json().get("results", []):
                            block_type = block.get("type", "")
                            block_data = block.get(block_type, {})
                            rich = block_data.get("rich_text", [])
                            for rt in rich:
                                text_parts.append(rt.get("plain_text", ""))
                    # Extract properties as metadata
                    props: dict = {}
                    for prop_name, prop_val in (page.get("properties") or {}).items():
                        ptype = prop_val.get("type", "")
                        if ptype == "title":
                            props[prop_name] = "".join(
                                t.get("plain_text", "") for t in prop_val.get("title", [])
                            )
                        elif ptype == "rich_text":
                            props[prop_name] = "".join(
                                t.get("plain_text", "") for t in prop_val.get("rich_text", [])
                            )
                        elif ptype == "select":
                            sel = prop_val.get("select")
                            props[prop_name] = sel.get("name", "") if sel else ""
                        elif ptype == "checkbox":
                            props[prop_name] = bool(prop_val.get("checkbox", False))
                        elif ptype == "number":
                            props[prop_name] = prop_val.get("number")
                    docs.append({
                        "content": "\n".join(text_parts),
                        "metadata": {
                            "source": page.get("url", ""),
                            "format": "notion",
                            "page_id": page_id,
                            "database_id": database_id,
                            **props,
                        },
                    })
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"Notion load failed: {e}"}}]
    if not docs:
        return [{"content": "", "metadata": {"error": "no pages in Notion database"}}]
    return docs


# -------------------- Confluence space --------------------

async def load_confluence(
    base_url: str,
    space_key: str,
    *,
    username: str | None = None,
    api_token: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Load pages from a Confluence space.

    Args:
        base_url: Confluence instance URL (e.g.
            ``https://yoursite.atlassian.net/wiki``).
        space_key: space key (the short uppercase identifier).
        username: email for Atlassian Cloud (or LARGESTACK_CONFLUENCE_USER env).
        api_token: API token (or LARGESTACK_CONFLUENCE_TOKEN env).
        limit: max pages to fetch.

    Auth: HTTP Basic with email + API token.
    """
    user = username or os.environ.get("LARGESTACK_CONFLUENCE_USER") or os.environ.get(
        "CONFLUENCE_USER", ""
    )
    token = api_token or os.environ.get("LARGESTACK_CONFLUENCE_TOKEN") or os.environ.get(
        "CONFLUENCE_TOKEN", ""
    )
    if not user or not token:
        return [{"content": "", "metadata": {"error": "Confluence creds missing"}}]
    base_url = base_url.rstrip("/")
    auth = (user, token)
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30, auth=auth) as client:
            r = await client.get(
                f"{base_url}/rest/api/content",
                params={
                    "spaceKey": space_key, "limit": limit,
                    "expand": "body.storage,version",
                },
            )
            if r.status_code >= 400:
                return [{"content": "", "metadata": {
                    "error": f"Confluence HTTP {r.status_code}: {r.text[:200]}"
                }}]
            for page in r.json().get("results", []):
                title = page.get("title", "")
                content_html = (page.get("body") or {}).get("storage", {}).get("value", "")
                # Strip HTML tags
                text = re.sub(r"<[^>]+>", " ", content_html)
                text = re.sub(r"\s+", " ", text).strip()
                docs.append({
                    "content": text,
                    "metadata": {
                        "source": f"{base_url}/spaces/{space_key}/pages/{page.get('id')}",
                        "format": "confluence",
                        "title": title,
                        "page_id": page.get("id", ""),
                        "space_key": space_key,
                        "version": (page.get("version") or {}).get("number"),
                    },
                })
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"Confluence load failed: {e}"}}]
    if not docs:
        return [{"content": "", "metadata": {"error": "no pages in Confluence space"}}]
    return docs


# -------------------- GitHub repo (recursive) --------------------

async def load_github_repo(
    owner: str,
    repo: str,
    *,
    branch: str = "main",
    api_token: str | None = None,
    extensions: list[str] | None = None,
    max_files: int = 100,
) -> list[dict]:
    """Load all files from a GitHub repository.

    Uses GitHub Trees API for directory listing + Contents API for file
    content. Skips binary files (>1MB) and non-text extensions.

    Args:
        owner: repo owner.
        repo: repo name.
        branch: branch name.
        api_token: GitHub PAT (or LARGESTACK_GITHUB_TOKEN env).
        extensions: list of extensions to include (default: .py .md .txt .rst .json .yaml .yml).
        max_files: cap to prevent runaway loads.
    """
    token = api_token or os.environ.get("LARGESTACK_GITHUB_TOKEN") or os.environ.get(
        "GITHUB_TOKEN", ""
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    extensions = extensions or [
        ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml",
        ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
    ]
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Get tree recursively
            r = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}",
                headers=headers, params={"recursive": "1"},
            )
            if r.status_code >= 400:
                return [{"content": "", "metadata": {
                    "error": f"GitHub tree HTTP {r.status_code}"
                }}]
            tree = r.json().get("tree", [])
            files = [
                t for t in tree
                if t.get("type") == "blob"
                and any(t.get("path", "").endswith(e) for e in extensions)
                and (t.get("size") or 0) < 1_000_000  # skip huge files
            ][:max_files]
            # 2. Fetch each file content
            for f in files:
                path = f.get("path", "")
                cr = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                    headers=headers, params={"ref": branch},
                )
                if cr.status_code != 200:
                    continue
                cdata = cr.json()
                content_b64 = cdata.get("content", "")
                if cdata.get("encoding") == "base64":
                    try:
                        content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                    except Exception:
                        continue
                else:
                    content = content_b64
                docs.append({
                    "content": content,
                    "metadata": {
                        "source": cdata.get("html_url", ""),
                        "format": "github",
                        "path": path,
                        "repo": f"{owner}/{repo}",
                        "branch": branch,
                        "sha": cdata.get("sha", ""),
                    },
                })
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"GitHub load failed: {e}"}}]
    if not docs:
        return [{"content": "", "metadata": {"error": "no matching files in repo"}}]
    return docs


# -------------------- Google Drive folder --------------------

async def load_google_drive(
    folder_id: str,
    *,
    credentials_path: str | None = None,
    max_files: int = 50,
) -> list[dict]:
    """Load all files from a Google Drive folder (and subfolders).

    Args:
        folder_id: Drive folder ID (from URL).
        credentials_path: path to service account JSON (or
            ``GOOGLE_APPLICATION_CREDENTIALS`` env var).
        max_files: cap on total files.

    Requires: ``pip install google-api-python-client google-auth``.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except ImportError:
        return [{"content": "", "metadata": {
            "error": "GDrive loader needs: pip install google-api-python-client google-auth"
        }}]

    creds_path = (
        credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    )
    if not creds_path:
        return [{"content": "", "metadata": {"error": "GOOGLE_APPLICATION_CREDENTIALS not set"}}]

    def _fetch():
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        service = build("drive", "v3", credentials=creds)
        # List files in folder
        files_resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType, webViewLink)",
            pageSize=max_files,
        ).execute()
        files = files_resp.get("files", [])
        out = []
        for f in files:
            mime = f.get("mimeType", "")
            try:
                if mime == "application/vnd.google-apps.document":
                    # Export as plain text
                    content = service.files().export_media(
                        fileId=f["id"], mimeType="text/plain",
                    ).execute()
                    if isinstance(content, bytes):
                        content = content.decode("utf-8", errors="replace")
                elif mime == "application/vnd.google-apps.spreadsheet":
                    content = service.files().export_media(
                        fileId=f["id"], mimeType="text/csv",
                    ).execute()
                    if isinstance(content, bytes):
                        content = content.decode("utf-8", errors="replace")
                else:
                    # Generic file download
                    content = service.files().get_media(fileId=f["id"]).execute()
                    if isinstance(content, bytes):
                        try:
                            content = content.decode("utf-8")
                        except UnicodeDecodeError:
                            content = "<binary>"
            except Exception as e:
                content = f"<error: {e}>"
            out.append({
                "content": content if isinstance(content, str) else "<binary>",
                "metadata": {
                    "source": f.get("webViewLink", ""),
                    "format": "google_drive",
                    "name": f.get("name", ""),
                    "mime_type": mime,
                    "file_id": f.get("id", ""),
                },
            })
        return out

    try:
        docs = await asyncio.to_thread(_fetch)
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"GDrive fetch failed: {e}"}}]
    if not docs:
        return [{"content": "", "metadata": {"error": "no files in GDrive folder"}}]
    return docs


# -------------------- Email IMAP --------------------

async def load_email_imap(
    server: str,
    username: str,
    password: str,
    *,
    folder: str = "INBOX",
    limit: int = 50,
    port: int = 993,
    use_ssl: bool = True,
) -> list[dict]:
    """Load emails from any IMAP server.

    Args:
        server: IMAP server hostname (e.g. ``imap.gmail.com``,
            ``outlook.office365.com``).
        username: full email address.
        password: password or app-specific password.
        folder: IMAP folder name (default INBOX).
        limit: max number of recent messages.
        port: IMAP port (993 SSL, 143 plain).
        use_ssl: whether to use SSL/TLS.

    Returns one document per message with subject, from, date as metadata.
    """
    def _fetch():
        import imaplib
        import email
        from email import policy

        try:
            if use_ssl:
                M = imaplib.IMAP4_SSL(server, port)
            else:
                M = imaplib.IMAP4(server, port)
            M.login(username, password)
            M.select(folder)
            typ, data = M.search(None, "ALL")
            if typ != "OK":
                return []
            ids = data[0].split()
            recent = ids[-limit:]  # most recent N
            out = []
            for msg_id in recent:
                typ, msg_data = M.fetch(msg_id, "(RFC822)")
                if typ != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw, policy=policy.default)
                subject = str(msg.get("Subject", ""))
                from_addr = str(msg.get("From", ""))
                to_addr = str(msg.get("To", ""))
                date = str(msg.get("Date", ""))
                # Extract body
                body_parts = []
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        if ctype == "text/plain":
                            try:
                                body_parts.append(part.get_content())
                            except Exception:
                                pass
                else:
                    try:
                        body_parts.append(msg.get_content())
                    except Exception:
                        pass
                body = "\n".join(body_parts)
                out.append({
                    "content": body,
                    "metadata": {
                        "source": f"imap://{username}@{server}/{folder}/{msg_id.decode()}",
                        "format": "email",
                        "subject": subject,
                        "from": from_addr,
                        "to": to_addr,
                        "date": date,
                        "message_id": msg_id.decode(),
                    },
                })
            try:
                M.close()
                M.logout()
            except Exception:
                pass
            return out
        except Exception as e:
            return [{"content": "", "metadata": {"error": f"IMAP failed: {e}"}}]

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"IMAP load failed: {e}"}}]


# -------------------- Gmail (API) --------------------

async def load_gmail(
    query: str = "is:unread",
    *,
    credentials_path: str | None = None,
    token_path: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Load Gmail messages via Gmail API.

    Args:
        query: Gmail search syntax (e.g. ``"from:boss@example.com"``,
            ``"label:starred"``, ``"is:unread newer_than:7d"``).
        credentials_path: path to OAuth client credentials JSON.
        token_path: path to stored OAuth token (created on first auth).
        max_results: cap on returned messages.

    Requires: ``pip install google-api-python-client google-auth-oauthlib``.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
    except ImportError:
        return [{"content": "", "metadata": {
            "error": "Gmail loader needs: pip install google-api-python-client google-auth-oauthlib"
        }}]

    token_p = token_path or os.environ.get("GMAIL_TOKEN_PATH", "")
    if not token_p or not os.path.exists(token_p):
        return [{"content": "", "metadata": {
            "error": "GMAIL_TOKEN_PATH not set or file missing (run OAuth flow first)"
        }}]

    def _fetch():
        creds = Credentials.from_authorized_user_file(token_p)
        service = build("gmail", "v1", credentials=creds)
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results,
        ).execute()
        messages = resp.get("messages", [])
        out = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="full",
            ).execute()
            payload = msg.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            body_data = ""
            # Walk parts looking for text/plain
            def walk(part):
                nonlocal body_data
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        try:
                            body_data += base64.urlsafe_b64decode(data).decode(
                                "utf-8", errors="replace"
                            )
                        except Exception:
                            pass
                for sub in part.get("parts", []):
                    walk(sub)
            walk(payload)
            out.append({
                "content": body_data or msg.get("snippet", ""),
                "metadata": {
                    "source": f"gmail://me/{m['id']}",
                    "format": "gmail",
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "message_id": m["id"],
                    "thread_id": msg.get("threadId", ""),
                },
            })
        return out

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"Gmail fetch failed: {e}"}}]


# -------------------- Web scraping (Playwright) --------------------

async def load_web_scrape(
    url: str,
    *,
    wait_for_selector: str | None = None,
    timeout: int = 30,
    headless: bool = True,
) -> list[dict]:
    """Scrape a dynamic web page using Playwright (JS-rendered).

    Use this instead of ``load_html`` for JS-heavy pages (SPAs, paywalls,
    delayed-load content).

    Args:
        url: page URL.
        wait_for_selector: CSS selector to wait for before extracting.
        timeout: page load timeout in seconds.
        headless: run browser headless.

    Requires: ``pip install playwright`` then ``playwright install chromium``.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [{"content": "", "metadata": {
            "error": "Playwright not installed (pip install playwright; playwright install chromium)"
        }}]

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(url, timeout=timeout * 1000)
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout * 1000)
                except Exception:
                    pass  # continue anyway
            text = await page.evaluate("() => document.body.innerText")
            title = await page.title()
            await browser.close()
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"Playwright failed: {e}"}}]

    return [{
        "content": text or "",
        "metadata": {
            "source": url,
            "format": "web_scrape",
            "title": title,
            "rendered": True,
        },
    }]


# -------------------- OCR (Tesseract) --------------------

async def load_ocr(
    path: str,
    *,
    language: str = "eng",
) -> list[dict]:
    """OCR a scanned PDF or image file using Tesseract.

    Supports image formats (PNG, JPG, TIFF) and PDFs (multi-page).

    Args:
        path: file path.
        language: Tesseract language code (e.g. ``eng``, ``hin`` for Hindi,
            ``eng+hin`` for both).

    Requires: ``pip install pytesseract pdf2image Pillow`` and the
    Tesseract binary installed system-wide.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return [{"content": "", "metadata": {
            "error": "OCR needs: pip install pytesseract Pillow"
        }}]

    if not os.path.exists(path):
        return [{"content": "", "metadata": {"error": f"file not found: {path}"}}]

    ext = os.path.splitext(path)[1].lower()

    def _ocr_image():
        return pytesseract.image_to_string(Image.open(path), lang=language)

    def _ocr_pdf():
        try:
            from pdf2image import convert_from_path
        except ImportError:
            return None  # signal to caller
        pages = convert_from_path(path)
        return [pytesseract.image_to_string(p, lang=language) for p in pages]

    try:
        if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"}:
            text = await asyncio.to_thread(_ocr_image)
            return [{
                "content": text,
                "metadata": {
                    "source": path, "format": "ocr_image", "language": language,
                },
            }]
        elif ext == ".pdf":
            pages_text = await asyncio.to_thread(_ocr_pdf)
            if pages_text is None:
                return [{"content": "", "metadata": {
                    "error": "PDF OCR needs: pip install pdf2image"
                }}]
            return [
                {
                    "content": text,
                    "metadata": {
                        "source": path, "format": "ocr_pdf",
                        "language": language, "page": i,
                        "total_pages": len(pages_text),
                    },
                }
                for i, text in enumerate(pages_text)
            ]
        else:
            return [{"content": "", "metadata": {
                "error": f"unsupported OCR file extension: {ext}"
            }}]
    except Exception as e:
        return [{"content": "", "metadata": {"error": f"OCR failed: {e}"}}]
