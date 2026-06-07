"""Databricks Foundation Model APIs provider."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "databricks-meta-llama-3-3-70b-instruct": {"context": 128000, "tool_use": True},
    "databricks-meta-llama-3-1-405b-instruct": {"context": 128000, "tool_use": True},
    "databricks-meta-llama-3-1-70b-instruct": {"context": 128000, "tool_use": True},
    "databricks-dbrx-instruct": {"context": 32768, "tool_use": True},
    "databricks-mixtral-8x7b-instruct": {"context": 32768},
}


class DatabricksProvider(OpenAIProvider):
    name = "databricks"
    default_model = "databricks-meta-llama-3-3-70b-instruct"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str, workspace_url: str = ""):
        url = (
            f"{workspace_url.rstrip('/')}/serving-endpoints"
            if workspace_url
            else "https://databricks.com/serving-endpoints"
        )
        super().__init__(api_key=api_key, base_url=url)

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 32768})
