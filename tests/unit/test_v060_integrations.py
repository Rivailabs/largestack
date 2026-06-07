"""v0.6.0: Tests for new native integrations (Postgres, Sheets, Linear, Jira).

Uses respx to mock HTTP — no real API calls.
"""

from __future__ import annotations

import json
import pytest

respx = pytest.importorskip("respx")


# -------------------- Postgres --------------------


@pytest.mark.asyncio
async def test_postgres_no_url_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_POSTGRES_URL", raising=False)
    from largestack._integrations.postgres import postgres_query

    out = await postgres_query("SELECT 1")
    assert "LARGESTACK_POSTGRES_URL" in out


@pytest.mark.asyncio
async def test_postgres_blocks_non_select(monkeypatch):
    monkeypatch.setenv("LARGESTACK_POSTGRES_URL", "postgresql://test")
    from largestack._integrations.postgres import postgres_query

    out = await postgres_query("DROP TABLE users")
    assert "blocked" in out.lower() or "select" in out.lower()


@pytest.mark.asyncio
async def test_postgres_blocks_insert(monkeypatch):
    monkeypatch.setenv("LARGESTACK_POSTGRES_URL", "postgresql://test")
    from largestack._integrations.postgres import postgres_query

    out = await postgres_query("INSERT INTO t VALUES (1)")
    assert "blocked" in out.lower() or "select" in out.lower()


@pytest.mark.asyncio
async def test_postgres_allows_with_cte(monkeypatch):
    """WITH (CTE) is also allowed — common pattern in real queries."""
    # v1.1.1: localhost:1 → instant connection-refused, NO external DNS lookup (the
    # previous 'invalid' host could trigger a real getaddrinfo on hosts with a
    # wildcard/search-domain resolver). Keeps this gate test hermetic.
    monkeypatch.setenv("LARGESTACK_POSTGRES_URL", "postgresql://localhost:1/db")
    from largestack._integrations.postgres import postgres_query

    out = await postgres_query("WITH x AS (SELECT 1) SELECT * FROM x")
    # Fails at connection (refused) but NOT at validation — CTE must pass the SQL guard.
    assert "blocked" not in out.lower() or "connection" in out.lower()


# -------------------- Google Sheets --------------------


@pytest.mark.asyncio
async def test_sheets_no_creds_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_GOOGLE_SERVICE_ACCOUNT", raising=False)
    from largestack._integrations.sheets import sheets_read_range

    out = await sheets_read_range("abc")
    assert "LARGESTACK_GOOGLE_SERVICE_ACCOUNT" in out


@pytest.mark.asyncio
async def test_sheets_missing_file_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("LARGESTACK_GOOGLE_SERVICE_ACCOUNT", str(tmp_path / "missing.json"))
    from largestack._integrations.sheets import sheets_read_range

    out = await sheets_read_range("abc")
    assert "Error" in out


@pytest.mark.asyncio
async def test_sheets_append_invalid_values_json(monkeypatch, tmp_path):
    """If values isn't valid JSON, error early before hitting Google."""
    fake_sa = tmp_path / "sa.json"
    # Make a syntactically valid SA file (won't be used for real auth)
    fake_sa.write_text(
        json.dumps(
            {
                "client_email": "test@example.iam.gserviceaccount.com",
                "private_key": "INVALID_KEY",
            }
        )
    )
    monkeypatch.setenv("LARGESTACK_GOOGLE_SERVICE_ACCOUNT", str(fake_sa))
    from largestack._integrations.sheets import sheets_append_row

    out = await sheets_append_row("abc", "Sheet1!A:Z", "{not json")
    assert "invalid values JSON" in out


# -------------------- Linear --------------------


@pytest.mark.asyncio
async def test_linear_no_token(monkeypatch):
    monkeypatch.delenv("LARGESTACK_LINEAR_API_KEY", raising=False)
    from largestack._integrations.linear import linear_list_issues

    out = await linear_list_issues()
    assert "LARGESTACK_LINEAR_API_KEY" in out


@pytest.mark.asyncio
async def test_linear_list_issues_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_LINEAR_API_KEY", "lin_api_test")
    from largestack._integrations.linear import linear_list_issues

    with respx.mock() as mock:
        mock.post("https://api.linear.app/graphql").respond(
            200,
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "identifier": "ENG-1",
                                "title": "Fix bug",
                                "state": {"name": "In Progress"},
                            },
                            {
                                "identifier": "ENG-2",
                                "title": "Add feature",
                                "state": {"name": "Todo"},
                            },
                        ]
                    }
                }
            },
        )
        out = await linear_list_issues()
    assert "ENG-1" in out and "Fix bug" in out
    assert "[In Progress]" in out


@pytest.mark.asyncio
async def test_linear_create_issue_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_LINEAR_API_KEY", "lin_api_test")
    from largestack._integrations.linear import linear_create_issue

    with respx.mock() as mock:
        mock.post("https://api.linear.app/graphql").respond(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "identifier": "ENG-99",
                            "url": "https://linear.app/x/issue/ENG-99",
                        },
                    }
                }
            },
        )
        out = await linear_create_issue("team-uuid", "New issue", "details")
    assert "ENG-99" in out
    assert "linear.app" in out


@pytest.mark.asyncio
async def test_linear_create_issue_requires_args(monkeypatch):
    monkeypatch.setenv("LARGESTACK_LINEAR_API_KEY", "lin_api_test")
    from largestack._integrations.linear import linear_create_issue

    out = await linear_create_issue("", "")
    assert "required" in out


@pytest.mark.asyncio
async def test_linear_handles_graphql_error(monkeypatch):
    monkeypatch.setenv("LARGESTACK_LINEAR_API_KEY", "lin_api_test")
    from largestack._integrations.linear import linear_list_issues

    with respx.mock() as mock:
        mock.post("https://api.linear.app/graphql").respond(
            200,
            json={"errors": [{"message": "Unauthorized"}]},
        )
        out = await linear_list_issues()
    assert "Unauthorized" in out


# -------------------- Jira --------------------


@pytest.mark.asyncio
async def test_jira_missing_env_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_JIRA_URL", raising=False)
    monkeypatch.delenv("LARGESTACK_JIRA_EMAIL", raising=False)
    monkeypatch.delenv("LARGESTACK_JIRA_API_TOKEN", raising=False)
    from largestack._integrations.jira import jira_search_issues

    out = await jira_search_issues("project = X")
    assert "LARGESTACK_JIRA_" in out


@pytest.mark.asyncio
async def test_jira_search_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("LARGESTACK_JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("LARGESTACK_JIRA_API_TOKEN", "token123")
    from largestack._integrations.jira import jira_search_issues

    with respx.mock() as mock:
        mock.post("https://example.atlassian.net/rest/api/3/search/jql").respond(
            200,
            json={
                "issues": [
                    {
                        "key": "ENG-1",
                        "fields": {
                            "summary": "Fix login",
                            "status": {"name": "To Do"},
                        },
                    },
                ]
            },
        )
        out = await jira_search_issues("project = ENG")
    assert "ENG-1" in out
    assert "Fix login" in out
    assert "[To Do]" in out


@pytest.mark.asyncio
async def test_jira_add_comment_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("LARGESTACK_JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("LARGESTACK_JIRA_API_TOKEN", "token123")
    from largestack._integrations.jira import jira_add_comment

    with respx.mock() as mock:
        mock.post("https://example.atlassian.net/rest/api/3/issue/ENG-1/comment").respond(
            201,
            json={"id": "10001"},
        )
        out = await jira_add_comment("ENG-1", "Looks good!")
    assert "ENG-1" in out
    assert "id=10001" in out


@pytest.mark.asyncio
async def test_jira_unauthorized(monkeypatch):
    monkeypatch.setenv("LARGESTACK_JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("LARGESTACK_JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("LARGESTACK_JIRA_API_TOKEN", "wrong")
    from largestack._integrations.jira import jira_search_issues

    with respx.mock() as mock:
        mock.post("https://example.atlassian.net/rest/api/3/search/jql").respond(401)
        out = await jira_search_issues("project = X")
    assert "authentication failed" in out.lower()


# -------------------- Package init --------------------


def test_v060_package_exports_all_new_tools():
    """All 14 tools must be importable from largestack._integrations."""
    from largestack import _integrations

    expected_v06 = {
        "postgres_query",
        "sheets_read_range",
        "sheets_append_row",
        "linear_list_issues",
        "linear_create_issue",
        "jira_search_issues",
        "jira_add_comment",
    }
    assert expected_v06.issubset(set(_integrations.__all__))
    for name in expected_v06:
        assert hasattr(_integrations, name), f"missing {name}"
    # v0.5 still exported
    assert "slack_send_message" in _integrations.__all__
