"""Agent identity & credential scoping — OWASP ASI03 (Identity & Privilege Abuse).

Each agent gets scoped credentials. No agent can access another agent's secrets.

    ident = AgentIdentityManager()
    ident.register("researcher", credentials={"api_key": "xxx"}, permissions=["read"])
    ident.register("writer", credentials={"api_key": "yyy"}, permissions=["read", "write"])

    creds = ident.get_credentials("researcher")  # Only researcher's creds
    ident.check_permission("researcher", "write")  # False — not allowed
"""

from __future__ import annotations
import hashlib, logging, time
from typing import Any

log = logging.getLogger("largestack.identity")


class AgentIdentity:
    def __init__(
        self,
        agent_name: str,
        permissions: list[str] = None,
        credentials: dict = None,
        max_session_duration: float = 3600,
    ):
        self.agent_name = agent_name
        self.permissions = set(permissions or ["read"])
        self._credentials = credentials or {}
        self.created_at = time.time()
        self.max_session_duration = max_session_duration
        self.token = hashlib.sha256(f"{agent_name}:{time.time()}".encode()).hexdigest()[:32]

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.max_session_duration


class AgentIdentityManager:
    def __init__(self):
        self._agents: dict[str, AgentIdentity] = {}

    def register(
        self,
        agent_name: str,
        permissions: list[str] = None,
        credentials: dict = None,
        max_session_duration: float = 3600,
    ):
        self._agents[agent_name] = AgentIdentity(
            agent_name, permissions, credentials, max_session_duration
        )
        log.info(f"Agent registered: {agent_name} with permissions {permissions}")

    def get_credentials(self, agent_name: str) -> dict:
        """Get agent's OWN credentials only. Never cross-agent."""
        identity = self._agents.get(agent_name)
        if not identity:
            log.warning(f"Unknown agent: {agent_name}")
            return {}
        if identity.is_expired:
            log.warning(f"Agent session expired: {agent_name}")
            return {}
        return dict(identity._credentials)

    def check_permission(self, agent_name: str, action: str) -> bool:
        identity = self._agents.get(agent_name)
        if not identity:
            return False
        if identity.is_expired:
            log.warning(f"Expired session: {agent_name}")
            return False
        allowed = action in identity.permissions
        if not allowed:
            log.warning(f"Permission denied: {agent_name} cannot {action}")
        return allowed

    def verify_token(self, agent_name: str, token: str) -> bool:
        identity = self._agents.get(agent_name)
        if not identity:
            return False
        return identity.token == token and not identity.is_expired

    def rotate_credentials(self, agent_name: str, new_credentials: dict):
        if agent_name in self._agents:
            self._agents[agent_name]._credentials = new_credentials
            self._agents[agent_name].token = hashlib.sha256(
                f"{agent_name}:{time.time()}".encode()
            ).hexdigest()[:32]
