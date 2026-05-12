from largestack import provider_support_matrix, get_provider_capabilities, tool_capable_providers


def test_provider_matrix_has_core_verified_providers():
    providers = {p["provider"]: p for p in provider_support_matrix()}
    assert providers["openai"]["chat"] is True
    assert providers["deepseek"]["tool_calling"] is True
    assert providers["anthropic"]["status"] == "verified"
    assert providers["ollama"]["local"] is True
    assert providers["local"]["status"] in {"partial", "experimental", "verified"}


def test_get_provider_capabilities_normalizes_names():
    assert get_provider_capabilities("ollama-openai")["provider"] == "ollama_openai"
    assert "deepseek" in tool_capable_providers()
