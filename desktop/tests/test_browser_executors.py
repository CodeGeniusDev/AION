"""Browser executor tests for the bridge (Phase 4).

Two layers:
1. Executor logic with BrowserManager mocked — proves the bridge
   enforces the URL policy *before* launching anything, ignores the
   requester's ``headless``/``output_path`` params, and derives the
   screenshot path inside the workspace.
2. Real Playwright integration against a local fixture page — skipped
   automatically when playwright or its Chromium build is unavailable.
"""

import asyncio
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aion_desktop import bridge as bridge_module  # noqa: E402
from aion_desktop.browser import BrowserPolicy, UrlBlockedError  # noqa: E402
from aion_desktop.bridge import _executor_for  # noqa: E402

FIXTURE_HTML = b"""<!doctype html>
<html><head><title>AION Phase 4 Fixture</title></head>
<body><h1 id=marker>aion-phase4-fixture</h1></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(FIXTURE_HTML)

    def log_message(self, *args):  # silence the fixture server
        pass


@pytest.fixture()
def fixture_url():
    """Serve the fixture page on an ephemeral (non-admin) port."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/fixture.html"
    server.shutdown()


# ---------------------------------------------------------------------------
# 1. Executor contract (no browser launched)
# ---------------------------------------------------------------------------

class _RecordingManager:
    """Stand-in for BrowserManager recording how it was constructed."""

    instances: list["_RecordingManager"] = []

    def __init__(self, *, headless=True, policy=None, **kwargs):
        self.headless = headless
        self.policy = policy
        self.navigated: list[str] = []
        self.screenshotted: list[str] = []
        _RecordingManager.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def navigate(self, url, **kwargs):
        # Mirrors the real manager: re-validate (redirects live here).
        self.policy.validate(url)
        self.navigated.append(url)
        return {"url": url, "status": 200, "title": "AION Phase 4 Fixture"}

    async def screenshot(self, path, full_page=False):
        self.screenshotted.append(path)
        return {"path": path, "size": 123, "success": True}


@pytest.fixture()
def mock_manager(monkeypatch, tmp_path):
    _RecordingManager.instances = []
    monkeypatch.setattr(bridge_module, "BrowserManager", _RecordingManager)
    return _RecordingManager


def test_navigate_executor_ignores_requester_headless_param(tmp_path, mock_manager):
    """A request must never be able to un-hide the browser."""
    ex = _executor_for(
        "browser_navigate", tmp_path, [],
        browser_policy=BrowserPolicy(), headless=True,
    )
    result = asyncio.run(ex({"url": "https://example.com", "headless": False}))
    assert result["success"] is True
    assert mock_manager.instances[0].headless is True  # config wins, param ignored


def test_navigate_executor_refuses_blocked_url_without_launching(tmp_path, mock_manager):
    ex = _executor_for(
        "browser_navigate", tmp_path, [],
        browser_policy=BrowserPolicy(), headless=True,
    )
    result = asyncio.run(ex({"url": "file:///etc/passwd"}))
    assert result["success"] is False
    assert "URL not permitted" in result["error"]
    assert mock_manager.instances == []  # browser object never constructed


def test_navigate_executor_reports_redirect_violation(tmp_path, mock_manager, monkeypatch):
    policy = BrowserPolicy(denylist=("detour.example",))

    class _Redirecting(mock_manager):
        async def navigate(self, url, **kwargs):
            self.policy.validate(url)
            raise UrlBlockedError("host 'detour.example' is denylisted")

    monkeypatch.setattr(bridge_module, "BrowserManager", _Redirecting)
    ex = _executor_for("browser_navigate", tmp_path, [], browser_policy=policy)
    result = asyncio.run(ex({"url": "https://ok.example/redirects-badly"}))
    assert result["success"] is False
    assert "Redirect not permitted" in result["error"]


def test_screenshot_executor_ignores_output_path_and_uses_url(tmp_path, mock_manager, fixture_url):
    """The caller cannot aim the PNG outside the workspace; the url
    parameter (the only one the chat whitelist even allows) is honored."""
    ex = _executor_for(
        "browser_screenshot", tmp_path, [],
        browser_policy=BrowserPolicy(), headless=True,
    )
    result = asyncio.run(ex({
        "url": fixture_url,
        "output_path": str(tmp_path.parent / "escape.png"),  # ignored
    }))
    assert result["success"] is True
    manager = mock_manager.instances[0]
    assert manager.navigated == [fixture_url]
    written = Path(manager.screenshotted[0])
    assert written.parent == tmp_path          # confined to workspace
    assert written.name.startswith("browser-screenshot-")
    assert "escape.png" not in str(written)


def test_screenshot_executor_refuses_blocked_url(tmp_path, mock_manager):
    ex = _executor_for(
        "browser_screenshot", tmp_path, [],
        browser_policy=BrowserPolicy(), headless=True,
    )
    result = asyncio.run(ex({"url": "http://localhost:8080/admin"}))
    assert result["success"] is False
    assert mock_manager.instances == []


# ---------------------------------------------------------------------------
# 2. Real Playwright integration
# ---------------------------------------------------------------------------

def _playwright_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            Path(p.chromium.executable_path).stat()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(
    not _playwright_ready(), reason="playwright or chromium build not installed"
)


@needs_browser
def test_real_navigate_and_screenshot(tmp_path, fixture_url):
    from aion_desktop.browser import BrowserManager

    async def _run():
        async with BrowserManager(headless=True, policy=BrowserPolicy()) as browser:
            nav = await browser.navigate(fixture_url)
            shot = await browser.screenshot(str(tmp_path / "shot.png"))
            return nav, shot

    nav, shot = asyncio.run(_run())
    assert nav["status"] == 200
    assert nav["title"] == "AION Phase 4 Fixture"
    assert Path(shot["path"]).read_bytes()[:8].startswith(b"\x89PNG")
    assert shot["size"] > 0


@needs_browser
def test_real_navigate_rejects_file_url(tmp_path):
    from aion_desktop.browser import BrowserManager

    async def _run():
        async with BrowserManager(headless=True, policy=BrowserPolicy()) as browser:
            await browser.navigate("file:///etc/passwd")

    with pytest.raises(UrlBlockedError):
        asyncio.run(_run())
