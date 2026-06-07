"""Browser automation — Playwright with persistent browser lifecycle."""

from __future__ import annotations
import asyncio
import logging

log = logging.getLogger("largestack.browser")


class BrowserTool:
    """Browser automation with persistent browser instance.

    Use as async context manager or call start()/close() explicitly:

        async with BrowserTool() as bt:
            text = await bt.navigate_and_extract("https://example.com")
            text2 = await bt.navigate_and_extract("https://other.com")
        # Browser closes automatically
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._available = False
        self._playwright_ctx = None
        self._browser = None
        self._lock = asyncio.Lock()
        try:
            from playwright.async_api import async_playwright

            self._async_playwright = async_playwright
            self._available = True
        except ImportError:
            pass  # don't log on import - too noisy

    @property
    def available(self) -> bool:
        return self._available

    async def start(self):
        """Start browser. Idempotent."""
        if not self._available:
            raise RuntimeError(
                "playwright not installed. pip install playwright && playwright install chromium"
            )
        async with self._lock:
            if self._browser is None:
                self._playwright_ctx = await self._async_playwright().start()
                self._browser = await self._playwright_ctx.chromium.launch(headless=self.headless)

    async def close(self):
        """Close browser. Idempotent."""
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright_ctx:
                await self._playwright_ctx.stop()
                self._playwright_ctx = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def navigate_and_extract(self, url: str, selector: str = "body") -> str:
        """Navigate and extract text. Reuses browser instance."""
        if not self._available:
            return "Browser unavailable. Install: pip install playwright"
        if self._browser is None:
            await self.start()
        try:
            page = await self._browser.new_page()
            try:
                await page.goto(url, timeout=30000)
                content = await page.locator(selector).inner_text()
                return content[:5000]
            finally:
                await page.close()
        except Exception as e:
            return f"Browser error: {e}"

    async def screenshot(self, url: str, path: str = "screenshot.png") -> str:
        if not self._available:
            return "Browser unavailable"
        if self._browser is None:
            await self.start()
        try:
            page = await self._browser.new_page()
            try:
                await page.goto(url, timeout=30000)
                await page.screenshot(path=path)
                return path
            finally:
                await page.close()
        except Exception as e:
            return f"Error: {e}"
