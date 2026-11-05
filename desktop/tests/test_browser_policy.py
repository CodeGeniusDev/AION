"""URL-policy tests for aion_desktop.browser.BrowserPolicy (no browser).

The policy is the Phase 4 security boundary: it must refuse non-http(s)
schemes, loopback admin ports, denylisted hosts, and anything outside a
configured allowlist — before Playwright is ever touched.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aion_desktop.browser import (  # noqa: E402
    DEFAULT_BLOCKED_PORTS,
    BrowserPolicy,
    UrlBlockedError,
    browser_policy_from_config,
)


def _reject(policy: BrowserPolicy, url: str) -> str:
    """Assert ``url`` is refused and return the reason for inspection."""
    with pytest.raises(UrlBlockedError) as exc:
        policy.validate(url)
    return str(exc.value)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "chrome://settings",
    "javascript:alert(1)//",
    "data:text/html,<script>alert(1)</script>",
    "about:blank",
    "ftp://example.com/pub",
    "httpx://example.com",      # unknown scheme
    "//example.com",            # schemeless
])
def test_non_http_schemes_are_refused(url):
    reason = _reject(BrowserPolicy(), url)
    assert "not allowed" in reason or "no host" in reason


@pytest.mark.parametrize("url", [
    "http://localhost:8080/tools/execute",   # the bridge itself
    "http://127.0.0.1:3000/",                # next dev server
    "http://localhost:8010/api/system",      # the AION API
    "http://[::1]:8443/",                    # IPv6 loopback
    "http://0.0.0.0:8000/",
    "http://anything.localhost:8080/",
])
def test_loopback_admin_ports_are_refused(url):
    assert "blocked" in _reject(BrowserPolicy(), url)


@pytest.mark.parametrize("url", [
    "http://localhost:9/?q=dev-port",        # ephemeral fixture port
    "http://127.0.0.1:1234/",
    "http://localhost/",                     # implicit 80, not admin
    "https://example.com/",
    "https://sub.decoricks.com:443/page",
])
def test_permitted_urls_pass(url):
    assert BrowserPolicy().validate(url) == url


def test_denylist_beats_allowlist():
    policy = BrowserPolicy(allowlist=("evil.com",), denylist=("evil.com",))
    assert "denylisted" in _reject(policy, "https://evil.com/x")


def test_allowlist_pins_hosts():
    policy = BrowserPolicy(allowlist=("decoricks.com",))
    assert policy.validate("https://decoricks.com/") == "https://decoricks.com/"
    assert "not allowlisted" in _reject(policy, "https://example.com/")


def test_hostname_case_and_trailing_dot_normalized():
    policy = BrowserPolicy(allowlist=("Example.COM.",))
    policy.validate("https://example.com./x")  # must not raise


def test_malformed_port_refused_not_crashed():
    assert "malformed" in _reject(BrowserPolicy(), "http://localhost:notaport/")


def test_empty_or_hostless_url_refused():
    assert "no host" in _reject(BrowserPolicy(), "")
    assert "no host" in _reject(BrowserPolicy(), "https:///path")


def test_custom_blocked_ports_from_config():
    config = {"browser": {"blocked_ports": [9999]}}
    policy = browser_policy_from_config(config)
    assert "blocked" in _reject(policy, "http://localhost:9999/")
    # default admin ports no longer blocked when overridden explicitly
    policy.validate("http://localhost:8080/")
    assert policy.blocked_ports == (9999,)


def test_defaults_from_empty_config():
    policy = browser_policy_from_config({})
    assert policy.blocked_ports == DEFAULT_BLOCKED_PORTS
    assert policy.allowlist == () and policy.denylist == ()
