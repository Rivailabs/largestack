"""Beginner-facing integration registry for Largestack AI projects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationSpec:
    name: str
    description: str
    env_vars: tuple[str, ...]
    risk_type: str
    approval: str
    approval_actions: tuple[str, ...]
    install_hint: str
    test_command: str
    example_usage: str

    def as_project_entry(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "env_vars": list(self.env_vars),
            "risk_type": self.risk_type,
            "approval": self.approval,
            "install_hint": self.install_hint,
            "test_command": self.test_command,
            "example_usage": self.example_usage,
        }


INTEGRATIONS: dict[str, IntegrationSpec] = {
    "jira": IntegrationSpec(
        name="jira",
        description="Create and read Jira issues.",
        env_vars=("LARGESTACK_JIRA_URL", "LARGESTACK_JIRA_EMAIL", "LARGESTACK_JIRA_API_TOKEN"),
        risk_type="unsafe_tool",
        approval="require_approval",
        approval_actions=("issue_create", "issue_update"),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use for support escalation or engineering ticket creation.",
    ),
    "slack": IntegrationSpec(
        name="slack",
        description="Read channels and send Slack messages.",
        env_vars=("LARGESTACK_SLACK_TOKEN",),
        risk_type="unsafe_tool",
        approval="require_approval",
        approval_actions=("send_message",),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use for human approval notifications and incident channels.",
    ),
    "postgres": IntegrationSpec(
        name="postgres",
        description="Query and update Postgres databases.",
        env_vars=("LARGESTACK_POSTGRES_URL",),
        risk_type="financial_data",
        approval="require_approval",
        approval_actions=("db_write", "db_update", "db_delete"),
        install_hint="pip install largestack[postgres]",
        test_command="largestack doctor",
        example_usage="Use read queries by default; require approval for writes.",
    ),
    "qdrant": IntegrationSpec(
        name="qdrant",
        description="Use Qdrant as a vector database for RAG.",
        env_vars=("LARGESTACK_QDRANT_URL", "LARGESTACK_QDRANT_API_KEY"),
        risk_type="external_exfiltration",
        approval="require_approval",
        approval_actions=("external_upload",),
        install_hint="pip install largestack[rag]",
        test_command="largestack rag test",
        example_usage="Use for vector RAG when documents can leave the local process.",
    ),
    "chroma": IntegrationSpec(
        name="chroma",
        description="Use Chroma as a local or persistent vector store for RAG.",
        env_vars=("LARGESTACK_CHROMA_PATH",),
        risk_type="unknown",
        approval="warn",
        approval_actions=("vector_index_write",),
        install_hint="pip install chromadb",
        test_command="largestack rag test",
        example_usage="Use for local vector RAG when documents should stay on the developer machine.",
    ),
    "pgvector": IntegrationSpec(
        name="pgvector",
        description="Use Postgres pgvector for SQL + vector RAG.",
        env_vars=("LARGESTACK_POSTGRES_URL",),
        risk_type="financial_data",
        approval="require_approval",
        approval_actions=("db_write", "vector_index_write"),
        install_hint="pip install largestack[postgres]",
        test_command="largestack rag test",
        example_usage="Use for production SQL + vector retrieval with database approval controls.",
    ),
    "opensearch": IntegrationSpec(
        name="opensearch",
        description="Use OpenSearch for keyword, hybrid, or vector retrieval.",
        env_vars=("LARGESTACK_OPENSEARCH_URL", "LARGESTACK_OPENSEARCH_USER", "LARGESTACK_OPENSEARCH_PASSWORD"),
        risk_type="external_exfiltration",
        approval="require_approval",
        approval_actions=("external_upload", "vector_index_write"),
        install_hint="pip install opensearch-py",
        test_command="largestack rag test",
        example_usage="Use for enterprise search when index writes and external uploads are approved.",
    ),
    "github": IntegrationSpec(
        name="github",
        description="Read repositories and create issues or pull request comments.",
        env_vars=("LARGESTACK_GITHUB_TOKEN",),
        risk_type="unsafe_tool",
        approval="require_approval",
        approval_actions=("issue_create", "comment_write", "repo_write"),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use read-only repo analysis by default; require approval for comments, issues, and writes.",
    ),
    "youtube": IntegrationSpec(
        name="youtube",
        description="Load public YouTube transcript or metadata sources.",
        env_vars=("LARGESTACK_YOUTUBE_API_KEY",),
        risk_type="unknown",
        approval="warn",
        approval_actions=("external_read",),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use as a read-only knowledge source.",
    ),
    "stripe": IntegrationSpec(
        name="stripe",
        description="Read Stripe billing data and initiate payment/refund actions.",
        env_vars=("LARGESTACK_STRIPE_API_KEY",),
        risk_type="financial_data",
        approval="require_approval",
        approval_actions=("payment", "refund_payment", "external_upload"),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use read-only billing lookup by default; require approval for payments/refunds.",
    ),
    "razorpay": IntegrationSpec(
        name="razorpay",
        description="Razorpay billing/payment connector. Makes REAL calls to api.razorpay.com (orders, refunds, payment links) — gate behind approval.",
        env_vars=("LARGESTACK_RAZORPAY_KEY_ID", "LARGESTACK_RAZORPAY_KEY_SECRET"),
        risk_type="financial_data",
        approval="require_approval",
        approval_actions=("payment", "refund_payment", "external_upload"),
        install_hint="pip install largestack",
        test_command="largestack doctor",
        example_usage="Use mocked payment planning by default; require maker-checker before real payment/refund actions.",
    ),
    "mcp": IntegrationSpec(
        name="mcp",
        description="Connect tools from an MCP server over HTTP or stdio.",
        env_vars=("LARGESTACK_MCP_URL", "LARGESTACK_MCP_COMMAND"),
        risk_type="unsafe_tool",
        approval="require_approval",
        approval_actions=("mcp_tool_call", "external_read", "external_upload"),
        install_hint="pip install largestack[mcp]",
        test_command="largestack mcp test",
        example_usage="Use MCP to expose third-party tools; review tool descriptions for prompt injection before enabling writes.",
    ),
}


def available_integrations() -> list[str]:
    return sorted(INTEGRATIONS)


def get_integration(name: str) -> IntegrationSpec:
    key = name.replace("_", "-").lower()
    if key not in INTEGRATIONS:
        raise ValueError(f"Unknown integration: {name}. Choose from: {available_integrations()}")
    return INTEGRATIONS[key]
