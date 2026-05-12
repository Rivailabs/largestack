"""Azure OpenAI provider.

v0.5.0: keeps the lazy-HTTP-client init from the parent class. Azure's
header swap (api-key instead of Authorization) is now done in a property
override rather than at construction time.
"""
from __future__ import annotations
import httpx
from largestack._core.providers.openai_prov import OpenAIProvider


class AzureOpenAIProvider(OpenAIProvider):
    name = "azure"

    def __init__(self, api_key: str, endpoint: str, api_version: str = "2024-10-21"):
        base_url = f"{endpoint.rstrip('/')}/openai/deployments"
        super().__init__(api_key=api_key, base_url=base_url)
        self._api_version = api_version

    @property
    def _c(self) -> httpx.AsyncClient:
        """Lazy-initialize HTTP client with Azure-specific auth header."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"api-key": self._api_key, "Content-Type": "application/json"},
                timeout=httpx.Timeout(connect=10, read=120, write=30, pool=5),
                http2=True,
            )
        return self._client
