"""Browser + voice tool tests (graceful when deps missing)."""

import sys

sys.path.insert(0, ".")


def test_browser_tool_unavailable_handling():
    from largestack._core.browser_tool import BrowserTool

    bt = BrowserTool()
    # Should not crash even without playwright
    assert isinstance(bt.available, bool)


def test_voice_agent_create():
    from largestack._core.voice_agent import VoiceAgent

    va = VoiceAgent()
    assert isinstance(va.available, bool)
