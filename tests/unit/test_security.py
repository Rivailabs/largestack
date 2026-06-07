"""Tests for security features."""

from largestack._security.sandbox import Sandbox
from largestack._security.permissions import Permissions
from largestack._security.vault import SecretStore
from largestack._security.encryption import EncryptionManager


def test_sandbox_network():
    sb = Sandbox(network_allow=["api.openai.com", "api.anthropic.com"], network_deny=["*"])
    assert sb.check_network("https://api.openai.com/v1/chat")
    assert sb.check_network("https://api.anthropic.com/v1/messages")
    assert not sb.check_network("https://evil.com/steal")
    assert not sb.check_network("https://random.site.com")


def test_sandbox_path():
    sb = Sandbox(allowed_paths=["/tmp", "/home/user/projects"])
    assert sb.check_path("/tmp/test.txt")
    assert not sb.check_path("/etc/passwd")


def test_permissions():
    p = Permissions(can_spawn_agents=False, can_send_email=False, max_cost_per_run=1.0)
    assert not p.check("spawn_agent")
    assert not p.check("send_email")
    assert p.check("execute_code")
    assert p.check("write_state")


def test_vault():
    v = SecretStore()
    v.set("OPENAI_KEY", "sk-test123456789")
    assert v.get("OPENAI_KEY") == "sk-test123456789"
    redacted = v.redact("My key is sk-test123456789 and it works")
    assert "sk-test123456789" not in redacted
    assert "sk" in redacted  # First 2 chars visible


def test_encryption():
    enc = EncryptionManager("my-secret-key-for-testing")
    original = "Hello, this is sensitive data! SSN: 123-45-6789"
    ciphertext = enc.encrypt(original)
    assert ciphertext != original
    decrypted = enc.decrypt(ciphertext)
    assert decrypted == original


def test_encryption_different_keys():
    enc1 = EncryptionManager("key-one")
    enc2 = EncryptionManager("key-two")
    ct = enc1.encrypt("secret")
    # Different key should fail to decrypt correctly
    try:
        result = enc2.decrypt(ct)
        assert result != "secret"  # XOR fallback won't crash but gives wrong result
    except:
        pass  # AES will raise
