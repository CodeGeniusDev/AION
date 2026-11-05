"""Voice service: optional STT/TTS with total graceful degradation.

Nothing here executes anything on the user's machine. Server-side TTS
synthesizes audio for the *browser* to play — the desktop "say out loud"
tool remains the bridge's job and stays behind the approval ledger.
STT deliberately happens in the browser (Web Speech API): no audio ever
needs to reach the server, so no microphone or model pipeline lives here.

Every public function returns *data* about availability instead of
raising: a missing optional dependency is a state the UI renders, not a
500. Import probes are lazy and cached per process so tests (and deploys)
can flip availability by injecting into ``sys.modules``.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass

logger = logging.getLogger("aion.voice")

MAX_TTS_CHARS = 1000  # bounded: TTS text is never logged and never huge


@dataclass(frozen=True)
class BackendStatus:
    available: bool
    backend: str
    install_hint: str

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "backend": self.backend,
            "install_hint": None if self.available else self.install_hint,
        }


def _module_importable(name: str) -> bool:
    # find_spec (not __import__) keeps the probe side-effect free; the
    # voice_* tools degrade on *presence*, never on successful heavy init.
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def stt_status() -> BackendStatus:
    """Server-side STT is intentionally not wired: transcription happens
    in the browser (Web Speech API) so voice text enters the normal chat
    path. The status is honest, not a stub."""
    return BackendStatus(
        available=False,
        backend="browser-web-speech",
        install_hint=(
            "Speech recognition runs in the browser (Web Speech API). "
            "No server-side STT package is required or installed."
        ),
    )


def tts_status() -> BackendStatus:
    if _module_importable("edge_tts"):
        return BackendStatus(available=True, backend="edge-tts", install_hint="")
    return BackendStatus(
        available=False,
        backend="edge-tts",
        install_hint="pip install edge-tts (optional; needs internet at synthesis time)",
    )


class VoiceUnavailable(RuntimeError):
    """Raised when TTS is asked for but no backend is installed — the
    route converts this to the structured 'not installed' response."""


async def synthesize(text: str) -> bytes:
    """Synthesize MP3 bytes via edge-tts. Raises VoiceUnavailable when the
    optional dependency is missing; propagates backend errors as
    VoiceUnavailable too, so callers never see third-party tracebacks."""
    if not text.strip():
        raise ValueError("text must not be empty")
    if len(text) > MAX_TTS_CHARS:
        raise ValueError(f"text exceeds {MAX_TTS_CHARS} characters")
    if not tts_status().available:
        raise VoiceUnavailable("No TTS backend installed. " + tts_status().install_hint)
    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
        return bytes(audio)
    except VoiceUnavailable:
        raise
    except Exception as exc:
        # Network failure, service outage, malformed response: one honest type.
        logger.warning("TTS synthesis failed: %s", type(exc).__name__)
        raise VoiceUnavailable(f"Speech synthesis failed: {type(exc).__name__}") from exc
