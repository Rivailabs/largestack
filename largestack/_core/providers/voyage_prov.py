"""Voyage AI provider — embeddings and reranking."""
from largestack._core.providers.openai_prov import OpenAIProvider

EMBEDDING_MODELS = {
    "voyage-3-large": {"dimensions": 1024, "context": 32000, "domain": "general"},
    "voyage-3": {"dimensions": 1024, "context": 32000, "domain": "general"},
    "voyage-3-lite": {"dimensions": 512, "context": 32000, "domain": "general"},
    "voyage-code-3": {"dimensions": 1024, "context": 32000, "domain": "code"},
    "voyage-finance-2": {"dimensions": 1024, "context": 32000, "domain": "finance"},
    "voyage-law-2": {"dimensions": 1024, "context": 16000, "domain": "law"},
    "voyage-multilingual-2": {"dimensions": 1024, "context": 32000, "domain": "multilingual"},
}

RERANKER_MODELS = {
    "rerank-2": {"context": 16000},
    "rerank-2-lite": {"context": 8000},
}

class VoyageProvider(OpenAIProvider):
    name = "voyage"
    default_model = "voyage-3-large"
    supported_models = list(EMBEDDING_MODELS.keys()) + list(RERANKER_MODELS.keys())
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.voyageai.com/v1")
    def get_capabilities(self, model: str) -> dict:
        m = model.split("/")[-1]
        return EMBEDDING_MODELS.get(m) or RERANKER_MODELS.get(m) or {"context": 16000}
    def is_embedding_model(self, model: str) -> bool:
        return model.split("/")[-1] in EMBEDDING_MODELS
