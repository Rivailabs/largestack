"""Dashboard auth middleware — API key based (env: LARGESTACK_DASHBOARD_KEY).

Defaults to deny-all in production. In development, if LARGESTACK_DASHBOARD_KEY is unset
AND LARGESTACK_ENV != "production", auth is bypassed with a loud warning logged once.

This is intentionally minimal — no JWT/OIDC. For real auth, wire to your IdP
in front of this server (Caddy/Cloudflare/Traefik with auth_request, etc.).
"""
from __future__ import annotations
import logging
import os
import secrets
from fastapi import Request

log = logging.getLogger("largestack.dashboard.auth")
_warned_once = False


def get_dashboard_api_key() -> str | None:
    """Read LARGESTACK_DASHBOARD_KEY from env. Returns None if unset."""
    return os.environ.get("LARGESTACK_DASHBOARD_KEY")


def is_production() -> bool:
    return os.environ.get("LARGESTACK_ENV", "development").lower() == "production"


def verify_api_key(request: Request) -> None:
    """FastAPI dependency. Raises HTTPException(401) on failure.

    Behavior:
    - If LARGESTACK_DASHBOARD_KEY is set: require X-API-Key header to match (constant-time compare).
    - If LARGESTACK_DASHBOARD_KEY is unset and LARGESTACK_ENV=production: deny all.
    - If LARGESTACK_DASHBOARD_KEY is unset and dev mode: allow with a one-time warning.
    """
    global _warned_once
    from fastapi import HTTPException

    expected = get_dashboard_api_key()
    if expected:
        provided = request.headers.get("X-API-Key", "")
        # Use compare_digest to avoid timing attacks
        if not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
        return

    # No key configured
    if is_production():
        raise HTTPException(
            status_code=401,
            detail="Dashboard requires authentication. Set LARGESTACK_DASHBOARD_KEY env var."
        )

    if not _warned_once:
        log.warning(
            "LARGESTACK_DASHBOARD_KEY is not set. Dashboard auth is disabled in development. "
            "Set LARGESTACK_DASHBOARD_KEY before deploying."
        )
        _warned_once = True
    return
