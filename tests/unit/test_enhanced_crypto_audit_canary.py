"""Tests for enhanced encryption, audit, canary modules."""
import os, sys, tempfile, time; sys.path.insert(0, ".")


def tmp_db(name: str = "t.db") -> str:
    return os.path.join(tempfile.mkdtemp(), name)


# ═══ Encryption ═══

def test_encrypt_decrypt_roundtrip():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="my-test-key-32-bytes-padded-0000")
    ct = enc.encrypt("hello world")
    pt = enc.decrypt(ct)
    assert pt == "hello world"

def test_encrypt_different_nonces():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="testkey")
    ct1 = enc.encrypt("same text")
    ct2 = enc.encrypt("same text")
    # Different nonces → different ciphertext even for same plaintext
    assert ct1 != ct2
    assert enc.decrypt(ct1) == enc.decrypt(ct2) == "same text"

def test_encrypt_key_rotation():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="original")
    ct_old = enc.encrypt("secret1")
    
    new_version = enc.rotate_key()
    assert new_version == 2
    
    ct_new = enc.encrypt("secret2")
    # Both decryptable (old key preserved)
    assert enc.decrypt(ct_old) == "secret1"
    assert enc.decrypt(ct_new) == "secret2"

def test_encrypt_retire_key_after_reencryption():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="v1")
    ct = enc.encrypt("data")
    enc.rotate_key()
    # Can still decrypt old ciphertext
    assert enc.decrypt(ct) == "data"
    # Retiring current key should fail
    try:
        enc.retire_key(enc._current_version)
        assert False
    except ValueError:
        pass

def test_hash_functions():
    from largestack._security.encryption import EncryptionManager
    h1 = EncryptionManager.hash_sha256("hello")
    h2 = EncryptionManager.hash_sha256("hello")
    h3 = EncryptionManager.hash_sha256("world")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256 hex

def test_hmac_sign_verify():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="shared-secret")
    sig = enc.hmac_sign("my message")
    assert enc.hmac_verify("my message", sig)
    assert not enc.hmac_verify("tampered", sig)

def test_password_hashing():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="mk")
    hashed = enc.hash_password("user-password")
    assert enc.verify_password("user-password", hashed)
    assert not enc.verify_password("wrong-password", hashed)

def test_password_hash_is_salted():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="mk")
    h1 = enc.hash_password("same")
    h2 = enc.hash_password("same")
    # Different salts → different hashes for same password
    assert h1 != h2
    # But both verify
    assert enc.verify_password("same", h1)
    assert enc.verify_password("same", h2)

def test_encrypt_stats():
    from largestack._security.encryption import EncryptionManager
    enc = EncryptionManager(key="k")
    enc.encrypt("a")
    enc.decrypt(enc.encrypt("b"))
    s = enc.stats
    assert s["operation_count"] >= 3
    assert s["current_version"] == 1


# ═══ Audit Trail ═══

def test_audit_basic_log():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("agent.run", "execute", agent_name="bot", cost=0.01, trace_id="t1")
    a.log("tool.call", "search", agent_name="bot")
    assert a.count() == 2
    assert a.count(agent_name="bot") == 2

def test_audit_integrity_chain():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("e1", "a1")
    a.log("e2", "a2")
    a.log("e3", "a3")
    ok, broken = a.verify_integrity()
    assert ok, f"Chain broken at {broken}"

def test_audit_integrity_detects_tampering():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("e1", "a1", cost=1.0)
    a.log("e2", "a2", cost=2.0)
    a.log("e3", "a3", cost=3.0)
    # Manually tamper with a row
    a.db.execute("UPDATE audit_log SET cost=99.0 WHERE id=1")
    a.db.commit()
    ok, broken = a.verify_integrity()
    assert not ok
    assert broken == 1

def test_audit_query_filters():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("agent.run", "execute", agent_name="bot1", user_id="alice")
    a.log("agent.run", "execute", agent_name="bot2", user_id="alice")
    a.log("tool.call", "search", agent_name="bot1", user_id="bob")
    
    # By agent
    bot1 = a.query(agent_name="bot1")
    assert len(bot1) == 2
    # By event type
    runs = a.query(event_type="agent.run")
    assert len(runs) == 2
    # By user
    alice = a.query(user_id="alice")
    assert len(alice) == 2

def test_audit_trace_aggregation():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("agent.run", "start", trace_id="t-123")
    a.log("tool.call", "search", trace_id="t-123")
    a.log("agent.run", "end", trace_id="t-123")
    events = a.get_events_for_trace("t-123")
    assert len(events) == 3

def test_audit_actions_by_user():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("e", "search", user_id="alice", cost=0.10)
    a.log("e", "search", user_id="alice", cost=0.20)
    a.log("e", "scrape", user_id="alice", cost=0.05)
    actions = a.get_actions_by_user("alice")
    assert actions["search"]["count"] == 2
    assert abs(actions["search"]["total_cost"] - 0.30) < 0.001

def test_audit_stats():
    from largestack._enterprise.audit import AuditTrail
    a = AuditTrail(tmp_db("audit.db"))
    a.log("e", "a", agent_name="bot", user_id="u1", cost=1.0)
    a.log("e", "a", agent_name="bot", user_id="u2", cost=2.0)
    s = a.stats
    assert s["total_entries"] == 2
    assert s["unique_agents"] == 1
    assert s["unique_users"] == 2
    assert s["total_cost"] == 3.0


# ═══ Canary ═══

def test_canary_starts_at_first_stage():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment()
    assert c.current_percentage == 0.01

def test_canary_advances_with_good_metrics():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=10)
    for _ in range(20):
        c.record_result("new", True, latency_ms=100)
    advanced = c.advance()
    assert advanced
    assert c.current_percentage > 0.01

def test_canary_does_not_advance_without_samples():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=50)
    for _ in range(5):  # Not enough
        c.record_result("new", True)
    advanced = c.advance()
    assert not advanced

def test_canary_rollback_on_high_failure():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=10, rollback_threshold=0.85)
    c.advance()  # At stage 2
    for _ in range(30):
        c.record_result("new", False, error_type="timeout")
    assert c.should_rollback()

def test_canary_error_burst_rollback():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=10)
    # Many successes then sudden burst
    for _ in range(30):
        c.record_result("new", True)
    for _ in range(10):  # >5 errors → burst detected
        c.record_result("new", False, error_type="500")
    assert c.should_rollback()

def test_canary_latency_regression_blocks_advance():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=10, latency_regression_factor=1.5)
    # Old version: 100ms
    for _ in range(20):
        c.record_result("old", True, latency_ms=100)
    # New version: 300ms (3x slower, beyond 1.5x threshold)
    for _ in range(20):
        c.record_result("new", True, latency_ms=300)
    advanced = c.advance()
    assert not advanced  # Blocked by latency regression

def test_canary_force_complete():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment()
    c.force_complete()
    assert c.current_percentage == 1.0

def test_canary_stage_history():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment(min_samples_per_stage=10)
    for _ in range(20):
        c.record_result("new", True)
    c.advance()
    hist = c.stats["stage_history"]
    assert len(hist) >= 1
    assert hist[0]["from_stage"] == 0
    assert hist[0]["to_stage"] == 1

def test_canary_stats_metrics():
    from largestack._enterprise.canary import CanaryDeployment
    c = CanaryDeployment()
    for _ in range(10):
        c.record_result("new", True, latency_ms=50)
        c.record_result("old", True, latency_ms=60)
    s = c.stats
    assert s["new_version"]["samples"] == 10
    assert s["old_version"]["samples"] == 10
    assert s["new_version"]["success_rate"] == 1.0
