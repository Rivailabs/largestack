"""Inter-agent authentication — OWASP ASI07 (Insecure Inter-Agent Communication).

Signs and verifies messages between agents using HMAC-SHA256.

    auth = InterAgentAuth(secret="shared-secret-key")
    signed = auth.sign_message("agent1", "agent2", "Hello")
    verified = auth.verify_message(signed)  # True if not tampered
"""
from __future__ import annotations
import hashlib, hmac, json, time, logging
from typing import Any

log = logging.getLogger("largestack.inter_agent_auth")

class SignedMessage:
    def __init__(self, sender: str, receiver: str, content: str,
                 timestamp: float, signature: str, nonce: str):
        self.sender = sender
        self.receiver = receiver
        self.content = content
        self.timestamp = timestamp
        self.signature = signature
        self.nonce = nonce

class InterAgentAuth:
    def __init__(self, secret: str | None = None, max_age_seconds: float = 300):
        # v1.1.1: no public default key. A hardcoded "largestack-default-key"
        # meant anyone could forge messages. Require an explicit secret (arg or
        # LARGESTACK_INTER_AGENT_SECRET); otherwise generate a random per-process
        # secret (cross-process verification then fails until a shared secret is set).
        import os, secrets as _secrets
        if secret is None:
            secret = os.environ.get("LARGESTACK_INTER_AGENT_SECRET")
        if not secret:
            secret = _secrets.token_hex(32)
            log.warning("InterAgentAuth: no shared secret provided — set "
                        "LARGESTACK_INTER_AGENT_SECRET or pass secret=. Using a random "
                        "per-process secret; cross-process verification will fail until shared.")
        self._secret = secret.encode()
        self._max_age = max_age_seconds
        # nonce -> message timestamp, pruned to the freshness window to bound memory
        self._seen_nonces: dict[str, float] = {}

    def sign_message(self, sender: str, receiver: str, content: str) -> SignedMessage:
        import os
        nonce = os.urandom(16).hex()
        ts = time.time()
        payload = f"{sender}:{receiver}:{content}:{ts}:{nonce}"
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        return SignedMessage(sender, receiver, content, ts, sig, nonce)

    def verify_message(self, msg: SignedMessage) -> tuple[bool, str]:
        now = time.time()
        # Prune nonces outside the freshness window (older messages are rejected
        # by the age check anyway) so the replay set can't grow unbounded.
        if self._seen_nonces:
            cutoff = now - self._max_age
            self._seen_nonces = {n: t for n, t in self._seen_nonces.items() if t >= cutoff}
        # Replay protection
        if msg.nonce in self._seen_nonces:
            return False, "Replay attack: nonce already used"
        # Age check
        age = now - msg.timestamp
        if age > self._max_age:
            return False, f"Message too old: {age:.0f}s > {self._max_age}s"
        # Signature verification
        payload = f"{msg.sender}:{msg.receiver}:{msg.content}:{msg.timestamp}:{msg.nonce}"
        expected = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(msg.signature, expected):
            return False, "Invalid signature — message tampered"
        self._seen_nonces[msg.nonce] = msg.timestamp
        return True, "Verified"
