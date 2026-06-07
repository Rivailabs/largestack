"""Tests for the v1.1.1 Phase-1 gap-closing work (see release_evidence/)."""
from __future__ import annotations
import asyncio
import os
import tempfile

import pytest


# ---- RAG: BM25 stemming (refund ↔ Refunds) ----
def test_bm25_stemming_matches_inflections():
    from largestack import create_rag
    rag = create_rag(["Refunds are available within 30 days.", "Warranty covers 12 months."], top_k=1)
    assert "30 days" in rag.retrieve("refund policy")[0]["text"]        # refund→refund(s)
    assert "Warranty" in rag.retrieve("warranties")[0]["text"]          # warranties→warranti? still matches warranty


def test_rag_dense_auto_flag_accepted():
    from largestack._rag.pipeline import RAGPipeline
    # dense="auto" must not raise even if sentence-transformers is absent (BM25 fallback)
    rag = RAGPipeline(["doc one", "doc two"], dense="auto", top_k=1)
    assert rag.retrieve("one")  # still returns BM25 results


# ---- Structured output: Ollama native `format` param ----
def test_build_native_params_ollama_format():
    from largestack._core.structured import build_native_params
    params = build_native_params("ollama/qwen2.5:0.5b", {"type": "object", "properties": {"x": {"type": "string"}}})
    assert "format" in params and params["format"]["type"] == "object"


def test_ollama_provider_sends_format_in_body():
    """Behavioral: the `format` schema must reach the Ollama /api/chat request body."""
    from largestack._core.providers.ollama_prov import OllamaProvider
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"message": {"content": "{}"}, "done": True,
                    "prompt_eval_count": 1, "eval_count": 1}

    class _Client:
        async def post(self, path, json=None):
            captured["body"] = json
            return _Resp()

    p = OllamaProvider()
    p._c = _Client()
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    asyncio.run(p.chat([{"role": "user", "content": "hi"}], "ollama/qwen2.5:0.5b", format=schema))
    assert captured["body"]["format"] == schema


# ---- ML guards: umbrella flag ----
def test_ml_guards_umbrella_flag(monkeypatch):
    from largestack._guard.config import ml_guards_enabled
    monkeypatch.delenv("LARGESTACK_ENABLE_NLI_GUARD", raising=False)
    monkeypatch.delenv("LARGESTACK_ENABLE_ML_GUARDS", raising=False)
    assert ml_guards_enabled("LARGESTACK_ENABLE_NLI_GUARD") is False
    monkeypatch.setenv("LARGESTACK_ENABLE_ML_GUARDS", "1")
    assert ml_guards_enabled("LARGESTACK_ENABLE_NLI_GUARD") is True       # umbrella turns it on
    assert ml_guards_enabled("LARGESTACK_ENABLE_ML_PII") is True


# ---- SIEM exporter ----
def test_siem_export_cef_and_json():
    d = tempfile.mkdtemp()
    from largestack._enterprise.audit import AuditTrail
    from largestack._enterprise.siem import SiemExporter
    adb = os.path.join(d, "audit.db")
    a = AuditTrail(adb)
    a.log("agent.run", "completed", agent_name="bot", user_id="alice", cost=0.01, trace_id="t1")
    a.log("agent.run", "failed", agent_name="bot", user_id="eve", trace_id="t2")
    out = os.path.join(d, "out.cef")
    n = SiemExporter(audit_db=adb, fmt="cef").export_file(out)
    text = open(out).read()
    assert n == 2 and text.startswith("CEF:0|") and "duser=alice" in text
    outj = os.path.join(d, "out.jsonl")
    SiemExporter(audit_db=adb, fmt="json").export_file(outj)
    import json
    assert json.loads(open(outj).readline())["action"] == "completed"


# ---- Output sanitizer (LLM05) ----
def test_output_sanitizer_html_and_scan():
    from largestack._guard.output_sanitizer import OutputSanitizer
    s = OutputSanitizer()
    payload = "<script>steal()</script> click <a onclick='x'>here</a> javascript:evil()"
    assert "script_tag" in s.scan(payload) and "js_uri" in s.scan(payload)
    html_safe = s.sanitize(payload, mode="html")
    assert "<script>" not in html_safe and "&lt;script&gt;" in html_safe
    text_safe = s.sanitize(payload, mode="text")
    assert "<script>" not in text_safe and "javascript:" not in text_safe
    assert "onerror=" not in s.sanitize("<img src=x onerror=alert(1)>", mode="text")
    assert s.is_safe("a perfectly normal answer about refunds")


# ---- SSO OIDC (claims validation + production hardening + JWKS signature path) ----
def test_sso_oidc_dev_decode_and_role_mapping():
    from largestack._enterprise.sso import SSOProvider
    import base64, json
    # craft an unsigned JWT (dev mode allows this)
    payload = {"sub": "u1", "email": "u1@x.com", "roles": ["admin"], "tid": "tenant7", "name": "U One"}
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    tok = f"{b64({'alg':'none'})}.{b64(payload)}.sig"
    p = SSOProvider(provider="oidc", client_id="app", role_claim="roles", tenant_claim="tid")
    info = asyncio.run(p.authenticate(tok))
    assert info["user_id"] == "u1" and info["roles"] == ["admin"] and info["tenant_id"] == "tenant7"


def test_sso_production_refuses_unverified(monkeypatch):
    from largestack._enterprise.sso import SSOProvider, SSOError
    monkeypatch.setenv("LARGESTACK_ENV", "production")
    import base64, json
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    tok = f"{b64({'alg':'none'})}.{b64({'sub':'u1'})}.sig"
    p = SSOProvider(provider="oidc", client_id="app")  # no jwks_url
    with pytest.raises(SSOError):
        asyncio.run(p.authenticate(tok))


def test_sso_oidc_jwks_signature_verified(monkeypatch):
    """Full RS256 verification path (the real OIDC flow), offline via a fake JWKS client."""
    pytest.importorskip("jwt")
    pytest.importorskip("cryptography")
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    pub_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)
    token = pyjwt.encode({"sub": "u9", "email": "u9@x.com", "roles": ["operator"],
                          "aud": "app", "iss": "https://idp"}, priv_pem, algorithm="RS256")

    class _FakeKey:
        key = pub_pem

    class _FakeJWKClient:
        def __init__(self, url): pass
        def get_signing_key_from_jwt(self, tok): return _FakeKey()

    monkeypatch.setattr(pyjwt, "PyJWKClient", _FakeJWKClient)
    from largestack._enterprise.sso import SSOProvider
    p = SSOProvider(provider="oidc", client_id="app", issuer="https://idp",
                    jwks_url="https://idp/jwks", role_claim="roles")
    info = asyncio.run(p.authenticate(token))
    assert info["user_id"] == "u9" and info["roles"] == ["operator"]
