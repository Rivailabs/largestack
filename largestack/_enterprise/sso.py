"""SSO/OAuth2/OIDC integration for enterprise authentication.

Supported providers:
  - OIDC-compatible: Google, Microsoft (Azure AD), Okta, Auth0, WorkOS
  - SAML 2.0 (requires python3-saml or similar)
  - Local mock (testing)

Features:
  - JWT token validation (with signature verification when available)
  - Session management with TTL
  - Refresh token support
  - Role/group mapping from token claims
  - Session revocation (logout)
  - Multi-tenant support (tenant claim in token)
"""
from __future__ import annotations
import base64, json, logging, os, time, uuid
from typing import Any

log = logging.getLogger("largestack.sso")


class SSOError(Exception):
    """SSO authentication/authorization error."""
    pass


class Session:
    """An authenticated session."""
    def __init__(self, session_id: str, user_info: dict, ttl: float = 3600):
        self.session_id = session_id
        self.user_info = user_info
        self.created_at = time.time()
        self.ttl = ttl
        self.last_active = time.time()
        self.refresh_token = None
    
    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def refresh(self, ttl: float = None):
        """Refresh session — extend TTL."""
        self.created_at = time.time()
        self.last_active = time.time()
        if ttl is not None:
            self.ttl = ttl
    
    def touch(self):
        """Update last_active timestamp."""
        self.last_active = time.time()
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_info": self.user_info,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_active": self.last_active,
            "is_expired": self.is_expired,
        }


class SSOProvider:
    """SSO authentication provider with multi-backend support.
    
    Usage:
        sso = SSOProvider(
            provider="oidc",
            client_id="...",
            client_secret="...",
            issuer="https://accounts.google.com",
            jwks_url="https://www.googleapis.com/oauth2/v3/certs",
        )
        
        # Authenticate and create session
        user = await sso.authenticate(id_token)
        session_id = await sso.create_session(user, ttl=3600)
        
        # Validate later
        session = await sso.validate_session(session_id)
        if session and not session.is_expired:
            # Allow request
    """
    SUPPORTED_PROVIDERS = ("oidc", "workos", "okta", "auth0", "google", "azure", "mock")
    
    def __init__(self, provider: str = "mock", client_id: str = "",
                 client_secret: str = "", issuer: str = "",
                 jwks_url: str = "", default_ttl: float = 3600,
                 role_claim: str = "roles", tenant_claim: str = "tenant_id"):
        if provider not in self.SUPPORTED_PROVIDERS:
            raise SSOError(f"Unsupported provider: {provider}. Supported: {self.SUPPORTED_PROVIDERS}")
        
        self.provider = provider
        self.client_id = client_id or os.environ.get("LARGESTACK_SSO_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("LARGESTACK_SSO_CLIENT_SECRET", "")
        self.issuer = issuer or os.environ.get("LARGESTACK_SSO_ISSUER", "")
        self.jwks_url = jwks_url
        self.default_ttl = default_ttl
        self.role_claim = role_claim
        self.tenant_claim = tenant_claim

        # v0.5.0: pluggable session backend.
        # Default: in-memory (legacy behavior). Set LARGESTACK_SESSION_BACKEND=redis
        # for distributed sessions across workers.
        from largestack._enterprise.session_store import create_session_store
        self._session_store = create_session_store()
        # Legacy compatibility: tests/code may poke at self._sessions directly.
        # Keep it pointed at the in-memory store's dict for backwards compat.
        if hasattr(self._session_store, "_sessions"):
            self._sessions = self._session_store._sessions
        else:
            self._sessions: dict[str, Session] = {}

        self._jwks_cache: dict = {}
        self._jwks_cache_time: float = 0
    
    async def authenticate(self, token: str) -> dict:
        """Validate SSO token and return user info dict.
        
        Returns:
            {
                "user_id": str,
                "email": str,
                "name": str,
                "roles": [str],
                "tenant_id": str,
                "authenticated": bool,
                "provider": str,
                "raw_claims": dict,
            }
        
        Raises SSOError if token invalid.
        """
        if not token or not isinstance(token, str):
            raise SSOError("Invalid token format")
        
        if self.provider == "mock":
            return self._mock_authenticate(token)
        
        # For real providers: decode JWT
        claims = self._decode_jwt(token)
        self._validate_claims(claims)
        
        return self._build_user_info(claims)
    
    def _decode_jwt(self, token: str) -> dict:
        """Decode JWT. Uses pyjwt if available for full signature validation.
        
        v0.3.5 hardening: production env REFUSES unsigned/unverified decode.
        Set LARGESTACK_ENV=production to enforce. In dev, unsigned decode is allowed
        but always logs a warning.
        """
        env = os.environ.get("LARGESTACK_ENV", "development").lower()
        is_production = env == "production"
        
        try:
            import jwt as pyjwt
            # Full validation with JWKS
            if self.jwks_url:
                try:
                    jwks_client = pyjwt.PyJWKClient(self.jwks_url)
                    signing_key = jwks_client.get_signing_key_from_jwt(token)
                    claims = pyjwt.decode(
                        token, signing_key.key,
                        algorithms=["RS256", "ES256"],
                        audience=self.client_id,
                        issuer=self.issuer if self.issuer else None,
                    )
                    return claims
                except Exception as e:
                    log.warning(f"JWT signature validation failed: {e}")
                    if is_production:
                        # P0-5: never silently downgrade to unsigned decode in production
                        raise SSOError(
                            f"JWT signature validation failed and LARGESTACK_ENV=production. "
                            f"Refusing to decode without verification. Original error: {e}"
                        )
            
            # No JWKS configured OR JWKS validation failed in dev mode
            if is_production:
                raise SSOError(
                    "JWT verification requires `jwks_url` to be set in production "
                    "(LARGESTACK_ENV=production). Refusing to decode unverified token."
                )
            
            log.warning("Decoding JWT without signature verification (DEV ONLY)")
            try:
                return pyjwt.decode(token, options={"verify_signature": False})
            except Exception as e:
                raise SSOError(f"Invalid JWT: {e}")
        except ImportError:
            if is_production:
                raise SSOError(
                    "pyjwt is not installed and LARGESTACK_ENV=production. "
                    "Install pyjwt for production JWT verification."
                )
            log.warning("pyjwt not installed — using unsafe JWT parse (DEV ONLY)")
            return self._decode_jwt_unsafe(token)
    
    def _decode_jwt_unsafe(self, token: str) -> dict:
        """Unsafe JWT decode without signature verification."""
        parts = token.split(".")
        if len(parts) != 3:
            raise SSOError(f"Invalid JWT format: expected 3 parts, got {len(parts)}")
        try:
            payload_b64 = parts[1]
            # JWT uses URL-safe base64 without padding
            padding = 4 - len(payload_b64) % 4
            payload_b64 += "=" * padding
            payload = base64.urlsafe_b64decode(payload_b64)
            return json.loads(payload)
        except Exception as e:
            raise SSOError(f"Failed to decode JWT: {e}")
    
    def _validate_claims(self, claims: dict):
        """Validate required claims in JWT."""
        # Expiry check (if exp claim present)
        exp = claims.get("exp")
        if exp and exp < time.time():
            raise SSOError(f"Token expired at {exp}")
        
        # Issuer check (if configured)
        if self.issuer and claims.get("iss") != self.issuer:
            log.warning(f"Token issuer mismatch: expected {self.issuer}, got {claims.get('iss')}")
        
        # Audience check
        if self.client_id and "aud" in claims:
            aud = claims["aud"]
            if isinstance(aud, list):
                if self.client_id not in aud:
                    raise SSOError(f"Audience mismatch")
            elif aud != self.client_id:
                raise SSOError(f"Audience mismatch")
    
    def _build_user_info(self, claims: dict) -> dict:
        """Extract user info from validated claims."""
        user_id = (claims.get("sub") or claims.get("user_id") or
                   claims.get("email") or claims.get("preferred_username") or "")
        
        # Roles may be under different claim names
        roles = claims.get(self.role_claim, claims.get("groups", claims.get("role", [])))
        if isinstance(roles, str):
            roles = [roles]
        elif not isinstance(roles, list):
            roles = []
        
        tenant_id = claims.get(self.tenant_claim, claims.get("tid", claims.get("org_id", "")))
        
        return {
            "user_id": user_id,
            "email": claims.get("email", ""),
            "name": claims.get("name", claims.get("given_name", "")),
            "roles": roles,
            "tenant_id": tenant_id,
            "authenticated": True,
            "provider": self.provider,
            "raw_claims": claims,
        }
    
    def _mock_authenticate(self, token: str) -> dict:
        """Mock authentication for testing."""
        return {
            "user_id": f"user_{token[:8]}",
            "email": f"user_{token[:4]}@example.com",
            "name": "Mock User",
            "roles": ["operator"],
            "tenant_id": "tenant_default",
            "authenticated": True,
            "provider": "mock",
            "raw_claims": {},
        }
    
    async def create_session(self, user_info: dict, ttl: float = None) -> str:
        """Create an authenticated session. Returns session_id."""
        session_id = str(uuid.uuid4())
        session = Session(session_id, user_info, ttl=ttl or self.default_ttl)
        # v0.5.0: write through to session store (in-memory or Redis)
        self._session_store.put(session)
        # Legacy: also visible via _sessions dict for backwards compat
        if hasattr(self._session_store, "_sessions"):
            self._sessions = self._session_store._sessions
        else:
            self._sessions[session_id] = session
        log.info(f"SSO: session created for {user_info.get('user_id')}")
        return session_id

    async def validate_session(self, session_id: str) -> Session | None:
        """Get session by ID if still valid."""
        session = self._session_store.get(session_id)
        if not session:
            return None
        if session.is_expired:
            log.debug(f"SSO: session {session_id} expired")
            self._session_store.delete(session_id)
            return None
        session.touch()
        # Write back updated last_active timestamp (Redis: re-set with TTL)
        self._session_store.put(session)
        return session

    async def refresh_session(self, session_id: str, ttl: float = None) -> bool:
        """Extend session TTL."""
        session = self._session_store.get(session_id)
        if not session:
            return False
        session.refresh(ttl)
        self._session_store.put(session)
        return True

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke session (logout)."""
        deleted = self._session_store.delete(session_id)
        if deleted:
            log.info(f"SSO: session {session_id} revoked")
        return deleted

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user (force logout everywhere)."""
        all_sessions = self._session_store.all()
        to_remove = [
            s.session_id for s in all_sessions
            if s.user_info.get("user_id") == user_id
        ]
        for sid in to_remove:
            self._session_store.delete(sid)
        return len(to_remove)

    async def list_active_sessions(self, user_id: str = None) -> list[dict]:
        """List active (non-expired) sessions, optionally filtered by user."""
        self._prune_expired()
        sessions = self._session_store.all()
        if user_id:
            sessions = [s for s in sessions if s.user_info.get("user_id") == user_id]
        return [s.to_dict() for s in sessions]

    def _prune_expired(self):
        """Remove expired sessions."""
        self._session_store.cleanup_expired()
    
    def has_role(self, user_info: dict, role: str) -> bool:
        """Check if user has a specific role."""
        return role in (user_info.get("roles") or [])
    
    def has_any_role(self, user_info: dict, roles: list[str]) -> bool:
        """Check if user has at least one of the given roles."""
        user_roles = set(user_info.get("roles") or [])
        return bool(user_roles & set(roles))
    
    @property
    def stats(self) -> dict:
        self._prune_expired()
        return {
            "provider": self.provider,
            "active_sessions": len(self._sessions),
            "default_ttl_seconds": self.default_ttl,
            "issuer": self.issuer,
        }
