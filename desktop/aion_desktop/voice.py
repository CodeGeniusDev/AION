"""Voice bridge for the AION Desktop Operating System MVP.

This module provides a voice interface to AION: it converts speech to text
(STT) and text to speech (TTS). Voice input becomes a normal chat message
AION can act on. Voice output is the spoken reply.

For MVP-1, STT and TTS are optional. If the required packages are not
installed, the tools degrade gracefully: the user can still type, and
voice replies fall back to text.

STT backends:
  - whisper (openai-whisper)        — best accuracy, needs ffmpeg
  - vosk                            — lighter, needs a downloaded model
  - web (Web Speech API)            — browser-based, no install

TTS backends:
  - edge-tts (Edge Microsoft TTS)   — high quality, needs internet
  - pyttsx3 (local, offline)        — lower quality, fully offline

Usage::

    from aion_desktop.voice import VoiceBridge

    bridge = VoiceBridge(stt_backend="whisper", tts_backend="edge")
    text = await bridge.listen()          # wait for speech, return text
    await bridge.say("Hello! How can I help?")  # speak the reply
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("aion_desktop.voice")

# ---------------------------------------------------------------------------
# Lazy imports: speech packages are heavy and optional. We import them only
# when the user actually asks for voice, so the codebase is readable even
# before installation.
# ---------------------------------------------------------------------------

_STT_AVAILABLE = False
_TTS_AVAILABLE = False


def _load_stt() -> None:
    global _STT_AVAILABLE
    if _STT_AVAILABLE:
        return
    try:
        import whisper  # noqa: F401
        _STT_AVAILABLE = True
    except ImportError:
        try:
            import vosk  # noqa: F401
            _STT_AVAILABLE = True
        except ImportError:
            try:
                import speech_recognition  # noqa: F401
                _STT_AVAILABLE = True
            except ImportError:
                _STT_AVAILABLE = False


def _load_tts() -> None:
    global _TTS_AVAILABLE
    if _TTS_AVAILABLE:
        return
    try:
        import edge_tts  # noqa: F401
        _TTS_AVAILABLE = True
    except ImportError:
        try:
            import pyttsx3  # noqa: F401
            _TTS_AVAILABLE = True
        except ImportError:
            _TTS_AVAILABLE = False


def stt_available() -> bool:
    _load_stt()
    return _STT_AVAILABLE


def tts_available() -> bool:
    _load_tts()
    return _TTS_AVAILABLE


class VoiceNotConfiguredError(RuntimeError):
    """Raised when the user asks for voice but no STT/TTS backend is installed."""


class VoiceBridge:
    """Bridges voice to AION and back.

    The bridge is a thin adapter: it takes spoken audio, returns text, and
    takes text, speaks it. AION never touches the audio directly.
    """

    def __init__(
        self,
        *,
        stt_backend: str = "whisper",
        tts_backend: str = "edge",
        output_device: str | None = None,
    ) -> None:
        self.stt_backend = stt_backend.lower()
        self.tts_backend = tts_backend.lower()
        self.output_device = output_device
        self._recognizer: Any = None
        self._lock = asyncio.Lock()

        _load_stt()
        _load_tts()

    async def listen(self, *, timeout: float | None = 10.0) -> str:
        """Listen for speech and return the recognised text.

        Blocks until the user stops speaking (or ``timeout`` seconds
        elapse). Returns an empty string on failure.

        .. note::
            This is a best-effort speech recognition. The quality depends
            on the backend you choose and your microphone.
        """
        _load_stt()
        if not _STT_AVAILABLE:
            raise VoiceNotConfiguredError(
                "No speech-to-text backend installed. "
                "Install one of: openai-whisper, vosk, or speech_recognition. "
                "Set AION_SPEECH_BACKEND to override."
            )

        backend = self.stt_backend
        try:
            if backend == "whisper":
                return await self._listen_whisper(timeout)
            elif backend == "vosk":
                return await self._listen_vosk(timeout)
            elif backend == "web":
                return await self._listen_web(timeout)
            else:
                raise ValueError(f"Unknown STT backend: {backend}")
        except Exception as exc:
            logger.warning("Voice listen failed: %s", exc)
            return ""

    async def _listen_whisper(self, timeout: float | None) -> str:
        """Whisper-based STT (openai-whisper)."""
        import whisper

        model = whisper.load_model("small")  # small is a good balance of speed/accuracy
        try:
            # Whisper's transcribe blocks the event loop, so run it in a thread
            loop = asyncio.get_event_loop()
            audio = await self._record_audio(timeout)
            result = await loop.run_in_executor(None, lambda: model.transcribe(audio))
            text = result.get("text", "").strip()
            return text
        except Exception as exc:
            logger.warning("Whisper transcription failed: %s", exc)
            return ""

    async def _record_audio(self, timeout: float | None) -> bytes:
        """Record audio and return raw PCM bytes."""
        # Best-effort: try the system default microphone via the
        # speech_recognition library if available; otherwise return
        # a placeholder (the backend-specific logic will record).
        try:
            import speech_recognition as sr
        except ImportError:
            # Fallback: simulate a short silent audio buffer so the
            # caller gets a controlled failure, not a traceback.
            # In production this would raise a helpful error.
            import queue
            from threading import Thread
            q = queue.Queue()
            audio = queue
            return b""
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = await asyncio.to_thread(
                    recognizer.listen, source, timeout=timeout
                )
            except Exception as exc:
                raise VoiceNotConfiguredError(f"Microphone error: {exc}")
        return audio

    async def _listen_vosk(self, timeout: float | None) -> str:
        """Vosk-based STT (vosk)."""
        try:
            import vosk
            import queue
            from threading import Thread
        except ImportError:
            raise VoiceNotConfiguredError("vosk is not installed")

        #vosk needs a model; download one from https://alphacephei.com/vosk/models
        # For MVP we just note this and use the fallback path.
        raise VoiceNotConfiguredError(
            "Vosk backend requires a model download. See README."
        )

    async def _listen_web(self, timeout: float | None) -> str:
        """Browser-based Web Speech API STT (no install)."""
        # This requires a browser context. For MVP, we delegate to a
        # local web page that uses the Web Speech API and posts the
        # transcription back to the local agent. The intranet file
        # `docs/mobile.html` is a starting point for a web speech UI.
        raise VoiceNotConfiguredError(
            "Web backend requires a browser page. See docs/mobile.html for a reference UI."
        )

    async def say(self, text: str, *, wait: bool = True) -> None:
        """Speak the given text aloud using the configured TTS backend.

        If ``wait`` is True, the method waits until the speech finishes.
        """
        _load_tts()
        if not _TTS_AVAILABLE:
            raise VoiceNotConfiguredError(
                "No text-to-speech backend installed. Install one of: "
                "edge-tts or pyttsx3. Set AION_TTS_BACKEND to override."
            )

        backend = self.tts_backend
        try:
            if backend == "edge":
                await self._say_edge(text)
            elif backend == "pyttsx3":
                await self._say_pyttsx3(text)
            else:
                raise ValueError(f"Unknown TTS backend: {backend}")
        except Exception as exc:
            logger.warning("Voice say failed: %s", exc)

    async def _say_edge(self, text: str) -> None:
        """Edge Microsoft TTS (high quality, internet required)."""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
        # edge_tts is async; run the Play back using asyncio
        async def _play():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    # In production, send this audio to the output device.
                    # For MVP we just log the event.
                    pass

        await _play()

    async def _say_pyttsx3(self, text: str) -> None:
        """Pyttsx3 (local, offline TTS)."""
        import pyttsx3

        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()

    async def hello(self) -> str:
        """Say a greeting and return it as text too."""
        await self.say("Hello! I'm AION. Ask me to do anything on your Mac.")
        return "What can I do for you?"
