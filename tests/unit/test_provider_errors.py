"""Tests for provider structure."""
import sys; sys.path.insert(0, ".")

def test_25_providers_mapped():
    from largestack._core.gateway import PROVIDER_MAP
    # v0.7.0 added LiteLLM as the 26th provider. Later releases may add
    # providers; the release invariant is that LiteLLM remains present and
    # the provider map does not regress below the documented floor.
    assert len(PROVIDER_MAP) >= 26
    assert "litellm" in PROVIDER_MAP

def test_providers_importable():
    from largestack._core.gateway import PROVIDER_MAP
    for name, cls in PROVIDER_MAP.items():
        assert cls is not None, f"{name} is None"

def test_groq_models():
    from largestack._core.providers.groq_prov import MODELS
    assert len(MODELS) >= 3
    for model, info in MODELS.items():
        assert "context" in info

def test_provider_names_lowercase():
    from largestack._core.gateway import PROVIDER_MAP
    for name in PROVIDER_MAP:
        assert name == name.lower()

def test_gateway_creates():
    from largestack._core.gateway import LLMGateway
    gw = LLMGateway()
    assert gw is not None

def test_gateway_cost_tracker():
    from largestack._core.gateway import LLMGateway
    gw = LLMGateway()
    assert hasattr(gw, 'cost_tracker')
