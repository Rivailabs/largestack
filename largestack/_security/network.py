"""Network security policies — URL/IP/port allow-deny with rate limiting."""

from __future__ import annotations
import re, logging, time, ipaddress, socket
from urllib.parse import urlparse
from collections import defaultdict, deque
from typing import Any

log = logging.getLogger("largestack.network")


class NetworkPolicy:
    """Fine-grained network access control.

    Supports:
      - URL/domain allowlist and denylist with wildcards
      - IP address allowlist (CIDR ranges)
      - Port restrictions
      - HTTP method restrictions (GET/POST/PUT/DELETE)
      - Per-endpoint rate limiting
      - Protocol restrictions (http vs https only)

    Patterns:
      "*.openai.com"         — any subdomain of openai.com
      "api.anthropic.com"    — exact hostname
      "*"                    — wildcard (deny all by default)
      "10.0.0.0/8"           — CIDR for IP ranges

        policy = NetworkPolicy(
            allow_domains=["*.openai.com", "api.anthropic.com"],
            deny_domains=["*.malicious.com"],
            allow_ip_ranges=["10.0.0.0/8"],
            allowed_ports=[80, 443],
            allowed_methods=["GET", "POST"],
            https_only=True,
            rate_limit_per_host=100,
        )
        allowed, reason = policy.check("https://api.openai.com/v1/chat")
    """

    def __init__(
        self,
        allow_domains: list[str] = None,
        deny_domains: list[str] = None,
        allow_ip_ranges: list[str] = None,
        deny_ip_ranges: list[str] = None,
        allowed_ports: list[int] = None,
        allowed_methods: list[str] = None,
        https_only: bool = False,
        rate_limit_per_host: int = 0,  # 0 = no limit
        rate_window_seconds: float = 60.0,
        resolve_dns: bool = True,
    ):
        self.resolve_dns = resolve_dns
        self.allow_domains = allow_domains or []
        self.deny_domains = deny_domains or []
        self.allowed_ports = allowed_ports or []
        self.allowed_methods = [m.upper() for m in (allowed_methods or [])]
        self.https_only = https_only
        self.rate_limit_per_host = rate_limit_per_host
        self.rate_window_seconds = rate_window_seconds

        # Parse CIDR ranges
        self._allow_ip_networks = []
        self._deny_ip_networks = []
        for cidr in allow_ip_ranges or []:
            try:
                self._allow_ip_networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as e:
                log.warning(f"Invalid CIDR {cidr}: {e}")
        for cidr in deny_ip_ranges or []:
            try:
                self._deny_ip_networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as e:
                log.warning(f"Invalid CIDR {cidr}: {e}")

        # Rate limiter state: host → deque of timestamps
        self._rate_tracker: dict[str, deque] = defaultdict(deque)
        self._violation_count = 0

    def check(self, url: str, method: str = "GET") -> tuple[bool, str]:
        """Check if a request is allowed. Returns (allowed, reason_if_denied)."""
        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Invalid URL: {e}"

        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        port = parsed.port or (443 if scheme == "https" else 80)

        # 1. HTTPS-only check
        if self.https_only and scheme != "https":
            self._violation_count += 1
            return False, f"HTTPS required, got {scheme}"

        # 2. Method check
        if self.allowed_methods and method.upper() not in self.allowed_methods:
            self._violation_count += 1
            return False, f"Method {method} not allowed. Allowed: {self.allowed_methods}"

        # 3. Port check
        if self.allowed_ports and port not in self.allowed_ports:
            self._violation_count += 1
            return False, f"Port {port} not allowed. Allowed: {self.allowed_ports}"

        # 4. IP range check (if host is IP address)
        if self._is_ip(host):
            try:
                ip = ipaddress.ip_address(host)
                # Check deny ranges
                for net in self._deny_ip_networks:
                    if ip in net:
                        self._violation_count += 1
                        return False, f"IP {host} in denied range {net}"
                # Check allow ranges (if any specified, must match)
                if self._allow_ip_networks:
                    if not any(ip in net for net in self._allow_ip_networks):
                        self._violation_count += 1
                        return False, f"IP {host} not in any allowed range"
            except ValueError:
                pass

        # 4b. SSRF: when deny IP ranges are set, also guard *hostnames* — the
        # IP-literal check above is trivially bypassed by a name that resolves
        # to an internal address (localhost, metadata.google.internal,
        # 169.254.169.254.nip.io). Name-based blocks need no DNS; the resolved-IP
        # check catches rebinding tricks in real deployments (fail-open on a DNS
        # error so offline environments aren't broken).
        if self._deny_ip_networks and host and not self._is_ip(host):
            lowered = host.lower().rstrip(".")
            if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
                self._violation_count += 1
                return False, f"Host {host} names an internal network (blocked)"
            if self.resolve_dns:
                try:
                    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
                    resolved = {info[4][0] for info in infos}
                except OSError:
                    resolved = set()  # fail-open on resolution failure
                for addr in resolved:
                    try:
                        ip = ipaddress.ip_address(addr)
                    except ValueError:
                        continue
                    for net in self._deny_ip_networks:
                        if ip in net:
                            self._violation_count += 1
                            return False, f"Host {host} resolves to {addr} in denied range {net}"

        # 5. Domain check
        if self.deny_domains:
            for pattern in self.deny_domains:
                if self._host_matches(host, pattern):
                    # Check if explicitly re-allowed
                    if any(self._host_matches(host, a) for a in self.allow_domains):
                        pass  # Allow overrides
                    else:
                        self._violation_count += 1
                        return False, f"Domain {host} denied by pattern {pattern}"

        # 6. Allow-only mode (default-deny)
        if "*" in self.deny_domains or (self.allow_domains and not self.deny_domains):
            if not any(self._host_matches(host, p) for p in self.allow_domains):
                self._violation_count += 1
                return False, f"Domain {host} not in allowlist"

        # 7. Rate limiting
        if self.rate_limit_per_host > 0:
            now = time.monotonic()
            # Prune old timestamps
            dq = self._rate_tracker[host]
            cutoff = now - self.rate_window_seconds
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= self.rate_limit_per_host:
                self._violation_count += 1
                return False, (
                    f"Rate limit: {self.rate_limit_per_host}/{self.rate_window_seconds}s "
                    f"for host {host}"
                )

            dq.append(now)

        return True, ""

    def check_bulk(self, urls: list[str], method: str = "GET") -> dict:
        """Check multiple URLs at once. Returns {allowed: [...], denied: [...]}."""
        allowed = []
        denied = []
        for url in urls:
            ok, reason = self.check(url, method)
            if ok:
                allowed.append(url)
            else:
                denied.append({"url": url, "reason": reason})
        return {"allowed": allowed, "denied": denied}

    def get_violations(self, urls: list[str], method: str = "GET") -> list[dict]:
        """Get denial list with reasons for a batch of URLs."""
        return self.check_bulk(urls, method)["denied"]

    @staticmethod
    def _host_matches(host: str, pattern: str) -> bool:
        """Match hostname against wildcard pattern."""
        if not host:
            return False
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            # "*.openai.com" matches api.openai.com, openai.com
            suffix = pattern[1:]  # ".openai.com"
            base = pattern[2:]  # "openai.com"
            return host.endswith(suffix) or host == base
        return host.lower() == pattern.lower()

    @staticmethod
    def _is_ip(host: str) -> bool:
        """Check if host is an IP address (v4 or v6)."""
        try:
            ipaddress.ip_address(host)
            return True
        except (ValueError, TypeError):
            return False

    def add_allow_domain(self, pattern: str):
        self.allow_domains.append(pattern)

    def add_deny_domain(self, pattern: str):
        self.deny_domains.append(pattern)

    @property
    def stats(self) -> dict:
        return {
            "allow_domains": len(self.allow_domains),
            "deny_domains": len(self.deny_domains),
            "allow_ip_ranges": len(self._allow_ip_networks),
            "deny_ip_ranges": len(self._deny_ip_networks),
            "allowed_ports": self.allowed_ports,
            "allowed_methods": self.allowed_methods,
            "https_only": self.https_only,
            "rate_limit_per_host": self.rate_limit_per_host,
            "violation_count": self._violation_count,
        }


# Preset policies
def public_only() -> NetworkPolicy:
    """Allow only common public APIs, block internal networks."""
    return NetworkPolicy(
        allow_domains=["*"],
        deny_ip_ranges=[
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "127.0.0.0/8",
            "169.254.0.0/16",  # RFC1918 + loopback + link-local
            "::1/128",
            "fc00::/7",  # IPv6 loopback + unique-local
        ],
        https_only=True,
    )


def lockdown(allowed_domains: list[str]) -> NetworkPolicy:
    """Default-deny, only specified domains allowed."""
    return NetworkPolicy(
        allow_domains=allowed_domains,
        deny_domains=["*"],
        https_only=True,
        allowed_methods=["GET", "POST"],
    )
