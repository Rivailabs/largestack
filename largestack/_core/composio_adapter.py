"""Composio adapter — 900+ tool integrations via single SDK.

Slack, Notion, GitHub, Linear, Jira, Salesforce, HubSpot, Gmail, Google Drive, etc.

Usage:
    from largestack._core.composio_adapter import ComposioToolset
    
    toolset = ComposioToolset(api_key="...")
    tools = toolset.get_tools(apps=["github", "slack"])
    agent = Agent(tools=tools)
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("largestack.composio")


class ComposioToolset:
    """Wrapper for Composio toolkit. 900+ integrations in one dependency."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("COMPOSIO_API_KEY") or os.environ.get("LARGESTACK_COMPOSIO_API_KEY")
        self._available = False
        try:
            from composio import ComposioToolSet
            self._toolset = ComposioToolSet(api_key=self.api_key)
            self._available = True
        except ImportError:
            log.warning("composio not installed. pip install composio-core")
    
    @property
    def available(self) -> bool:
        return self._available and bool(self.api_key)
    
    def get_tools(self, apps: list[str] | None = None, actions: list[str] | None = None) -> list:
        """Get tools for specified apps or actions."""
        if not self._available:
            log.error("Composio not available")
            return []
        try:
            if apps:
                return self._toolset.get_tools(apps=apps)
            if actions:
                return self._toolset.get_tools(actions=actions)
            return []
        except Exception as e:
            log.error(f"Composio get_tools failed: {e}")
            return []
    
    def list_apps(self) -> list[str]:
        """Common Composio apps (subset of 900+)."""
        return [
            "github", "slack", "notion", "linear", "jira", "asana", "trello",
            "gmail", "google-drive", "google-calendar", "google-sheets", "google-docs",
            "salesforce", "hubspot", "pipedrive", "intercom", "zendesk",
            "shopify", "stripe", "razorpay", "discord", "telegram", "whatsapp",
            "airtable", "monday", "clickup", "twitter-x", "linkedin", "reddit",
            "youtube", "spotify", "dropbox", "onedrive", "outlook", "calendly",
        ]
