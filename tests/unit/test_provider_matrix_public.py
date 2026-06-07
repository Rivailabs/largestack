from largestack import provider_support_matrix, get_provider_capabilities, tool_capable_providers


def test_provider_matrix_has_core_verified_providers():
    providers = {p["provider"]: p for p in provider_support_matrix()}
    assert providers["openai"]["chat"] is True
    assert providers["deepseek"]["tool_calling"] is True
    # v1.1.1: anthropic is honestly "adapter_only" — structurally complete but not
    # live-verified (no key tested). Don't over-claim "verified".
    assert providers["anthropic"]["status"] == "adapter_only"
    assert providers["anthropic"]["tool_calling"] is True
    assert providers["ollama"]["local"] is True
    assert providers["local"]["status"] in {"partial", "experimental", "verified"}


def test_get_provider_capabilities_normalizes_names():
    assert get_provider_capabilities("ollama-openai")["provider"] == "ollama_openai"
    assert "deepseek" in tool_capable_providers()
