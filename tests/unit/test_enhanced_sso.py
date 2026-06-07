"""Tests for enhanced SSO provider."""

import asyncio, base64, json, sys, time

sys.path.insert(0, ".")


def make_test_jwt(claims: dict) -> str:
    """Create an unsigned JWT for testing (header.payload.sig)."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = "sig"  # Not verified in mock mode
    return f"{header}.{payload}.{sig}"


def test_sso_mock_authenticate():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock")
    user = asyncio.run(sso.authenticate("test-token-abc12345"))
    assert user["authenticated"]
    assert user["user_id"].startswith("user_")
    assert user["provider"] == "mock"


def test_sso_invalid_token_raises():
    from largestack._enterprise.sso import SSOProvider, SSOError

    sso = SSOProvider(provider="mock")
    try:
        asyncio.run(sso.authenticate(""))
        assert False
    except SSOError:
        pass


def test_sso_unsupported_provider_raises():
    from largestack._enterprise.sso import SSOProvider, SSOError

    try:
        SSOProvider(provider="bogus")
        assert False
    except SSOError:
        pass


def test_sso_session_lifecycle():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock", default_ttl=3600)
    user = asyncio.run(sso.authenticate("abc12345"))
    sid = asyncio.run(sso.create_session(user))

    # Validate
    session = asyncio.run(sso.validate_session(sid))
    assert session is not None
    assert not session.is_expired

    # Revoke
    assert asyncio.run(sso.revoke_session(sid))
    assert asyncio.run(sso.validate_session(sid)) is None


def test_sso_session_expires():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock", default_ttl=0.01)  # 10ms TTL
    user = asyncio.run(sso.authenticate("abc12345"))
    sid = asyncio.run(sso.create_session(user, ttl=0.01))
    time.sleep(0.05)
    session = asyncio.run(sso.validate_session(sid))
    # Expired session returns None
    assert session is None


def test_sso_refresh_extends_session():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock")
    user = asyncio.run(sso.authenticate("abc12345"))
    sid = asyncio.run(sso.create_session(user, ttl=0.1))

    # Refresh
    ok = asyncio.run(sso.refresh_session(sid, ttl=3600))
    assert ok
    session = asyncio.run(sso.validate_session(sid))
    assert session is not None
    assert session.ttl == 3600


def test_sso_revoke_all_user_sessions():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock")
    # Create 3 sessions for same user
    for i in range(3):
        user = {"user_id": "alice", "provider": "mock", "roles": [], "email": ""}
        asyncio.run(sso.create_session(user))

    count = asyncio.run(sso.revoke_all_user_sessions("alice"))
    assert count == 3
    remaining = asyncio.run(sso.list_active_sessions("alice"))
    assert len(remaining) == 0


def test_sso_role_check():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock")
    user = {"roles": ["admin", "developer"]}
    assert sso.has_role(user, "admin")
    assert not sso.has_role(user, "viewer")
    assert sso.has_any_role(user, ["viewer", "developer"])
    assert not sso.has_any_role(user, ["viewer", "reader"])


def test_sso_jwt_decode_unsafe():
    """Test JWT decoding without signature verification."""
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="oidc")
    token = make_test_jwt(
        {
            "sub": "user-123",
            "email": "alice@example.com",
            "name": "Alice",
            "roles": ["admin"],
            "exp": int(time.time()) + 3600,
        }
    )
    user = asyncio.run(sso.authenticate(token))
    assert user["user_id"] == "user-123"
    assert user["email"] == "alice@example.com"
    assert "admin" in user["roles"]


def test_sso_jwt_expired_rejected():
    from largestack._enterprise.sso import SSOProvider, SSOError

    sso = SSOProvider(provider="oidc")
    expired_token = make_test_jwt(
        {
            "sub": "user-1",
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
    )
    try:
        asyncio.run(sso.authenticate(expired_token))
        assert False
    except SSOError as e:
        assert "expired" in str(e).lower()


def test_sso_malformed_jwt_rejected():
    from largestack._enterprise.sso import SSOProvider, SSOError

    sso = SSOProvider(provider="oidc")
    try:
        asyncio.run(sso.authenticate("not.a.jwt.at.all"))
        assert False
    except SSOError:
        pass


def test_sso_custom_role_claim():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="oidc", role_claim="groups")
    token = make_test_jwt(
        {
            "sub": "u1",
            "groups": ["engineering", "admins"],
            "exp": int(time.time()) + 3600,
        }
    )
    user = asyncio.run(sso.authenticate(token))
    assert "engineering" in user["roles"]


def test_sso_tenant_claim():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="oidc")
    token = make_test_jwt(
        {
            "sub": "u1",
            "tenant_id": "acme-corp",
            "exp": int(time.time()) + 3600,
        }
    )
    user = asyncio.run(sso.authenticate(token))
    assert user["tenant_id"] == "acme-corp"


def test_sso_stats():
    from largestack._enterprise.sso import SSOProvider

    sso = SSOProvider(provider="mock")
    user = asyncio.run(sso.authenticate("abc12345"))
    asyncio.run(sso.create_session(user))
    asyncio.run(sso.create_session(user))
    s = sso.stats
    assert s["active_sessions"] == 2
    assert s["provider"] == "mock"
