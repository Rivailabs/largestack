"""Shared URL validation for built-in tools (v0.3.12).

Used by:
  - http_tool.http_request
  - web.web_fetch          (was missing SSRF protection — same flaw)
  - browser.browser_navigate (was missing SSRF protection — same flaw)

The original v0.3.11 patch fixed http_tool.py only. The other two tools
shipped with the same SSRF vulnerability. This module is the single source
of truth so we don't repeat the fix in three places (and forget one).

Behavior:
  - Scheme allowlist: http/https only
  - Reject hosts that resolve to private/loopback/link-local/multicast/
    reserved/metadata IPs
  - Optional LARGESTACK_HTTP_ALLOWLIST="host1,host2" — when set, ONLY listed
    hosts are permitted (production-safe pinning)
"""

from __future__ import annotations
import ipaddress
import os
import socket
from urllib.parse import urlparse


def _get_allowlist() -> set[str] | None:
    raw = os.environ.get("LARGESTACK_HTTP_ALLOWLIST", "").strip()
    if not raw:
        return None
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _is_blocked_ip(ip: str) -> bool:
    """Block private, loopback, link-local, multicast, reserved, metadata IPs."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparsable → block
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or str(addr) in {"169.254.169.254", "fd00:ec2::254"}  # AWS/GCP/Azure metadata
    )


def validate_url(url: str) -> str | None:
    """Returns an error string if URL is invalid/blocked, else None."""
    if not isinstance(url, str) or not url:
        return "URL must be a non-empty string"
    if len(url) > 2048:
        return "URL too long (>2048 chars)"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return f"Failed to parse URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return f"Only http/https schemes allowed, got: {parsed.scheme!r}"

    host = (parsed.hostname or "").strip()
    if not host:
        return "URL has no host"

    # Allowlist mode (recommended for production)
    allowlist = _get_allowlist()
    if allowlist is not None:
        if host.lower() not in allowlist:
            return (
                f"Host {host!r} not in LARGESTACK_HTTP_ALLOWLIST. "
                "Set LARGESTACK_HTTP_ALLOWLIST to a comma-separated list of "
                "permitted hosts."
            )
        # Operator-allowlisted → trust them, skip IP checks.
        return None

    # Default: SSRF protection — resolve and reject private IPs.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except (socket.gaierror, socket.herror) as e:
        return f"DNS resolution failed: {e}"
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            return (
                f"Host {host!r} resolves to blocked IP {ip!r} "
                "(private/loopback/link-local/metadata). "
                "Set LARGESTACK_HTTP_ALLOWLIST to override for trusted hosts."
            )
    return None
