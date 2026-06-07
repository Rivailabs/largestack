"""Dashboard a11y + mobile-responsive regression tests (v0.4.0).

Validates that the server-rendered HTML follows accessibility basics:
- lang attribute on <html>
- skip-to-content link
- semantic landmark roles (nav, main)
- aria-current on active nav link
- viewport meta for mobile
- responsive CSS breakpoints
- prefers-reduced-motion support
- visible focus outlines
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test gets a fresh limiter — avoid cross-test pollution."""
    from largestack._dashboard.rate_limit import reset_for_tests

    reset_for_tests()
    yield
    reset_for_tests()


class TestDashboardA11y:
    def test_html_has_lang_attribute(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert '<html lang="en">' in r.text or "<html lang='en'>" in r.text

    def test_skip_to_content_link_present(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert 'class="skip-link"' in r.text
        assert "#main-content" in r.text

    def test_main_landmark_present(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert "<main" in r.text
        assert 'id="main-content"' in r.text
        assert 'role="main"' in r.text

    def test_nav_has_role_and_aria_label(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert "<nav" in r.text
        assert 'role="navigation"' in r.text
        assert "aria-label=" in r.text

    def test_active_nav_link_has_aria_current(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")  # overview is active
        # The active link should carry aria-current="page"
        assert 'aria-current="page"' in r.text

    def test_viewport_meta_present(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert '<meta name="viewport"' in r.text
        assert "width=device-width" in r.text

    def test_focus_outline_styles(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        # CSS should define a focus-visible outline
        assert ":focus-visible" in r.text

    def test_responsive_breakpoints_present(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        # Two breakpoints: tablet 640px, mobile 480px
        assert "max-width:640px" in r.text or "max-width: 640px" in r.text
        assert "max-width:480px" in r.text or "max-width: 480px" in r.text

    def test_reduced_motion_respected(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get("/")
        assert "prefers-reduced-motion" in r.text


class TestDashboardMobile:
    def test_mobile_chrome_user_agent_returns_html(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get(
            "/",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
                )
            },
        )
        # Same content for desktop and mobile — responsive CSS handles layout
        assert r.status_code == 200
        assert "<main" in r.text

    def test_iphone_user_agent_returns_html(self):
        from largestack._dashboard.app import create_app

        client = TestClient(create_app())
        r = client.get(
            "/",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                )
            },
        )
        assert r.status_code == 200
