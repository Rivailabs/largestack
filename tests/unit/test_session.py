"""Tests for session management."""

import sys, os, tempfile

sys.path.insert(0, ".")
from largestack._core.session import SessionStore


def test_session_save_load():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "hello")
    ss.save("u1", "assistant", "hi there")
    h = ss.load("u1")
    assert len(h) == 2 and h[0]["content"] == "hello"


def test_session_multiple_users():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "msg1")
    ss.save("u2", "user", "msg2")
    assert len(ss.load("u1")) == 1 and len(ss.load("u2")) == 1


def test_session_list():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "a")
    ss.save("u2", "user", "b")
    sessions = ss.list_sessions()
    assert len(sessions) == 2


def test_session_delete():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "x")
    ss.delete("u1")
    assert len(ss.load("u1")) == 0


def test_session_cleanup():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "old")
    ss.cleanup_expired(max_age_hours=0)  # Expire everything
    assert len(ss.load("u1")) == 0


def test_session_export():
    ss = SessionStore("sqlite", os.path.join(tempfile.mkdtemp(), "s.db"))
    ss.save("u1", "user", "hello")
    ss.save("u1", "assistant", "hi")
    exported = ss.export_session("u1")
    assert len(exported) == 2 and exported[0]["role"] == "user"
