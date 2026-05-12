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
    def __init__(self, secret: str = "largestack-default-key", max_age_seconds: float = 300):
        self._secret = secret.encode()
        self._max_age = max_age_seconds
        self._seen_nonces: set[str] = set()

    def sign_message(self, sender: str, receiver: str, content: str) -> SignedMessage:
        import os
        nonce = os.urandom(16).hex()
        ts = time.time()
        payload = f"{sender}:{receiver}:{content}:{ts}:{nonce}"
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        return SignedMessage(sender, receiver, content, ts, sig, nonce)

    def verify_message(self, msg: SignedMessage) -> tuple[bool, str]:
        # Replay protection
        if msg.nonce in self._seen_nonces:
            return False, "Replay attack: nonce already used"
        # Age check
        age = time.time() - msg.timestamp
        if age > self._max_age:
            return False, f"Message too old: {age:.0f}s > {self._max_age}s"
        # Signature verification
        payload = f"{msg.sender}:{msg.receiver}:{msg.content}:{msg.timestamp}:{msg.nonce}"
        expected = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(msg.signature, expected):
            return False, "Invalid signature — message tampered"
        self._seen_nonces.add(msg.nonce)
        return True, "Verified"
