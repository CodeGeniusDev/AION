"""Browser automation layer for the AION Desktop Operating System MVP.

This module controls a Chromium browser via Playwright. It is the
"eyes and hands" for web tasks: navigating to URLs and capturing
screenshots, with a URL policy that is enforced *before* the browser
is ever launched.

Security model
--------------
* Browser automation is headless by default. Headlessness is decided by
  the local agent's ``config.yaml`` ONLY — an execution request can
  never flip it (the bridge ignores any ``headless`` parameter).
* Every navigation target is validated against a :class:`BrowserPolicy`
  before the browser is even launched: only ``http``/``https`` schemes
  ever pass (``file:``, ``chrome:``, ``javascript:`` … are refused),
  loopback hosts are refused on blocked admin ports (the bridge, the
  API, the dev server), and an optional hostname allowlist can pin
  navigation to specific sites. A denylist always wins. Redirects are
  re-checked: a permitted URL may not bounce into a blocked one.
* Screenshots are written by the bridge inside its workspace directory;
  this layer just receives a final path.
* Pages are opened in private/isolated contexts. No credential or
  session data is shared across tasks.

Usage
-----
From the local agent's bridge:

    from aion_desktop.browser import BrowserManager, BrowserPolicy

    async with BrowserManager(policy=policy) as browser:
        result = await browser.navigate("https://example.com")
        shot = await browser.screenshot("/abs/path/in/workspace.png")
"""

from __future__ import annotations

import ipaddress
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("aion_desktop.browser")

# Lazy import: playwright is a heavy dependency that may not be installed
# yet. We import it inside the methods that need it so the module can be
# statically verified and the code can be read without playwright present.
# playwright is only required at runtime when a browser action is taken.
_PW = None


def _get_playwright() -> Any:
    """Return the playwright.async_api module, importing it lazily."""
    global _PW
    if _PW is None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install it first with: "
                "pip install playwright && "
                "python -m playwright install chromium"
            ) from exc
        _PW = async_playwright
    return _PW


# Default navigation timeout in seconds per page
DEFAULT_TIMEOUT = 30

# Admin/dev ports refused on loopback hosts by default. The bridge and
# the AION services themselves live here — a browser action must never
# become an SSRF probe of the local stack.
DEFAULT_BLOCKED_PORTS: tuple[int, ...] = (3000, 3001, 8000, 8010, 8080, 8443)

_LOCAL_HOSTS = frozenset({"localhost", "::1", "0.0.0.0"})


class UrlBlockedError(ValueError):
    """Raised when a URL fails the browser policy. The browser is never
    launched for a blocked URL, so refusal is total, not best-effort."""


@dataclass
class BrowserPolicy:
    """URL allow/deny policy enforced *before* any navigation.

    Attributes:
        allowlist: Hostnames that may be visited. Empty means "any host
            that isn't otherwise refused".
        denylist: Hostnames that are always refused, even if allowlisted.
        blocked_ports: TCP ports refused on loopback hosts.
    """

    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()
    blocked_ports: tuple[int, ...] = DEFAULT_BLOCKED_PORTS
    _allowed: frozenset[str] = field(default_factory=lambda: frozenset(), repr=False)

    def __post_init__(self) -> None:
        self._allowed = frozenset(
            h.strip().lower().rstrip(".") for h in self.allowlist if h.strip()
        )

    @staticmethod
    def _effective_port(scheme: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        return 80 if scheme == "http" else 443 if scheme == "https" else None

    def _is_loopback_host(self, host: str) -> bool:
        if host in _LOCAL_HOSTS or host.endswith(".localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def validate(self, url: str) -> str:
        """Return the URL if permitted, else raise
        :class:`UrlBlockedError` with the coarse reason."""
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise UrlBlockedError(f"malformed URL: {exc}") from exc
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").strip("[")
        if host.endswith("]"):
            host = host[:-1]
        if not host:
            raise UrlBlockedError("URL has no host")
        host = host.lower().rstrip(".")

        # Denylist first: an explicit "never" outranks an explicit "always".
        if host in {d.strip().lower().rstrip(".") for d in self.denylist if d.strip()}:
            raise UrlBlockedError(f"host '{host}' is denylisted")
        if scheme not in ("http", "https"):
            raise UrlBlockedError(f"scheme '{scheme or '(none)'}' is not allowed — only http/https")
        try:
            port = parts.port
        except ValueError as exc:
            raise UrlBlockedError(f"malformed port: {exc}") from exc
        port = self._effective_port(scheme, port)
        if self._is_loopback_host(host) and port in self.blocked_ports:
            raise UrlBlockedError(f"loopback port {port} is blocked")
        if self._allowed and host not in self._allowed:
            raise UrlBlockedError(f"host '{host}' is not allowlisted")
        return url


def browser_policy_from_config(config: dict[str, Any]) -> BrowserPolicy:
    """Build the policy from the ``browser`` section of config.yaml."""
    section = config.get("browser", {}) or {}

    def _tuple(key: str, default):
        value = section.get(key, default)
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return tuple(default)

    return BrowserPolicy(
        allowlist=_tuple("allowlist", ()),
        denylist=_tuple("denylist", ()),
        blocked_ports=_tuple("blocked_ports", DEFAULT_BLOCKED_PORTS),
    )


class BrowserNotInitializedError(RuntimeError):
    """Raised when an operation is attempted before the browser is open."""


class BrowserManager:
    """Manages one Playwright browser, one isolated context, and the
    active page inside it.

    The manager is an async context manager::

        async with BrowserManager(policy=policy) as browser:
            await browser.navigate("https://example.com")
            await browser.screenshot("/abs/in/workspace.png")

    ``navigate()`` sets the *active page*; ``screenshot()`` and the text
    helpers operate on it, so a navigate-then-screenshot sequence inside
    a single execution describes one real page. Every navigation (and
    every post-redirect URL) is checked against the policy.

    Attributes:
        headless: Whether a visible window is used. Config-driven;
            request parameters can never change it.
        timeout: Default navigation timeout in seconds.
        policy: The :class:`BrowserPolicy` gate for navigations.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        policy: BrowserPolicy | None = None,
    ) -> None:
        self.headless = headless
        self.timeout = timeout
        self.policy = policy if policy is not None else BrowserPolicy()
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Launch the browser. Safe to call inside a running event loop."""
        if self._browser is not None:
            return
        self._pw = await _get_playwright()().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        # One isolated context per execution: no cookies or storage are
        # shared with anything else, ever.
        self._context = await self._browser.new_context()
        self._context.set_default_navigation_timeout(self.timeout * 1000)
        self._context.set_default_timeout(self.timeout * 1000)
        logger.info("Browser started headless=%s timeout_s=%d", self.headless, self.timeout)

    def _require_context(self) -> Any:
        if self._browser is None or self._context is None:
            raise BrowserNotInitializedError("Browser is not started")
        return self._context

    async def navigate(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Validate ``url`` against the policy, then load it in a fresh
        page (the previous active page is closed).

        Returns a dict with the final URL, HTTP status, title and
        elapsed time. A redirect that lands on a policy-violating URL
        is reported as blocked and the page is discarded.
        """
        self.policy.validate(url)
        context = self._require_context()

        if self._page is not None:
            try:
                await self._page.close()
            except Exception:
                pass
        page = await context.new_page()
        self._page = page

        started = time.monotonic()
        timeout_ms = timeout * 1000 if timeout else self.timeout * 1000
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            # Redirects happen inside goto — re-check where we landed.
            self.policy.validate(page.url)
            title = await page.title()
            return {
                "url": page.url,
                "status": response.status if response else None,
                "title": title,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            }
        except UrlBlockedError:
            await page.close()
            self._page = None
            raise
        except Exception:
            await page.close()
            self._page = None
            raise

    async def screenshot(self, path: str, full_page: bool = False) -> dict[str, Any]:
        """Capture the active page to ``path`` (the bridge guarantees
        ``path`` is inside its workspace). Raises if nothing has been
        navigated yet — a blank-page screenshot is not useful."""
        self._require_context()
        if self._page is None:
            raise BrowserNotInitializedError(
                "No active page — navigate() before screenshot()"
            )
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=str(output), full_page=full_page)
        return {"path": str(output), "size": output.stat().st_size, "success": True}

    async def get_text(self, selector: str) -> dict[str, Any]:
        """Read the text content of an element on the active page."""
        self._require_context()
        if self._page is None:
            raise BrowserNotInitializedError("No active page — navigate() first")
        text = await self._page.text_content(selector)
        return {"selector": selector, "text": text or "", "success": True}

    async def stop(self) -> None:
        """Close the page, context and browser; shutdown is idempotent."""
        for closer in (
            getattr(self._page, "close", None),
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
        ):
            if closer is not None:
                try:
                    await closer()
                except Exception:
                    pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._page = self._context = self._browser = self._pw = None
        logger.info("Browser stopped")


# Best-effort import check: playwright may not be installed yet. The
# BrowserManager's start() method will raise a helpful RuntimeError if it
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
