"""v0.5.0: Native integration tests for Slack, Notion, GitHub.

Uses respx to mock httpx — no real API calls. These verify the
adapter behavior (auth, error paths, return-string format) without
needing real tokens.
"""

from __future__ import annotations

import pytest


# Skip whole module if respx isn't available — they're optional
respx = pytest.importorskip("respx")


# -------------------- Slack --------------------


@pytest.mark.asyncio
async def test_slack_send_no_token_returns_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_SLACK_TOKEN", raising=False)
    from largestack._integrations.slack import slack_send_message

    out = await slack_send_message("#general", "hello")
    assert "LARGESTACK_SLACK_TOKEN" in out


@pytest.mark.asyncio
async def test_slack_send_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_SLACK_TOKEN", "xoxb-fake-test-token")
    from largestack._integrations.slack import slack_send_message

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://slack.com/api/chat.postMessage").respond(
            200, json={"ok": True, "channel": "C123", "ts": "1234.5678"}
        )
        out = await slack_send_message("#general", "hello")
    assert "Posted to C123" in out
    assert "ts=1234.5678" in out


@pytest.mark.asyncio
async def test_slack_send_api_error(monkeypatch):
    monkeypatch.setenv("LARGESTACK_SLACK_TOKEN", "xoxb-fake")
    from largestack._integrations.slack import slack_send_message

    with respx.mock() as mock:
        mock.post("https://slack.com/api/chat.postMessage").respond(
            200, json={"ok": False, "error": "channel_not_found"}
        )
        out = await slack_send_message("#missing", "hi")
    assert "channel_not_found" in out


@pytest.mark.asyncio
async def test_slack_list_channels_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_SLACK_TOKEN", "xoxb-fake")
    from largestack._integrations.slack import slack_list_channels

    with respx.mock() as mock:
        mock.get("https://slack.com/api/conversations.list").respond(
            200,
            json={
                "ok": True,
                "channels": [
                    {"id": "C1", "name": "general"},
                    {"id": "C2", "name": "random"},
                ],
            },
        )
        out = await slack_list_channels()
    assert "C1  #general" in out
    assert "C2  #random" in out


# -------------------- Notion --------------------


@pytest.mark.asyncio
async def test_notion_no_token_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_NOTION_TOKEN", raising=False)
    from largestack._integrations.notion import notion_read_page

    out = await notion_read_page("abc")
    assert "LARGESTACK_NOTION_TOKEN" in out


@pytest.mark.asyncio
async def test_notion_read_page_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOTION_TOKEN", "secret_fake")
    from largestack._integrations.notion import notion_read_page

    with respx.mock() as mock:
        mock.get("https://api.notion.com/v1/blocks/abc123/children").respond(
            200,
            json={
                "results": [
                    {
                        "type": "heading_1",
                        "heading_1": {"rich_text": [{"plain_text": "Title"}]},
                    },
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Some text."}]},
                    },
                ]
            },
        )
        out = await notion_read_page("abc123")
    assert "# Title" in out
    assert "Some text." in out


@pytest.mark.asyncio
async def test_notion_read_page_404(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOTION_TOKEN", "secret_fake")
    from largestack._integrations.notion import notion_read_page

    with respx.mock() as mock:
        mock.get("https://api.notion.com/v1/blocks/xxx/children").respond(404)
        out = await notion_read_page("xxx")
    assert "not found" in out.lower()


@pytest.mark.asyncio
async def test_notion_search_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_NOTION_TOKEN", "secret_fake")
    from largestack._integrations.notion import notion_search

    with respx.mock() as mock:
        mock.post("https://api.notion.com/v1/search").respond(
            200,
            json={
                "results": [
                    {
                        "id": "page-1",
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "My Page"}],
                            }
                        },
                    }
                ]
            },
        )
        out = await notion_search("test")
    assert "page-1" in out
    assert "My Page" in out


# -------------------- GitHub --------------------


@pytest.mark.asyncio
async def test_github_no_token_error(monkeypatch):
    monkeypatch.delenv("LARGESTACK_GITHUB_TOKEN", raising=False)
    from largestack._integrations.github import github_list_issues

    out = await github_list_issues("a/b")
    assert "LARGESTACK_GITHUB_TOKEN" in out


@pytest.mark.asyncio
async def test_github_invalid_repo(monkeypatch):
    monkeypatch.setenv("LARGESTACK_GITHUB_TOKEN", "ghp_fake")
    from largestack._integrations.github import github_list_issues

    out = await github_list_issues("not-a-repo")
    assert "Invalid repo" in out


@pytest.mark.asyncio
async def test_github_list_issues_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_GITHUB_TOKEN", "ghp_fake")
    from largestack._integrations.github import github_list_issues

    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/foo/bar/issues").respond(
            200,
            json=[
                {"number": 42, "title": "Bug: thing broken"},
                {"number": 43, "title": "Feature: add stuff"},
            ],
        )
        out = await github_list_issues("foo/bar")
    assert "#42  Bug: thing broken" in out
    assert "#43  Feature: add stuff" in out


@pytest.mark.asyncio
async def test_github_list_issues_filters_out_prs(monkeypatch):
    """The GH issues endpoint returns PRs too — we must filter them out."""
    monkeypatch.setenv("LARGESTACK_GITHUB_TOKEN", "ghp_fake")
    from largestack._integrations.github import github_list_issues

    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/foo/bar/issues").respond(
            200,
            json=[
                {"number": 1, "title": "Real issue"},
                {"number": 2, "title": "PR title", "pull_request": {"url": "..."}},
            ],
        )
        out = await github_list_issues("foo/bar")
    assert "#1  Real issue" in out
    assert "PR title" not in out


@pytest.mark.asyncio
async def test_github_create_issue_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_GITHUB_TOKEN", "ghp_fake")
    from largestack._integrations.github import github_create_issue

    with respx.mock() as mock:
        mock.post("https://api.github.com/repos/foo/bar/issues").respond(
            201,
            json={
                "number": 99,
                "html_url": "https://github.com/foo/bar/issues/99",
            },
        )
        out = await github_create_issue("foo/bar", "New bug", body="details", labels="bug,p1")
    assert "#99" in out
    assert "github.com/foo/bar/issues/99" in out


@pytest.mark.asyncio
async def test_github_get_pr_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_GITHUB_TOKEN", "ghp_fake")
    from largestack._integrations.github import github_get_pr

    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/foo/bar/pulls/7").respond(
            200,
            json={
                "number": 7,
                "title": "Add feature",
                "state": "open",
                "merged": False,
                "draft": False,
                "user": {"login": "alice"},
                "head": {"ref": "feature"},
                "base": {"ref": "main"},
                "additions": 100,
                "deletions": 20,
                "changed_files": 5,
                "html_url": "https://github.com/foo/bar/pull/7",
            },
        )
        out = await github_get_pr("foo/bar", 7)
    assert "#7  Add feature" in out
    assert "state: open" in out
    assert "+100 -20" in out
    assert "5 file(s)" in out


# -------------------- Package import smoke --------------------


def test_integrations_package_exports_all_tools():
    """All 7 tools must be importable from largestack._integrations."""
    from largestack import _integrations

    expected = {
        "slack_send_message",
        "slack_list_channels",
        "notion_read_page",
        "notion_search",
        "github_list_issues",
        "github_create_issue",
        "github_get_pr",
    }
    assert expected.issubset(set(_integrations.__all__))
    for name in expected:
        assert hasattr(_integrations, name), f"missing {name}"
