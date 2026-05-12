"""Tests for enhanced provider catalogs and capabilities."""
import sys; sys.path.insert(0, ".")

def test_groq_has_catalog():
    from largestack._core.providers.groq_prov import GroqProvider, MODELS
    assert len(MODELS) >= 5
    assert "llama-3.3-70b-versatile" in MODELS
    p = GroqProvider(api_key="test")
    assert p.default_model == "llama-3.3-70b-versatile"
    assert "llama-3.3-70b-versatile" in p.supported_models

def test_groq_capabilities():
    from largestack._core.providers.groq_prov import GroqProvider
    p = GroqProvider(api_key="test")
    caps = p.get_capabilities("groq/llama-3.3-70b-versatile")
    assert caps["context"] == 128000
    assert caps["tool_use"] is True

def test_groq_validate_model():
    from largestack._core.providers.groq_prov import GroqProvider
    p = GroqProvider(api_key="test")
    assert p.validate_model("groq/llama-3.3-70b-versatile")
    assert p.validate_model("llama-some-variant")
    assert not p.validate_model("gpt-4o")

def test_perplexity_models():
    from largestack._core.providers.perplexity_prov import PerplexityProvider, MODELS
    assert "sonar" in MODELS
    assert MODELS["sonar"]["online"] is True
    p = PerplexityProvider(api_key="test")
    assert p.default_model == "sonar"

def test_xai_models():
    from largestack._core.providers.xai_prov import XAIProvider, MODELS
    assert "grok-2-1212" in MODELS
    p = XAIProvider(api_key="test")
    caps = p.get_capabilities("xai/grok-2-vision-1212")
    assert caps["vision"] is True

def test_cerebras_speed_info():
    from largestack._core.providers.cerebras_prov import CerebrasProvider, MODELS
    assert "speed" in MODELS["llama3.1-8b"]
    assert "2100" in MODELS["llama3.1-8b"]["speed"]

def test_together_diverse_models():
    from largestack._core.providers.together_prov import TogetherProvider, MODELS
    # Should have Meta + Mistral + Qwen + DeepSeek
    names = " ".join(MODELS.keys()).lower()
    assert "llama" in names
    assert "mistral" in names or "mixtral" in names
    assert "qwen" in names
    assert "deepseek" in names

def test_openrouter_unified_gateway():
    from largestack._core.providers.openrouter_prov import OpenRouterProvider, POPULAR_MODELS
    # Should include models from multiple providers
    providers_seen = set()
    for m in POPULAR_MODELS:
        providers_seen.add(m.split("/")[0])
    assert len(providers_seen) >= 4  # anthropic, openai, google, meta-llama, etc.

def test_openrouter_headers():
    from largestack._core.providers.openrouter_prov import OpenRouterProvider
    p = OpenRouterProvider(api_key="test", site_url="https://example.com", app_name="MyApp")
    assert p.extra_headers.get("HTTP-Referer") == "https://example.com"
    assert p.extra_headers.get("X-Title") == "MyApp"

def test_ai21_jamba_context():
    from largestack._core.providers.ai21_prov import AI21Provider, MODELS
    assert MODELS["jamba-1.5-large"]["context"] == 256000

def test_voyage_embedding_domains():
    from largestack._core.providers.voyage_prov import VoyageProvider, EMBEDDING_MODELS, RERANKER_MODELS
    # Should have specialized domain embeddings
    domains = set(m.get("domain") for m in EMBEDDING_MODELS.values() if "domain" in m)
    assert "code" in domains
    assert "finance" in domains
    # And rerankers
    assert len(RERANKER_MODELS) >= 2
    p = VoyageProvider(api_key="test")
    assert p.is_embedding_model("voyage/voyage-3-large")
    assert not p.is_embedding_model("voyage/rerank-2")

def test_all_providers_have_catalog():
    """Every enhanced provider has either MODELS or POPULAR_MODELS."""
    providers = ["groq", "perplexity", "xai", "cerebras", "together", "fireworks",
                  "sambanova", "ai21", "lepton", "nvidia", "anyscale", "cloudflare",
                  "voyage", "replicate", "databricks"]
    for name in providers:
        mod = __import__(f"largestack._core.providers.{name}_prov", fromlist=["MODELS"])
        assert hasattr(mod, "MODELS") or hasattr(mod, "POPULAR_MODELS") or hasattr(mod, "EMBEDDING_MODELS"), f"{name} missing catalog"
