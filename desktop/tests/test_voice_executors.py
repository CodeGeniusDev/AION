"""Voice executors: config-driven backends, graceful degradation, no crash.

Proves the Phase 6 bridge contract:
- backend names come from config (passed via ``_executor_for`` kwargs),
  never from request parameters — same policy as browser headlessness;
- a missing optional dependency returns an error *dict* (success=false),
  which the ledger records as a failed execution — it never raises out
  of the executor and never touches the response path unhandled.
"""

from pathlib import Path

import pytest

from aion_desktop import bridge
from aion_desktop.bridge import _executor_for
from aion_desktop.voice import VoiceNotConfiguredError


class RecordingVoiceBridge:
    """Stand-in for VoiceBridge capturing construction + usage."""

    last_kwargs: dict = {}
    say_text: str | None = None
    raise_missing: bool = False

    def __init__(self, *, stt_backend="whisper", tts_backend="edge"):
        RecordingVoiceBridge.last_kwargs = {
            "stt_backend": stt_backend, "tts_backend": tts_backend,
        }

    async def listen(self, *, timeout=None):
        if RecordingVoiceBridge.raise_missing:
            raise VoiceNotConfiguredError("No speech-to-text backend installed.")
        return "write a note to a.txt"

    async def say(self, text, *, wait=True):
        if RecordingVoiceBridge.raise_missing:
            raise VoiceNotConfiguredError("No text-to-speech backend installed.")
        RecordingVoiceBridge.say_text = text


@pytest.fixture(autouse=True)
def fake_bridge(monkeypatch):
    RecordingVoiceBridge.last_kwargs = {}
    RecordingVoiceBridge.say_text = None
    RecordingVoiceBridge.raise_missing = False
    monkeypatch.setattr(bridge, "VoiceBridge", RecordingVoiceBridge)


def _run(tool, params, **kwargs):
    ws = Path("/tmp/aion-test-ws")
    executor = _executor_for(tool, ws, [ws], **kwargs)
    assert executor is not None
    return executor(params)


def test_voice_say_uses_config_backends_not_request_params():
    result = _run(
        "voice_say", {"text": "Done.", "tts_backend": "evil"},
        voice_stt="vosk", voice_tts="pyttsx3",
    )
    assert result["success"] is True
    # Request-supplied backend names are simply ignored:
    assert RecordingVoiceBridge.last_kwargs == {
        "stt_backend": "vosk", "tts_backend": "pyttsx3",
    }
    assert RecordingVoiceBridge.say_text == "Done."


def test_voice_listen_uses_config_backends():
    result = _run("voice_listen", {}, voice_stt="web", voice_tts="edge")
    assert result["success"] is True and result["text"] == "write a note to a.txt"
    assert RecordingVoiceBridge.last_kwargs["stt_backend"] == "web"


def test_missing_backend_degrades_to_error_dict():
    RecordingVoiceBridge.raise_missing = True
    result = _run("voice_say", {"text": "hello"})
    assert result["success"] is False
    assert "backend installed" in result["error"].lower()
    result = _run("voice_listen", {})
    assert result["success"] is False


def test_defaults_are_the_documented_config_values():
    # No kwargs passed (unit-call compatibility): whisper/edge defaults.
    _run("voice_listen", {})
    assert RecordingVoiceBridge.last_kwargs == {
        "stt_backend": "whisper", "tts_backend": "edge",
    }


def test_build_app_reads_voice_backends_from_config(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bridge, "load_config",
        lambda: {
            "workspace_dir": str(tmp_path),
            "allowed_dirs": [str(tmp_path)],
            "voice": {"stt": "vosk", "tts": "pyttsx3"},
        },
    )
    monkeypatch.setattr(bridge, "get_workspace", lambda cfg: tmp_path)
    monkeypatch.setattr(bridge, "get_allowed_dirs", lambda cfg: [tmp_path])
    app = bridge.build_app("unit-test-secret", 8099)
    assert app.state.voice_stt == "vosk"
    assert app.state.voice_tts == "pyttsx3"
