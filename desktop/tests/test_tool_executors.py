"""Tests for bridge tool executors (no real side effects — subprocess mocked)."""

import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aion_desktop.bridge import _executor_for  # noqa: E402


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def _fake_run_factory(stdout: str, returncode: int = 0):
    def _fake_run(cmd, *args, **kwargs):  # signature mirrors subprocess.run
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)

    return _fake_run


def test_list_apps_parses_comma_separated_osascript_output(workspace, monkeypatch):
    """osascript returns ONE comma-separated line; count must not be 1."""
    canned = "Finder, Chrome, Terminal, WindowServer, Dock"
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(canned))

    executor = _executor_for("desktop_list_apps", workspace, [])
    result = executor({})

    assert result["success"] is True
    assert result["count"] == 5
    assert result["applications"] == ["Finder", "Chrome", "Terminal", "WindowServer", "Dock"]


def test_list_apps_handles_multiline_output_too(workspace, monkeypatch):
    canned = "Finder\nChrome\n\nTerminal\n"
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(canned))

    result = _executor_for("desktop_list_apps", workspace, {})({})

    assert result["count"] == 3
    assert result["applications"] == ["Finder", "Chrome", "Terminal"]


def test_list_apps_returns_empty_on_osascript_failure(workspace, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run_factory("", returncode=1))

    result = _executor_for("desktop_list_apps", workspace, [])({})

    assert result["success"] is True
    assert result["count"] == 0
    assert result["applications"] == []
