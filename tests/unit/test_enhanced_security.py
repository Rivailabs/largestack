"""Tests for enhanced security modules."""

import sys

sys.path.insert(0, ".")

# ═══ Network Policy ═══


def test_network_default_allows():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy()
    allowed, _ = p.check("https://example.com/path")
    assert allowed


def test_network_https_only():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(https_only=True)
    assert not p.check("http://example.com")[0]
    assert p.check("https://example.com")[0]


def test_network_method_restriction():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(allowed_methods=["GET"])
    assert p.check("https://example.com", method="GET")[0]
    assert not p.check("https://example.com", method="DELETE")[0]


def test_network_port_restriction():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(allowed_ports=[443])
    assert p.check("https://example.com")[0]  # 443 by default
    assert not p.check("http://example.com:8080")[0]


def test_network_wildcard_subdomain():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(deny_domains=["*"], allow_domains=["*.openai.com"])
    assert p.check("https://api.openai.com/v1")[0]
    assert p.check("https://cdn.openai.com")[0]
    assert not p.check("https://evil.com")[0]


def test_network_exact_domain():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(deny_domains=["*"], allow_domains=["api.anthropic.com"])
    assert p.check("https://api.anthropic.com/v1")[0]
    assert not p.check("https://other.anthropic.com")[0]


def test_network_ip_range_deny():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(deny_ip_ranges=["10.0.0.0/8"])
    assert not p.check("http://10.0.0.1")[0]  # In denied range
    assert p.check("http://8.8.8.8")[0]  # Not in denied range


def test_network_rate_limit():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(rate_limit_per_host=3, rate_window_seconds=60)
    url = "https://example.com"
    # First 3 allowed
    for _ in range(3):
        assert p.check(url)[0]
    # 4th blocked
    allowed, reason = p.check(url)
    assert not allowed
    assert "Rate limit" in reason


def test_network_public_only_preset():
    from largestack._security.network import public_only

    p = public_only()
    # Internal IPs denied
    assert not p.check("http://192.168.1.1")[0]
    assert not p.check("http://10.0.0.1")[0]
    assert not p.check("http://127.0.0.1")[0]
    # Public domain allowed
    assert p.check("https://api.openai.com")[0]


def test_network_lockdown_preset():
    from largestack._security.network import lockdown

    p = lockdown(["api.openai.com", "api.anthropic.com"])
    assert p.check("https://api.openai.com", method="GET")[0]
    assert not p.check("https://example.com")[0]


def test_network_bulk_check():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(deny_domains=["bad.com"])
    result = p.check_bulk(
        [
            "https://good.com/a",
            "https://bad.com/x",
            "https://ok.com/b",
        ]
    )
    assert len(result["allowed"]) == 2
    assert len(result["denied"]) == 1


def test_network_stats():
    from largestack._security.network import NetworkPolicy

    p = NetworkPolicy(allow_domains=["a.com"], deny_domains=["b.com"])
    s = p.stats
    assert s["allow_domains"] == 1
    assert s["deny_domains"] == 1


# ═══ Permissions ═══


def test_permissions_tuple_unpacking():
    from largestack._security.permissions import Permissions

    p = Permissions(can_send_email=False)
    allowed, reason = p.check("send_email")
    assert allowed is False
    assert "Email" in reason


def test_permissions_bool_truthy():
    from largestack._security.permissions import Permissions

    p = Permissions()
    # Default execute_code=True
    assert p.check("execute_code")
    # Default send_email=False
    assert not p.check("send_email")


def test_permissions_presets():
    from largestack._security.permissions import get_preset, PRESET_POLICIES

    strict = get_preset("strict")
    standard = get_preset("standard")
    trusted = get_preset("trusted")
    admin = get_preset("admin")

    # Strict blocks email, admin allows
    assert not strict.check("send_email")
    assert admin.check("send_email")

    # Trusted allows fs writes
    assert trusted.check("write_filesystem")
    assert not strict.check("write_filesystem")


def test_permissions_resource_limits():
    from largestack._security.permissions import Permissions

    p = Permissions(max_cost_per_run=1.0, max_tool_calls_per_run=10)
    # Within limits
    allowed, _ = p.check_resource_limits(current_cost=0.5, tool_calls=5)
    assert allowed
    # Over cost
    allowed, reason = p.check_resource_limits(current_cost=2.0, tool_calls=5)
    assert not allowed
    assert "Cost" in reason
    # Over tool calls
    allowed, reason = p.check_resource_limits(current_cost=0.5, tool_calls=20)
    assert not allowed


def test_permissions_domain_allowlist():
    from largestack._security.permissions import Permissions

    p = Permissions(allowed_domains=["openai.com", "anthropic.com"])
    assert p.check("network_request", domain="openai.com")
    assert not p.check("network_request", domain="evil.com")


def test_permissions_enforcer():
    from largestack._security.permissions import Permissions, PermissionEnforcer

    p = Permissions(can_send_email=False)
    e = PermissionEnforcer(p)
    try:
        e.enforce("send_email")
        assert False
    except PermissionError:
        pass
    assert e.violation_count == 1


def test_permissions_enforcer_stats():
    from largestack._security.permissions import Permissions, PermissionEnforcer

    p = Permissions()
    e = PermissionEnforcer(p)
    e.check("execute_code")
    e.check("send_email")  # denied
    s = e.stats
    assert s["total_checks"] == 2
    assert s["denied"] == 1
    assert s["allowed"] == 1


def test_permissions_preset_invalid():
    from largestack._security.permissions import get_preset

    try:
        get_preset("doesnt_exist")
        assert False
    except ValueError:
        pass


# ═══ Vault ═══


def test_vault_env_backend():
    import os
    from largestack._security.vault import SecretStore

    os.environ["LARGESTACK_TEST_SECRET"] = "super-secret-value"
    store = SecretStore(backend="env")
    val = store.get("LARGESTACK_TEST_SECRET")
    assert val == "super-secret-value"


def test_vault_cache():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory", ttl_seconds=60)
    store.set("KEY", "value")
    assert store.get("KEY") == "value"
    assert store.cache_size == 1


def test_vault_redact():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory")
    store.set("API_KEY", "sk-abc123def456")
    text = "Error with API_KEY=sk-abc123def456 in request"
    redacted = store.redact(text)
    assert "sk-abc123def456" not in redacted


def test_vault_redact_short_secrets_ignored():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory")
    store.set("SHORT", "ok")  # Too short
    text = "hello ok world"
    redacted = store.redact(text)
    # Short secrets shouldn't be redacted (false positive prevention)
    assert "ok" in redacted


def test_vault_rotate():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory")
    store.set("KEY", "old-value")
    store.rotate("KEY", "new-value")
    assert store.get("KEY") == "new-value"


def test_vault_redact_pattern():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory")
    store.add_redact_pattern("custom-secret-xyz")
    redacted = store.redact("contains custom-secret-xyz in output")
    assert "custom-secret-xyz" not in redacted


def test_vault_clear_cache():
    from largestack._security.vault import SecretStore

    store = SecretStore(backend="memory")
    store.set("A", "1")
    store.set("B", "2")
    assert store.cache_size == 2
    store.clear_cache()
    assert store.cache_size == 0
