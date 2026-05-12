"""Tests verifying P0 fixes from v0.3.3 reviewer."""
from pathlib import Path
import sys, os, asyncio, json
sys.path.insert(0, ".")


# P0-1: engine forwards behavior kwargs to gateway
def test_engine_forwards_behavior_kwargs_to_gateway():
    """P0-1: AgentEngine.execute() must forward response_format/tool_choice/etc to gateway.chat()."""
    import largestack._core.engine as eng
    src = Path(eng.__file__).read_text()
    assert "behavior_kw" in src, "behavior_kw filter not present"
    assert '"response_format"' in src and '"tool_choice"' in src
    assert "**behavior_kw" in src, "kwargs not unpacked into gateway.chat()"


def test_engine_behavior_kw_filters_unsafe_keys():
    """P0-1: only known safe behavior kwargs forwarded — not arbitrary kw."""
    import largestack._core.engine as eng
    src = Path(eng.__file__).read_text()
    # Must filter to allowlist
    assert "_BEHAVIOR_KWS" in src
    # Must include key names
    for k in ["temperature", "max_tokens", "response_format", "tool_choice",
              "top_p", "top_k", "seed", "stop", "stop_sequences",
              "responseMimeType", "responseSchema"]:
        assert f'"{k}"' in src, f"behavior key {k} missing"


# P0-2: gateway passes cache_kw
def test_gateway_passes_cache_kw_to_get_exact():
    """P0-2: gateway must pass behavior kwargs to get_exact/put_exact."""
    import largestack._core.gateway as gw
    src = Path(gw.__file__).read_text()
    assert "cache_kw" in src
    assert "self._cache.get_exact(messages, model, **cache_kw)" in src
    assert "self._cache.put_exact(messages, model, resp, **cache_kw)" in src


def test_gateway_cache_kw_contains_response_format():
    """P0-2: cache_kw must include response_format and tool_choice."""
    import largestack._core.gateway as gw
    src = Path(gw.__file__).read_text()
    # Within the cache_kw dict
    assert '"response_format": kw.get("response_format")' in src
    assert '"tool_choice": kw.get("tool_choice")' in src


def test_cache_keys_differ_with_response_format():
    """P0-2 (behavioral): cache returns different responses for different response_format."""
    from largestack._core.semantic_cache import SemanticCache
    c = SemanticCache(ttl=3600)
    msgs = [{"role": "user", "content": "give me data"}]
    c.put_exact(msgs, "gpt-4", {"content": "plain"}, response_format=None)
    c.put_exact(msgs, "gpt-4", {"content": "json"}, response_format={"type": "json_object"})
    plain = c.get_exact(msgs, "gpt-4", response_format=None)
    js = c.get_exact(msgs, "gpt-4", response_format={"type": "json_object"})
    assert plain == {"content": "plain"}
    assert js == {"content": "json"}, "cache returned wrong entry — keys not differentiated"


# P0-3a: Ollama wraps errors
def test_ollama_wraps_timeout_into_provider_timeout():
    """P0-3a: Ollama must wrap httpx.TimeoutException into ProviderTimeoutError."""
    import largestack._core.providers.ollama_prov as op
    src = Path(op.__file__).read_text()
    assert "ProviderTimeoutError" in src
    assert "except httpx.TimeoutException" in src
    # No more raw raise_for_status
    assert "r.raise_for_status()" not in src, "Ollama still uses raw raise_for_status"


def test_ollama_wraps_request_error():
    """P0-3a: Ollama must wrap httpx.RequestError into ProviderError."""
    import largestack._core.providers.ollama_prov as op
    src = Path(op.__file__).read_text()
    assert "except httpx.RequestError" in src
    assert "ProviderError(f\"{self.name} request error" in src


def test_ollama_wraps_http_4xx_5xx():
    """P0-3a: Ollama must wrap HTTP ≥400 status into ProviderError."""
    import largestack._core.providers.ollama_prov as op
    src = Path(op.__file__).read_text()
    assert "if r.status_code >= 400:" in src
    assert "raise ProviderError" in src


# P0-3b: Bedrock wraps errors
def test_bedrock_wraps_missing_boto3_into_provider_error():
    """P0-3b: missing boto3 must raise ProviderError, not ImportError."""
    import largestack._core.providers.bedrock_prov as bp
    src = Path(bp.__file__).read_text()
    assert "_ensure_client" in src
    assert 'ProviderError(f"{self.name}: boto3 not installed' in src
    # Old raw ImportError raise must be gone
    assert 'raise ImportError("boto3 required' not in src


def test_bedrock_normalizes_aws_errors():
    """P0-3b: Bedrock has _normalize_aws_error mapping botocore exceptions."""
    import largestack._core.providers.bedrock_prov as bp
    src = Path(bp.__file__).read_text()
    assert "_normalize_aws_error" in src
    assert "ClientError" in src
    assert "ConnectTimeoutError" in src or "ReadTimeoutError" in src
    assert "ThrottlingException" in src
    assert "UnrecognizedClientException" in src or "InvalidSignatureException" in src


def test_bedrock_chat_uses_normalize_for_invoke_failures():
    """P0-3b: chat() must call _normalize_aws_error on invoke_model failure."""
    import largestack._core.providers.bedrock_prov as bp
    src = Path(bp.__file__).read_text()
    assert "raise self._normalize_aws_error(e) from e" in src


def test_bedrock_missing_boto3_returns_provider_error():
    """P0-3b (behavioral): instantiate Bedrock without boto3 still works; calling chat raises ProviderError."""
    from largestack._core.providers.bedrock_prov import BedrockProvider
    from largestack.errors import ProviderError
    p = BedrockProvider()
    # Force client to None to simulate missing boto3
    p._client = None
    
    async def main():
        try:
            await p.chat([{"role": "user", "content": "hi"}], "anthropic.claude-3-haiku")
        except ProviderError as e:
            assert "boto3" in str(e)
            return True
        except ImportError:
            assert False, "Bedrock raised ImportError (should be ProviderError)"
        return False
    
    assert asyncio.run(main()) is True


# P0-4: PEP 604 unions
def test_tool_schema_handles_pep604_optional():
    """P0-4: schema gen handles X | None (PEP 604 syntax)."""
    from largestack._core.tools import _type_to_schema
    s = _type_to_schema(int | None)
    assert s.get("type") == "integer", f"expected integer, got {s}"


def test_tool_schema_handles_pep604_union():
    """P0-4: schema gen handles X | Y (PEP 604 syntax)."""
    from largestack._core.tools import _type_to_schema
    s = _type_to_schema(int | float)
    assert "anyOf" in s, f"expected anyOf, got {s}"


def test_tool_schema_handles_pep604_list_optional():
    """P0-4: schema gen handles list[X] | None."""
    from largestack._core.tools import _type_to_schema
    s = _type_to_schema(list[str] | None)
    # Optional → unwraps to the array
    assert s.get("type") == "array"
    assert s.get("items") == {"type": "string"}


def test_decorators_python_to_json_handles_pep604():
    """P0-4: decorator schema mapping handles X | None."""
    from largestack.decorators import _python_to_json_type
    assert _python_to_json_type(str | None) == "string"
    assert _python_to_json_type(int | None) == "integer"
    assert _python_to_json_type(bool | None) == "boolean"


def test_decorators_module_imports_uniontype():
    """P0-4: decorators.py must import types.UnionType for PEP 604."""
    import largestack.decorators as dec
    src = Path(dec.__file__).read_text()
    assert "from types import UnionType" in src


def test_tools_module_imports_uniontype():
    """P0-4: tools.py must import types.UnionType."""
    import largestack._core.tools as tm
    src = Path(tm.__file__).read_text()
    assert "from types import UnionType" in src
    assert "origin is UnionType" in src or "origin is Union or origin is UnionType" in src


# P0-5: README honest claims
def test_readme_no_596_claim():
    """P0-5: README must not claim '596 unit tests passing' (test count drifts)."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "README.md")).read_text()
    assert "596 unit tests passing" not in src
    assert "596_passing" not in src


def test_readme_no_22_22_claim():
    """P0-5: README must not claim '22/22 verified end-to-end'."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "README.md")).read_text()
    assert "22/22 framework components verified" not in src


def test_readme_no_production_substrate_claim():
    """P0-5: README must not claim 'Production-ready substrate'."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "README.md")).read_text()
    assert "Production-ready substrate" not in src


def test_readme_has_known_limitations_pointer():
    """P0-5: README must point to known-limitations doc."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = Path(os.path.join(root, "README.md")).read_text()
    assert "known-limitations" in src.lower()


def test_known_limitations_doc_exists():
    """P0-5: docs/known-limitations.md must exist with substantive content."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(root, "docs/known-limitations.md")
    assert os.path.exists(path)
    src = Path(path).read_text().lower()
    # Must be honest, not marketing; release candidate/beta language is allowed,
    # stale alpha branding is not.
    assert "alpha-stage" not in src
    assert "not yet" in src or "limitation" in src or "release gate" in src
    assert len(src) > 1000, "known-limitations doc too short to be useful"


# Behavioral: end-to-end through engine forwards response_format
def test_e2e_response_format_reaches_provider_via_mock():
    """P0-1 (E2E): when user passes response_format=..., it reaches the provider HTTP body.
    
    Uses a fake provider that captures the kwargs it receives.
    """
    from largestack._core.providers.base import BaseProvider
    from largestack.types import LLMResponse
    
    captured_kw = {}
    
    class CapturingProvider(BaseProvider):
        name = "capture"
        async def chat(self, messages, model, tools=None, stream=False,
                       temperature=0.7, max_tokens=None, **kw):
            captured_kw.update(kw)
            captured_kw["_temperature"] = temperature
            captured_kw["_max_tokens"] = max_tokens
            captured_kw["_tools"] = tools
            return LLMResponse(content="ok", model=model, input_tokens=1, output_tokens=1, latency_ms=1)
        async def chat_stream(self, *a, **k):
            yield "ok"
        def count_tokens(self, t, m): return len(t) // 4
    
    from largestack import Agent
    from largestack._core.gateway import LLMGateway
    
    a = Agent(name="t", llm="capture/test-model", instructions="hi")
    # Inject capturing provider
    a._gw.providers["capture"] = CapturingProvider()
    a._engine.gateway = a._gw
    
    async def main():
        await a.run("hello", response_format={"type": "json_object"},
                    tool_choice="auto", seed=42, top_p=0.9)
    
    asyncio.run(main())
    
    # Verify behavior kwargs reached the provider
    assert captured_kw.get("response_format") == {"type": "json_object"}, \
        f"response_format not forwarded: {captured_kw}"
    assert captured_kw.get("tool_choice") == "auto", \
        f"tool_choice not forwarded: {captured_kw}"
    assert captured_kw.get("seed") == 42
    assert captured_kw.get("top_p") == 0.9


# Behavioral: cache differentiates by behavior params
def test_cache_differentiates_by_tool_choice():
    """P0-2 (behavioral): same prompt + different tool_choice = different cache entries."""
    from largestack._core.semantic_cache import SemanticCache
    c = SemanticCache()
    msgs = [{"role": "user", "content": "hello"}]
    c.put_exact(msgs, "gpt-4", {"content": "auto-tool"}, tool_choice="auto")
    c.put_exact(msgs, "gpt-4", {"content": "no-tool"}, tool_choice="none")
    auto = c.get_exact(msgs, "gpt-4", tool_choice="auto")
    none = c.get_exact(msgs, "gpt-4", tool_choice="none")
    assert auto["content"] == "auto-tool"
    assert none["content"] == "no-tool"


def test_cache_no_collision_for_temperature():
    """P0-2 (behavioral): same prompt + different temperature = different cache entries."""
    from largestack._core.semantic_cache import SemanticCache
    c = SemanticCache()
    msgs = [{"role": "user", "content": "hi"}]
    c.put_exact(msgs, "m", {"content": "cold"}, temperature=0.0)
    c.put_exact(msgs, "m", {"content": "hot"}, temperature=1.0)
    assert c.get_exact(msgs, "m", temperature=0.0)["content"] == "cold"
    assert c.get_exact(msgs, "m", temperature=1.0)["content"] == "hot"
