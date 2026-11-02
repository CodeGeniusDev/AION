"""Phase B.3: startup safety guard tests.

The guard is log-only by contract — these tests pin the decision table
(auth on/off x bridge reachable/dark), verify the warning text names the
dangerous combination, and prove no secret value ever appears in the log.
"""

import logging

import pytest

from services import startup_guard


@pytest.fixture
def caplog_guard(caplog):
    with caplog.at_level(logging.DEBUG, logger="startup_guard"):
        yield caplog


def test_auth_on_is_silent_and_never_probes(caplog_guard) -> None:
    probes = []
    startup_guard.check_startup_safety(
        bridge_reachable=lambda: probes.append(1) or True,
        require_auth=True,
    )
    assert probes == []  # authenticated deployment: no probe, no warning
    assert caplog_guard.records == []


def test_auth_off_bridge_reachable_warns(caplog_guard) -> None:
    startup_guard.check_startup_safety(
        bridge_reachable=lambda: True, require_auth=False
    )
    warnings = [r for r in caplog_guard.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "AION_REQUIRE_AUTH is OFF" in msg
    assert "reachable" in msg
    assert "AION_REQUIRE_AUTH=1" in msg  # tells the operator the fix


def test_auth_off_bridge_dark_is_informational_only(caplog_guard) -> None:
    startup_guard.check_startup_safety(
        bridge_reachable=lambda: False, require_auth=False
    )
    assert [r for r in caplog_guard.records if r.levelno >= logging.WARNING] == []


def test_probe_failure_never_raises(monkeypatch) -> None:
    """The real _bridge_reachable must swallow every transport error —
    startup cannot fail because of a log check."""
    import httpx

    from services.desktop_bridge_client import BridgeError

    def _boom(*a, **k):
        raise BridgeError("bridge unreachable: ConnectError")

    monkeypatch.setattr(httpx, "get", _boom)
    assert startup_guard._bridge_reachable() is False

    def _http_error(*a, **k):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "get", _http_error)
    assert startup_guard._bridge_reachable() is False


def test_warning_never_contains_the_secret(caplog_guard, monkeypatch) -> None:
    from dataclasses import replace

    secret = "super-secret-value-12345"
    monkeypatch.setattr(
        startup_guard, "settings",
        replace(startup_guard.settings, agent_secret=secret),
    )
    startup_guard.check_startup_safety(
        bridge_reachable=lambda: True, require_auth=False
    )
    assert secret not in caplog_guard.text
