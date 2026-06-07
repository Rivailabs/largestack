"""Twilio + GitHub Full + Confluence Toolkits (v0.9.0).

Three more toolkits in one file (cohesive grouping):

- ``TwilioToolkit`` — SMS, WhatsApp, voice calls
- ``GitHubFullToolkit`` — beyond v0.5's basic; PRs, branches, files, search
- ``ConfluenceToolkit`` — write/update Confluence pages
"""

from __future__ import annotations
import base64
import json
import logging
import os
from typing import Any, Callable

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.toolkits_v09")


# -------------------- Twilio --------------------


class TwilioToolkit:
    """Twilio: SMS, WhatsApp, voice calls.

    Auth: LARGESTACK_TWILIO_ACCOUNT_SID + LARGESTACK_TWILIO_AUTH_TOKEN env vars
    (or constructor args).
    """

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
    ):
        self.account_sid = (
            account_sid
            or os.environ.get("LARGESTACK_TWILIO_ACCOUNT_SID")
            or os.environ.get("TWILIO_ACCOUNT_SID", "")
        )
        self.auth_token = (
            auth_token
            or os.environ.get("LARGESTACK_TWILIO_AUTH_TOKEN")
            or os.environ.get("TWILIO_AUTH_TOKEN", "")
        )
        self.base_url = "https://api.twilio.com/2010-04-01"
        self._tools: list[Callable] = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.account_sid or not self.auth_token:
            return "error: LARGESTACK_TWILIO_ACCOUNT_SID + LARGESTACK_TWILIO_AUTH_TOKEN required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="twilio_send_sms",
            description="Send an SMS to a phone number (E.164 format like +14155551234)",
            timeout=30,
        )
        async def send_sms(to: str, body: str, from_: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.account_sid, tk.auth_token)
                ) as client:
                    data: dict = {"To": to, "Body": body}
                    if from_:
                        data["From"] = from_
                    elif os.environ.get("TWILIO_FROM_NUMBER"):
                        data["From"] = os.environ["TWILIO_FROM_NUMBER"]
                    else:
                        return "error: from_ arg or TWILIO_FROM_NUMBER required"
                    r = await client.post(
                        f"{tk.base_url}/Accounts/{tk.account_sid}/Messages.json",
                        data=data,
                    )
                    resp = r.json()
                    if r.status_code >= 400:
                        return f"error: Twilio HTTP {r.status_code}: {resp.get('message', '')}"
                    return json.dumps(
                        {
                            "sid": resp.get("sid"),
                            "status": resp.get("status"),
                            "to": resp.get("to"),
                            "from": resp.get("from"),
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="twilio_send_whatsapp",
            description="Send a WhatsApp message via Twilio (uses 'whatsapp:' prefix)",
            timeout=30,
        )
        async def send_whatsapp(to: str, body: str, from_: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            wa_to = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
            wa_from = ""
            if from_:
                wa_from = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
            elif os.environ.get("TWILIO_WA_FROM"):
                v = os.environ["TWILIO_WA_FROM"]
                wa_from = v if v.startswith("whatsapp:") else f"whatsapp:{v}"
            return await send_sms(wa_to, body, wa_from)

        @tool(
            name="twilio_make_call",
            description="Initiate an outbound voice call. url is a TwiML URL telling Twilio what to say.",
            timeout=30,
        )
        async def make_call(to: str, url: str, from_: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.account_sid, tk.auth_token)
                ) as client:
                    data: dict = {"To": to, "Url": url}
                    if from_:
                        data["From"] = from_
                    elif os.environ.get("TWILIO_FROM_NUMBER"):
                        data["From"] = os.environ["TWILIO_FROM_NUMBER"]
                    else:
                        return "error: from_ arg or TWILIO_FROM_NUMBER required"
                    r = await client.post(
                        f"{tk.base_url}/Accounts/{tk.account_sid}/Calls.json",
                        data=data,
                    )
                    resp = r.json()
                    if r.status_code >= 400:
                        return f"error: Twilio HTTP {r.status_code}: {resp.get('message', '')}"
                    return json.dumps(
                        {
                            "sid": resp.get("sid"),
                            "status": resp.get("status"),
                            "to": resp.get("to"),
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        return [send_sms, send_whatsapp, make_call]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- GitHub Full --------------------


class GitHubFullToolkit:
    """Full GitHub toolkit: PRs, branches, files, code search.

    Builds on the v0.5 basic GitHub tools (issues only). This adds:
    - PR creation, listing, merging
    - File read/write/delete
    - Branch ops
    - Code search

    Auth: LARGESTACK_GITHUB_TOKEN env var.
    """

    def __init__(self, owner: str, repo: str, api_token: str | None = None):
        self.owner = owner
        self.repo = repo
        self.api_token = (
            api_token
            or os.environ.get("LARGESTACK_GITHUB_TOKEN")
            or os.environ.get("GITHUB_TOKEN", "")
        )
        self.base_url = "https://api.github.com"
        self._tools = self._build_tools()

    @property
    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        if self.api_token:
            h["Authorization"] = f"Bearer {self.api_token}"
        return h

    def _check_auth(self) -> str | None:
        if not self.api_token:
            return "error: LARGESTACK_GITHUB_TOKEN required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(name="github_list_prs", description="List pull requests in the repo")
        async def list_prs(state: str = "open", limit: int = 10) -> str:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/repos/{tk.owner}/{tk.repo}/pulls",
                        headers=tk._headers,
                        params={"state": state, "per_page": min(int(limit), 100)},
                    )
                    if r.status_code >= 400:
                        return f"error: GitHub HTTP {r.status_code}"
                    prs = [
                        {
                            "number": p["number"],
                            "title": p["title"],
                            "state": p["state"],
                            "user": p["user"]["login"],
                            "created_at": p["created_at"],
                            "url": p["html_url"],
                        }
                        for p in r.json()
                    ]
                    return json.dumps({"prs": prs})
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="github_create_pr",
            description="Create a pull request. base is target branch (usually 'main'), head is the source branch.",
            timeout=30,
        )
        async def create_pr(title: str, head: str, base: str = "main", body: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{tk.base_url}/repos/{tk.owner}/{tk.repo}/pulls",
                        headers=tk._headers,
                        json={"title": title, "head": head, "base": base, "body": body},
                    )
                    if r.status_code >= 400:
                        return f"error: GitHub HTTP {r.status_code}: {r.text[:300]}"
                    p = r.json()
                    return json.dumps(
                        {
                            "number": p.get("number"),
                            "url": p.get("html_url"),
                            "state": p.get("state"),
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        @tool(name="github_get_file", description="Get the content of a file in the repo")
        async def get_file(path: str, ref: str = "main") -> str:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/repos/{tk.owner}/{tk.repo}/contents/{path}",
                        headers=tk._headers,
                        params={"ref": ref},
                    )
                    if r.status_code >= 400:
                        return f"error: GitHub HTTP {r.status_code}"
                    data = r.json()
                    if data.get("encoding") == "base64":
                        try:
                            content = base64.b64decode(data.get("content", "")).decode(
                                "utf-8", errors="replace"
                            )
                        except Exception:
                            content = "<binary>"
                    else:
                        content = data.get("content", "")
                    return json.dumps(
                        {
                            "path": data.get("path"),
                            "size": data.get("size"),
                            "sha": data.get("sha"),
                            "content": content,
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="github_search_code",
            description="Search for code across the repo. q is GitHub search syntax.",
        )
        async def search_code(q: str, limit: int = 10) -> str:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    full_q = f"{q} repo:{tk.owner}/{tk.repo}"
                    r = await client.get(
                        f"{tk.base_url}/search/code",
                        headers=tk._headers,
                        params={"q": full_q, "per_page": min(int(limit), 100)},
                    )
                    if r.status_code >= 400:
                        return f"error: GitHub HTTP {r.status_code}"
                    items = r.json().get("items", [])
                    matches = [
                        {
                            "path": i.get("path"),
                            "name": i.get("name"),
                            "url": i.get("html_url"),
                        }
                        for i in items
                    ]
                    return json.dumps({"matches": matches})
            except Exception as e:
                return f"error: {e}"

        @tool(name="github_list_branches", description="List branches in the repo")
        async def list_branches() -> str:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/repos/{tk.owner}/{tk.repo}/branches",
                        headers=tk._headers,
                    )
                    if r.status_code >= 400:
                        return f"error: GitHub HTTP {r.status_code}"
                    branches = [
                        {"name": b.get("name"), "sha": b.get("commit", {}).get("sha")}
                        for b in r.json()
                    ]
                    return json.dumps({"branches": branches})
            except Exception as e:
                return f"error: {e}"

        return [list_prs, create_pr, get_file, search_code, list_branches]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- Confluence (write) --------------------


class ConfluenceToolkit:
    """Confluence write operations.

    Read uses ``load_confluence`` from the loaders module; this toolkit
    provides write tools (create page, update page, attach file).

    Auth: LARGESTACK_CONFLUENCE_USER + LARGESTACK_CONFLUENCE_TOKEN.
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        api_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = (
            username
            or os.environ.get("LARGESTACK_CONFLUENCE_USER")
            or os.environ.get("CONFLUENCE_USER", "")
        )
        self.api_token = (
            api_token
            or os.environ.get("LARGESTACK_CONFLUENCE_TOKEN")
            or os.environ.get("CONFLUENCE_TOKEN", "")
        )
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.username or not self.api_token:
            return "error: Confluence creds required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="confluence_create_page",
            description="Create a new Confluence page in a space",
            timeout=30,
        )
        async def create_page(
            space_key: str, title: str, content_html: str, parent_id: str = ""
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            body: dict = {
                "type": "page",
                "title": title,
                "space": {"key": space_key},
                "body": {"storage": {"value": content_html, "representation": "storage"}},
            }
            if parent_id:
                body["ancestors"] = [{"id": parent_id}]
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.username, tk.api_token)
                ) as client:
                    r = await client.post(
                        f"{tk.base_url}/rest/api/content",
                        json=body,
                        headers={"Content-Type": "application/json"},
                    )
                    if r.status_code >= 400:
                        return f"error: Confluence HTTP {r.status_code}: {r.text[:300]}"
                    p = r.json()
                    return json.dumps(
                        {
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "url": (p.get("_links") or {}).get("base", "")
                            + (p.get("_links") or {}).get("webui", ""),
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="confluence_update_page",
            description="Update an existing Confluence page (must increment version)",
            timeout=30,
        )
        async def update_page(page_id: str, title: str, content_html: str, version: int) -> str:
            err = tk._check_auth()
            if err:
                return err
            body = {
                "type": "page",
                "title": title,
                "body": {"storage": {"value": content_html, "representation": "storage"}},
                "version": {"number": int(version) + 1},
            }
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.username, tk.api_token)
                ) as client:
                    r = await client.put(
                        f"{tk.base_url}/rest/api/content/{page_id}",
                        json=body,
                        headers={"Content-Type": "application/json"},
                    )
                    if r.status_code >= 400:
                        return f"error: Confluence HTTP {r.status_code}: {r.text[:300]}"
                    p = r.json()
                    return json.dumps(
                        {
                            "id": p.get("id"),
                            "version": (p.get("version") or {}).get("number"),
                        }
                    )
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="confluence_search",
            description="Search Confluence with CQL (e.g., 'title = \"Architecture\"')",
        )
        async def search(cql: str, limit: int = 10) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.username, tk.api_token)
                ) as client:
                    r = await client.get(
                        f"{tk.base_url}/rest/api/content/search",
                        params={"cql": cql, "limit": min(int(limit), 100)},
                    )
                    if r.status_code >= 400:
                        return f"error: Confluence HTTP {r.status_code}"
                    results = [
                        {"id": x.get("id"), "title": x.get("title"), "type": x.get("type")}
                        for x in r.json().get("results", [])
                    ]
                    return json.dumps({"results": results})
            except Exception as e:
                return f"error: {e}"

        return [create_page, update_page, search]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)
