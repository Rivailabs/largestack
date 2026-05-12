"""Browser automation tool — Playwright-based web interaction.

v0.3.12: Adds the same SSRF validator as http_tool / web_fetch. A headless
browser hitting `http://169.254.169.254/...` is just as dangerous as a
direct HTTP request — perhaps more so, because it can execute JS that
exfiltrates contents to a remote host.
"""
from largestack._core.tools import tool
from largestack._core.builtin_tools._url_validator import validate_url


@tool(timeout=60)
async def browser_navigate(url: str, action: str = "read") -> str:
    """Navigate to URL and extract content. Actions: read, screenshot, click.

    SSRF-protected (v0.3.12):
        - Scheme must be http/https
        - Host must NOT resolve to private/loopback/link-local/metadata IP
        - LARGESTACK_HTTP_ALLOWLIST controls strict pinning

    Requires playwright: pip install playwright && playwright install
    """
    err = validate_url(url)
    if err is not None:
        return f"Request blocked: {err}"

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Playwright not installed. Run: pip install playwright && playwright install"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=30000)

            if action == "read":
                content = await page.inner_text("body")
                return content[:5000]
            elif action == "screenshot":
                import tempfile

                with tempfile.NamedTemporaryFile(
                    prefix="largestack_screenshot_",
                    suffix=".png",
                    delete=False,
                ) as tmp:
                    screenshot_path = tmp.name

                await page.screenshot(path=screenshot_path)
                return f"Screenshot saved to {screenshot_path}"
            else:
                return f"Page loaded: {await page.title()}"
        finally:
            await browser.close()
