"""Native integrations for popular SaaS tools.

v0.5.0 shipped: Slack, Notion, GitHub.
v0.6.0 adds: Postgres, Google Sheets, Linear, Jira.

Pattern (unchanged from v0.5):
    from largestack._integrations.slack import slack_send_message
    from largestack._integrations.linear import linear_list_issues
    from largestack import Agent

    agent = Agent(
        name="ops",
        llm="...",
        tools=[slack_send_message, linear_list_issues],
    )

Each integration is **opt-in via env var** — none require external SDK
installation by default. Where the official SDK exists, it's used;
otherwise we hit the REST/GraphQL API directly via httpx.
"""

from largestack._integrations.slack import slack_send_message, slack_list_channels
from largestack._integrations.notion import notion_read_page, notion_search
from largestack._integrations.github import github_list_issues, github_create_issue, github_get_pr

# v0.6.0
from largestack._integrations.postgres import postgres_query
from largestack._integrations.sheets import sheets_read_range, sheets_append_row
from largestack._integrations.linear import linear_list_issues, linear_create_issue
from largestack._integrations.jira import jira_search_issues, jira_add_comment
from largestack._integrations.openai_embeddings import openai_embed

# v0.7.0: Cohere + Voyage embeddings
from largestack._integrations.cohere_embed import cohere_embed
from largestack._integrations.voyage_embed import voyage_embed

# v0.8.0: HuggingFace + Jina embeddings
from largestack._integrations.hf_embed import hf_embed
from largestack._integrations.jina_embed import jina_embed

# v0.8.0 toolkits
from largestack._integrations.openapi_toolkit import OpenAPIToolkit
from largestack._integrations.razorpay_toolkit import RazorpayToolkit

# v0.9.0: 6 more embedding providers
from largestack._integrations.embeddings_v09 import (
    sentence_transformers_embed,
    ollama_embed,
    nomic_embed,
    bedrock_embed,
    vertex_embed,
    azure_openai_embed,
)

# v0.9.0: 6 more toolkits
from largestack._integrations.sql_toolkit import SQLToolkit
from largestack._integrations.pandas_toolkit import PandasToolkit
from largestack._integrations.stripe_toolkit import StripeToolkit
from largestack._integrations.toolkits_v09 import (
    TwilioToolkit,
    GitHubFullToolkit,
    ConfluenceToolkit,
)

# v0.9.0: 6 Indian wedge toolkits (LARGESTACK-unique)
from largestack._integrations.indian_toolkits import (
    UPIToolkit,
    GSTToolkit,
    MCAToolkit,
    DigiLockerToolkit,
    eSignToolkit,
    KYCToolkit,
)

__all__ = [
    # Slack (v0.5)
    "slack_send_message",
    "slack_list_channels",
    # Notion (v0.5)
    "notion_read_page",
    "notion_search",
    # GitHub (v0.5)
    "github_list_issues",
    "github_create_issue",
    "github_get_pr",
    # Postgres (v0.6)
    "postgres_query",
    # Google Sheets (v0.6)
    "sheets_read_range",
    "sheets_append_row",
    # Linear (v0.6)
    "linear_list_issues",
    "linear_create_issue",
    # Jira (v0.6)
    "jira_search_issues",
    "jira_add_comment",
    # OpenAI Embeddings (v0.6)
    "openai_embed",
    # Cohere + Voyage Embeddings (v0.7)
    "cohere_embed",
    "voyage_embed",
    # HuggingFace + Jina Embeddings (v0.8)
    "hf_embed",
    "jina_embed",
    # v0.8.0 toolkits (auto-generate tools)
    "OpenAPIToolkit",
    "RazorpayToolkit",
    # v0.9.0: 6 more embedding providers
    "sentence_transformers_embed",
    "ollama_embed",
    "nomic_embed",
    "bedrock_embed",
    "vertex_embed",
    "azure_openai_embed",
    # v0.9.0: 6 more toolkits
    "SQLToolkit",
    "PandasToolkit",
    "StripeToolkit",
    "TwilioToolkit",
    "GitHubFullToolkit",
    "ConfluenceToolkit",
    # v0.9.0: 6 Indian wedge toolkits (LARGESTACK-unique)
    "UPIToolkit",
    "GSTToolkit",
    "MCAToolkit",
    "DigiLockerToolkit",
    "eSignToolkit",
    "KYCToolkit",
]
