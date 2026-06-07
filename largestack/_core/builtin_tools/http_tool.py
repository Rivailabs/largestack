"""HTTP client tool — v0.3.11 SSRF-hardened, v0.3.12 refactored to use shared validator.

v0.3.10 made arbitrary HTTP requests with `follow_redirects=True` and no
URL validation. An LLM tool call could:
  - Hit cloud metadata: http://169.254.169.254/latest/meta-data/iam
  - Reach internal services: http://localhost:8500/v1/kv/secrets
  - Bypass via redirect to a private IP after passing an external check

v0.3.11 fixed it inline. v0.3.12 extracts the validator to
`_url_validator.py` so `web_fetch` and `browser_navigate` (which had the
same flaw — silently) share the same protection.
"""

from __future__ import annotations
import logging
import os

from largestack._core.tools import tool
from largestack._core.builtin_tools._url_validator import validate_url

log = logging.getLogger("largestack.tools.http")

_FOLLOW_REDIRECTS = os.environ.get("LARGESTACK_HTTP_TOOL_FOLLOW_REDIRECTS", "").lower() in (
    "1",
    "true",
    "yes",
)


@tool(timeout=15)
async def http_request(url: str, method: str = "GET", body: str = "", headers: str = "") -> str:
    """Make an HTTP/HTTPS request. SSRF-protected.

    Validation:
        - Scheme must be http or https
        - Host must NOT resolve to a private/loopback/link-local/metadata IP
        - Set LARGESTACK_HTTP_ALLOWLIST=host1,host2,... to restrict to specific hosts
        - Redirects disabled by default (set LARGESTACK_HTTP_TOOL_FOLLOW_REDIRECTS=1 to allow)

    Args:
        url: target URL (http/https only)
        method: GET, POST, PUT, DELETE
        body: request body for POST/PUT
        headers: JSON-encoded dict of extra headers, e.g. '{"X-Foo":"bar"}'

    Returns:
        "Status: <code>\\n<body[:3000]>"
    """
    import json
    import httpx

    err = validate_url(url)
    if err is not None:
        return f"Request blocked: {err}"

    try:
        h = json.loads(headers) if headers else {}
        if not isinstance(h, dict):
            return "Error: headers must be a JSON object"
    except json.JSONDecodeError as e:
        return f"Error: invalid headers JSON: {e}"

    method_u = method.upper()
    if method_u not in ("GET", "POST", "PUT", "DELETE"):
        return f"Unsupported method: {method!r}"

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=_FOLLOW_REDIRECTS) as c:
            if method_u == "GET":
                r = await c.get(url, headers=h)
            elif method_u == "POST":
                r = await c.post(url, content=body, headers=h)
            elif method_u == "PUT":
                r = await c.put(url, content=body, headers=h)
            else:
                r = await c.delete(url, headers=h)
    except httpx.RequestError as e:
        return f"HTTP error: {e}"

    return f"Status: {r.status_code}\n{r.text[:3000]}"
