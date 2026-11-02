"""Voice endpoint schemas — availability is data, never an exception."""

from pydantic import BaseModel, Field


class VoiceStatusResponse(BaseModel):
    stt: dict  # {available, backend, install_hint|None}
    tts: dict


class VoiceSayRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class VoiceSayResponse(BaseModel):
    available: bool
    # When available: base64 MP3 for the browser <audio> element.
    audio_base64: str | None = None
    mime: str | None = None
    # When not: an honest state the UI renders instead of crashing.
    reason: str | None = None
    install_hint: str | None = None
