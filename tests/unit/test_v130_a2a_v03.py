"""v0.13.0: Tests for A2A v0.3 features (SSE streaming + signed cards)."""

from __future__ import annotations

import asyncio
import time

import pytest


# -------------------- TaskStreamEvent --------------------


def test_stream_event_sse_format():
    from largestack._a2a.v03 import TaskStreamEvent

    e = TaskStreamEvent(event="state_change", data={"state": "working"})
    sse = e.to_sse()
    assert sse.startswith("event: state_change\n")
    assert "data: " in sse
    assert sse.endswith("\n\n")
    # JSON parseable
    import json

    data_line = [l for l in sse.splitlines() if l.startswith("data: ")][0]
    parsed = json.loads(data_line[6:])
    assert parsed["state"] == "working"


# -------------------- StreamingA2AServer --------------------


@pytest.mark.asyncio
async def test_stream_task_emits_state_changes():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import StreamingA2AServer

    async def handler(input_text, task):
        return f"echo: {input_text}"

    server = StreamingA2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )

    events = []
    async for ev in server.stream_task("hello"):
        events.append(ev)

    # Expect: submitted state, working state, message, completed state, done
    event_types = [e.event for e in events]
    assert "state_change" in event_types
    assert "message" in event_types
    assert "done" in event_types

    # Final state should be 'completed'
    state_events = [e for e in events if e.event == "state_change"]
    states = [e.data.get("state") for e in state_events]
    assert "submitted" in states
    assert "working" in states
    assert "completed" in states


@pytest.mark.asyncio
async def test_stream_task_with_streaming_aware_handler():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import StreamingA2AServer

    async def streaming_handler(input_text, task, emit):
        # Emit two custom progress events
        await emit("progress", {"step": 1, "of": 3})
        await emit("progress", {"step": 2, "of": 3})
        await emit("progress", {"step": 3, "of": 3})
        return "done"

    server = StreamingA2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=streaming_handler,
    )

    events = []
    async for ev in server.stream_task("go"):
        events.append(ev)

    progress_events = [e for e in events if e.event == "progress"]
    assert len(progress_events) == 3
    assert progress_events[0].data["step"] == 1
    assert progress_events[2].data["step"] == 3


@pytest.mark.asyncio
async def test_stream_task_emits_error_on_failure():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import StreamingA2AServer

    async def broken(input_text, task):
        raise RuntimeError("boom")

    server = StreamingA2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=broken,
    )

    events = []
    async for ev in server.stream_task("x"):
        events.append(ev)

    assert any(e.event == "error" for e in events)
    state_events = [e for e in events if e.event == "state_change"]
    states = [e.data.get("state") for e in state_events]
    assert "failed" in states


@pytest.mark.asyncio
async def test_handle_streaming_request_returns_sse_strings():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import StreamingA2AServer

    async def handler(input_text, task):
        return f"echo: {input_text}"

    server = StreamingA2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )

    chunks = []
    async for sse in server.handle_streaming_request(
        "POST",
        "/tasks/sendSubscribe",
        {"input": "hi"},
    ):
        chunks.append(sse)

    full = "".join(chunks)
    assert "event: state_change" in full
    assert "event: done" in full


@pytest.mark.asyncio
async def test_handle_streaming_request_rejects_empty_input():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import StreamingA2AServer

    async def handler(input_text, task):
        return ""

    server = StreamingA2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )

    chunks = []
    async for sse in server.handle_streaming_request(
        "POST",
        "/tasks/sendSubscribe",
        {},
    ):
        chunks.append(sse)

    full = "".join(chunks)
    assert "event: error" in full


# -------------------- HS256 signed cards --------------------


def test_sign_and_verify_hs256_roundtrip():
    from largestack._a2a import AgentCard, AgentSkill
    from largestack._a2a.v03 import (
        sign_agent_card_hs256,
        verify_agent_card_hs256,
    )

    card = AgentCard(
        name="My Agent",
        description="d",
        url="u",
        skills=[AgentSkill(id="x", name="X", description="x")],
    )
    signed = sign_agent_card_hs256(
        card,
        secret="secret-key",
        kid="prod-2026",
    )
    ok, reason = verify_agent_card_hs256(signed, secret="secret-key")
    assert ok, reason


def test_hs256_rejects_wrong_secret():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import (
        sign_agent_card_hs256,
        verify_agent_card_hs256,
    )

    card = AgentCard(name="x", description="y", url="z")
    signed = sign_agent_card_hs256(card, secret="correct")
    ok, reason = verify_agent_card_hs256(signed, secret="wrong")
    assert not ok
    assert "mismatch" in reason


def test_hs256_rejects_expired_signature():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import (
        sign_agent_card_hs256,
        verify_agent_card_hs256,
    )

    card = AgentCard(name="x", description="y", url="z")
    signed = sign_agent_card_hs256(
        card,
        secret="s",
        ttl_seconds=-1,  # already expired
    )
    ok, reason = verify_agent_card_hs256(signed, secret="s")
    assert not ok
    assert "expired" in reason


def test_hs256_rejects_tampered_card():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import (
        sign_agent_card_hs256,
        verify_agent_card_hs256,
    )

    card = AgentCard(name="legit", description="d", url="u")
    signed = sign_agent_card_hs256(card, secret="s")
    # Tamper with the card after signing
    signed.card.name = "evil"
    ok, reason = verify_agent_card_hs256(signed, secret="s")
    assert not ok
    assert "mismatch" in reason


def test_signed_card_to_dict_roundtrip():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import (
        sign_agent_card_hs256,
        SignedAgentCard,
        verify_agent_card_hs256,
    )

    card = AgentCard(name="x", description="y", url="z")
    signed = sign_agent_card_hs256(card, secret="s")
    d = signed.to_dict()
    rebuilt = SignedAgentCard.from_dict(d)
    ok, _ = verify_agent_card_hs256(rebuilt, secret="s")
    assert ok


def test_sign_hs256_requires_secret():
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import sign_agent_card_hs256

    with pytest.raises(ValueError, match="secret"):
        sign_agent_card_hs256(
            AgentCard(name="x", description="y", url="z"),
            secret="",
        )


# -------------------- RS256 signed cards (optional dep) --------------------


def test_rs256_raises_clean_when_cryptography_missing():
    """If cryptography isn't installed, raise ImportError, not ImportError elsewhere."""
    import sys
    from largestack._a2a import AgentCard
    from largestack._a2a.v03 import sign_agent_card_rs256

    # Can't easily mock the import; if cryptography is installed,
    # this just verifies the function exists and is callable
    try:
        import cryptography  # noqa

        # cryptography IS installed — try a round trip
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        from largestack._a2a.v03 import (
            sign_agent_card_rs256,
            verify_agent_card_rs256,
        )

        card = AgentCard(name="x", description="y", url="z")
        signed = sign_agent_card_rs256(card, private_key_pem=priv_pem)
        ok, _ = verify_agent_card_rs256(signed, public_key_pem=pub_pem)
        assert ok
    except ImportError:
        # Confirms our code raises ImportError (the function existed)
        with pytest.raises(ImportError, match="cryptography"):
            sign_agent_card_rs256(
                AgentCard(name="x", description="y", url="z"),
                private_key_pem=b"fake",
            )


def test_canonical_json_is_stable():
    from largestack._a2a.v03 import _canonical_json

    a = _canonical_json({"b": 2, "a": 1})
    b = _canonical_json({"a": 1, "b": 2})
    assert a == b  # key order doesn't matter
