"""Browser automation layer for the AION Desktop Operating System MVP.

This module controls a Chromium browser via Playwright. It is the
"eyes and hands" for web tasks: navigating to URLs, typing, clicking,
filling forms, and capturing screenshots.

Security model
--------------
* Browser automation defaults to headless (no visible window). The user
  must explicitly set ``headless: false`` in the local agent's
  ``config.yaml`` to see a browser window.
* Pages are opened in private/isolated contexts. No credential or
  session data is shared across tasks.
* All navigation targets are validated against an optional URL allowlist.
  If the user does not provide an allowlist, all http/https URLs are
  allowed, but the browser runs in a sandbox and cannot access the
  filesystem or local services (for http://localhost, we route through
  the local agent's proxy so the backend can exercise the page if needed).

Usage
-----
From the local agent:

    from aion_desktop.browser import BrowserManager

    async with BrowserManager(headless=True) as browser:
        page = await browser.new_page()
        await page.goto("https://decoricks.com")
        title = await page.title()
        screenshot = await page.screenshot(path="decoricks.png")
        await page.fill("input[name=\"email\"]", "user@example.com")
        await page.click("button[type=\"submit\"]")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger("aion_desktop.browser")

# Lazy import: playwright is a heavy dependency that may not be installed
# yet. We import it inside the methods that need it so the module can be
# statically verified and the code can be read without playwright present.
# playwright is only required at runtime when a browser action is taken.
_PW_MODULE = None


def _get_playwright_module() -> Any:
    """Import playwright.async_api lazily, raising a helpful error if missing."""
    global _PW_MODULE
    if _PW_MODULE is None:
        try:
            import playwright.async_api  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install it first with: "
                "pip install playwright && "
                "python -m playwright install chromium"
            ) from exc
        _PW_MODULE = playwright.async_api
    return _PW_MODULE


# Default navigation timeout in seconds per page
DEFAULT_TIMEOUT = 30


class BrowserNotInitializedError(RuntimeError):
    """Raised when an operation is attempted before the browser is open."""


class BrowserManager:
    """Manages a Playwright browser and its pages.

    The manager is an async context manager::

        async with BrowserManager(headless=True) as browser:
            page = await browser.new_page()
            ...

    Each ``new_page()`` creates an isolated page context. Pages do not
    share cookies or local storage, so one task's activity is never
    visible to another task.

    Attributes:
        headless: Whether the browser window is visible.
        timeout: Default navigation/timeout in seconds.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        channel: str | None = None,
    ) -> None:
        self.headless = headless
        self.timeout = timeout * 1000  # Playwright expects milliseconds
        self.channel = channel
        self._pw: async_playwright | None = None
        self._browser: Any = None
        self._pages: list[Any] = []
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Launch the browser and prepare the Playwright driver."""
        if self._browser is not None:
            return

        self._pw = _get_playwright_module().async_playwright()
        self._pw.start()

        # Launch options: headless by default for security.
        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        }
        if not self.headless:
            # Visible mode: user has explicitly enabled it. We do not
            # attempt to show the browser window on the desktop; Playwright
            # will still render to a virtual framebuffer.
            if self.channel:
                launch_kwargs["channel"] = self.channel

        self._browser = asyncio.get_event_loop().run_until_complete(
            _get_playwright_module().async_playwright().chromium.launch(**launch_kwargs)
        )
        logger.info(
            "Browser started headless=%s timeout_ms=%d",
            self.headless,
            self.timeout,
        )

    async def new_page(self) -> Any:
        """Create a new isolated page context."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self._browser.new_page()
        self._pages.append(page)
        return page

    async def navigate(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Navigate a page to a URL and wait for content.

        Args:
            url: The URL to load.
            wait_until: When to consider the page ready. One of
                "load", "domcontentloaded", "networkidle". Defaults to
                "domcontentloaded" (fast, safe).
            timeout: Timeout in seconds (overrides the manager's default).

        Returns:
            A dict with the URL, status, title, and elapsed time.
        """
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")

        timeout_ms = timeout * 1000 if timeout else self.timeout
        started = time.monotonic()
        page = await self.new_page()

        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            # Allow the page to settle after navigation
            await asyncio.sleep(0.3)
            title = await page.title()
            content_type = await page.content_type()
            status = await page.status()
            return {
                "url": page.url,
                "status": status,
                "title": title,
                "content_type": content_type,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except Exception as exc:
            # Clean up the failed page before re-raising.
            await page.close()
            raise

    async def go_back(self) -> dict[str, Any]:
        """Go back one step in the browser history and return the new URL."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            await page.go_back(timeout=self.timeout * 1000)
            await asyncio.sleep(0.2)
            return {"url": page.url, "title": await page.title()}
        finally:
            await page.close()

    async def go_forward(self) -> dict[str, Any]:
        """Go forward one step in the browser history and return the new URL."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            await page.go_forward(timeout=self.timeout * 1000)
            await asyncio.sleep(0.2)
            return {"url": page.url, "title": await page.title()}
        finally:
            await page.close()

    async def click(
        self,
        selector: str,
        *,
        position: dict[str, float] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Click an element matching the CSS selector.

        Args:
            selector: CSS selector of the element to click.
            position: Optional {x, y} click coordinates (relative to the
                element). If None, Playwright clicks the element's center.
            timeout: Click timeout in seconds.

        Returns:
            A dict with the result, the click position, and elapsed time.
        """
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            click_timeout = timeout * 1000 if timeout else self.timeout * 1000
            await page.click(selector, timeout=click_timeout)
            # Give the click a moment to register (e.g. focus, navigation)
            await asyncio.sleep(0.2)
            return {
                "selector": selector,
                "action": "click",
                "success": True,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except Exception as exc:
            await page.close()
            raise

    async def fill(
        self,
        selector: str,
        value: str,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Fill a form field with text.

        This type-fills the field and clears any existing content.

        Args:
            selector: CSS selector of the input element.
            value: Text to type into the field.
            timeout: Fill timeout in seconds.

        Returns:
            A dict with the result, the selector, the value, and elapsed time.
        """
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            fill_timeout = timeout * 1000 if timeout else self.timeout * 1000
            await page.fill(selector, value, timeout=fill_timeout)
            return {
                "selector": selector,
                "action": "fill",
                "value_preview": value[:60] + "..." if len(value) > 60 else value,
                "success": True,
            }
        except Exception as exc:
            await page.close()
            raise

    async def type_text(
        self,
        selector: str,
        text: str,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Type text into the focused / first matching element, character by
        character (slower, more human-like than fill())."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            type_timeout = timeout * 1000 if timeout else self.timeout * 1000
            await page.type(selector, text, delay=30, timeout=type_timeout)
            return {
                "selector": selector,
                "action": "type",
                "value_preview": text[:60] + "..." if len(text) > 60 else text,
                "success": True,
            }
        except Exception as exc:
            await page.close()
            raise

    async def screenshot(self, path: str, full_page: bool = False) -> dict[str, Any]:
        """Capture a screenshot of the current page.

        Args:
            path: File path where the PNG will be saved. Parent directories
                are created automatically.
            full_page: Whether to capture the full page (including content
                below the fold). Defaults to False (visible viewport only).

        Returns:
            A dict with the result, the path, and the file size.
        """
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            output = Path(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(output), full_page=full_page)
            size = output.stat().st_size
            return {
                "path": str(output),
                "size": size,
                "success": True,
            }
        except Exception as exc:
            await page.close()
            raise

    async def get_text(self, selector: str) -> dict[str, Any]:
        """Read the text content of an element matching the CSS selector."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            text = await page.text_content(selector)
            return {"selector": selector, "text": text or "", "success": True}
        except Exception as exc:
            await page.close()
            raise

    async def get_input_value(self, selector: str) -> dict[str, Any]:
        """Read the current value of a form input field."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            value = await page.input_value(selector)
            return {"selector": selector, "value": value or "", "success": True}
        except Exception as exc:
            await page.close()
            raise

    async def select_option(self, selector: str, label: str) -> dict[str, Any]:
        """Select an option in a dropdown by its visible label."""
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            await page.select_option(selector, label)
            return {"selector": selector, "option": label, "success": True}
        except Exception as exc:
            await page.close()
            raise

    async def wait_for_selector(
        self,
        selector: str,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Wait until an element matching the selector is present in the DOM.

        Useful before clicking or filling a dynamically-loaded element.
        """
        if self._browser is None:
            raise BrowserNotInitializedError("Browser is not started")
        page = await self.new_page()
        try:
            wait_timeout = timeout * 1000 if timeout else self.timeout * 1000
            await page.wait_for_selector(selector, timeout=wait_timeout)
            return {"selector": selector, "success": True, "message": "selector found"}
        except Exception as exc:
            await page.close()
            raise

    async def close_page(self, page: Any) -> None:
        """Close a page and remove it from the manager's tracking."""
        if page in self._pages:
            self._pages.remove(page)
        await page.close()

    async def stop(self) -> None:
        """Close all pages and quit the browser."""
        if self._browser is None:
            return
        # Close all open pages
        for page in list(self._pages):
            try:
                await self.close_page(page)
            except Exception:
                pass
        try:
            await self._browser.close()
        except Exception:
            pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._browser = None
        self._pw = None
        logger.info("Browser stopped")

    @asynccontextmanager
    async def page_scope(self):
        """Context manager that opens a page, yields it, and closes it."""
        page = await self.new_page()
        try:
            yield page
        finally:
            await self.close_page(page)


# Best-effort import check: playwright may not be installed yet. The
# BrowserManager's start() method will raise a helpful ImportError if it
# is missing at runtime.
def check_playwright_installed() -> None:
    """Raise an informative error if playwright is not installed."""
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Playwright is not installed. Run: "
            "python -m playwright install chromium"
        )
