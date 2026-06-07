"""Tests for mTLS certificate management."""

import os, sys, tempfile

sys.path.insert(0, ".")


def tmp_dir():
    return tempfile.mkdtemp()


def test_stub_ca_init():
    from largestack._security.mtls import MTLSManager

    m = MTLSManager(ca_dir=tmp_dir())
    result = m.init_ca()
    assert result["status"] in ("created", "created_stub")


def test_issue_cert():
    from largestack._security.mtls import MTLSManager

    m = MTLSManager(ca_dir=tmp_dir())
    m.init_ca()
    cert = m.issue_cert("agent-research")
    assert cert.agent_name == "agent-research"
    assert cert.status == "active"
    assert not cert.is_expired


def test_rotate_cert():
    from largestack._security.mtls import MTLSManager

    m = MTLSManager(ca_dir=tmp_dir())
    m.init_ca()
    old = m.issue_cert("agent-a")
    new = m.rotate_cert("agent-a")
    assert new.cert_id != old.cert_id
    # Old should be rotated
    certs = m._certs["agent-a"]
    assert certs[0].status == "rotated"
    assert certs[1].status == "active"


def test_revoke_cert():
    from largestack._security.mtls import MTLSManager

    m = MTLSManager(ca_dir=tmp_dir())
    m.init_ca()
    cert = m.issue_cert("agent-x")
    assert m.is_valid(cert.cert_id)
    m.revoke_cert(cert.cert_id)
    assert not m.is_valid(cert.cert_id)


def test_state_persistence():
    from largestack._security.mtls import MTLSManager

    d = tmp_dir()
    m1 = MTLSManager(ca_dir=d)
    m1.init_ca()
    m1.issue_cert("agent-1")

    m2 = MTLSManager(ca_dir=d)
    assert len(m2._certs.get("agent-1", [])) == 1


def test_stats():
    from largestack._security.mtls import MTLSManager

    m = MTLSManager(ca_dir=tmp_dir())
    m.init_ca()
    m.issue_cert("a")
    m.issue_cert("b")
    s = m.stats
    assert s["total_certs"] == 2
    assert s["agents"] == 2
