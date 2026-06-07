"""Google Sheets integration — read and append rows.

Auth: env var ``LARGESTACK_GOOGLE_SERVICE_ACCOUNT`` (path to a service-account
JSON key file) — the simplest auth that works headlessly. Share the
sheet with the service account's email.

Uses the Sheets v4 REST API directly via httpx after minting a JWT —
no google-api-python-client / gspread dependency.
"""

from __future__ import annotations
import json
import logging
import os
import time

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.gsheets")
_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
_TOKEN_URI = "https://oauth2.googleapis.com/token"

# In-memory token cache (per process, per service account)
_token_cache: dict[str, tuple[str, float]] = {}


def _load_service_account() -> dict | None:
    path = os.environ.get("LARGESTACK_GOOGLE_SERVICE_ACCOUNT", "").strip()
    if not path:
        return None
    if not os.path.exists(path):
        log.warning(f"LARGESTACK_GOOGLE_SERVICE_ACCOUNT points to missing file: {path}")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load service account file: {e}")
        return None


async def _get_access_token(sa: dict) -> str | None:
    """Mint a Google OAuth2 access token from a service account JWT."""
    cache_key = sa.get("client_email", "")
    cached = _token_cache.get(cache_key)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    try:
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        import base64
    except ImportError:
        log.warning(
            "Sheets integration needs: pip install cryptography (for service-account JWT signing)"
        )
        return None

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": _TOKEN_URI,
        "iat": now,
        "exp": now + 3600,
    }

    def b64url(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    msg = b64url(json.dumps(header).encode()) + "." + b64url(json.dumps(payload).encode())
    private_key = serialization.load_pem_private_key(
        sa["private_key"].encode(),
        password=None,
    )
    sig = private_key.sign(
        msg.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    jwt = msg + "." + b64url(sig)

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            _TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            },
        )
    if r.status_code != 200:
        log.warning(f"Google token mint failed: {r.text[:200]}")
        return None
    token = r.json().get("access_token", "")
    _token_cache[cache_key] = (token, time.time() + 3500)
    return token


@tool(timeout=20)
async def sheets_read_range(spreadsheet_id: str, range_a1: str = "Sheet1") -> str:
    """Read a range from a Google Sheet.

    Args:
        spreadsheet_id: The sheet ID from the URL (between /d/ and /edit).
        range_a1: A1 notation, e.g. ``"Sheet1!A1:D10"`` or sheet name.

    Returns:
        JSON-encoded 2D array of cell values, or error string.

    Requires LARGESTACK_GOOGLE_SERVICE_ACCOUNT pointing to a JSON key file.
    The sheet must be shared with the service account's email.
    """
    sa = _load_service_account()
    if not sa:
        return "Error: LARGESTACK_GOOGLE_SERVICE_ACCOUNT env var not set or unreadable."
    token = await _get_access_token(sa)
    if not token:
        return "Error: failed to mint Google access token."

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{_SHEETS_API}/{spreadsheet_id}/values/{range_a1}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code == 404:
        return f"Sheet {spreadsheet_id} not found or service account lacks access."
    if r.status_code >= 400:
        return f"Sheets API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return "Sheets API returned non-JSON response."
    return json.dumps(body.get("values", []), indent=2)


@tool(timeout=20)
async def sheets_append_row(spreadsheet_id: str, range_a1: str, values: str) -> str:
    """Append a row to a Google Sheet.

    Args:
        spreadsheet_id: Sheet ID.
        range_a1: Where to append, e.g. ``"Sheet1!A:D"``.
        values: JSON-encoded list, e.g. ``'["alice", 42, "active"]'``.

    Returns:
        Success message with the updated range, or error string.
    """
    sa = _load_service_account()
    if not sa:
        return "Error: LARGESTACK_GOOGLE_SERVICE_ACCOUNT env var not set or unreadable."

    try:
        row = json.loads(values)
        if not isinstance(row, list):
            return "Error: values must be a JSON-encoded list."
    except json.JSONDecodeError as e:
        return f"Error: invalid values JSON: {e}"

    token = await _get_access_token(sa)
    if not token:
        return "Error: failed to mint Google access token."

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{_SHEETS_API}/{spreadsheet_id}/values/{range_a1}:append",
            headers={"Authorization": f"Bearer {token}"},
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [row]},
        )
    if r.status_code == 404:
        return f"Sheet {spreadsheet_id} not found or service account lacks access."
    if r.status_code >= 400:
        return f"Sheets API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return "Sheets API returned non-JSON response."
    return f"Appended to {body.get('updates', {}).get('updatedRange', range_a1)}"
