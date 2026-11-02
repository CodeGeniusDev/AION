"""Voice endpoints: status and browser-side speech synthesis.

These routes never touch the desktop bridge and never execute anything.
`/api/voice/say` synthesizes audio for the *browser* to play; the desktop
"say out loud" tool stays in the bridge behind the approval ledger.
A missing optional dependency yields a structured 'not installed' body —
never a crash, never a third-party traceback.
"""

import base64

from fastapi import APIRouter, Depends

from auth.dependency import get_current_principal
from models.voice import VoiceSayRequest, VoiceSayResponse, VoiceStatusResponse
from services import voice_service

router = APIRouter(tags=["voice"])


@router.get("/voice/status", response_model=VoiceStatusResponse)
async def voice_status(
    principal=Depends(get_current_principal),
) -> VoiceStatusResponse:
    """STT/TTS availability. Offline/uninstalled is data, not an error —
    same contract as /api/desktop/health."""
    return VoiceStatusResponse(
        stt=voice_service.stt_status().as_dict(),
        tts=voice_service.tts_status().as_dict(),
    )


@router.post("/voice/say", response_model=VoiceSayResponse)
async def voice_say(
    payload: VoiceSayRequest,
    principal=Depends(get_current_principal),
) -> VoiceSayResponse:
    """Synthesize MP3 for browser playback. Text is bounded (1–1000
    chars) and never logged. When edge-tts is missing or the network
    fails, callers get {available: false, reason, install_hint}."""
    try:
        audio = await voice_service.synthesize(payload.text)
    except voice_service.VoiceUnavailable as exc:
        return VoiceSayResponse(
            available=False,
            reason=str(exc),
            install_hint=voice_service.tts_status().install_hint,
        )
    except ValueError as exc:
        # Defensive: the request model already bounds the text.
        return VoiceSayResponse(available=False, reason=str(exc))
    return VoiceSayResponse(
        available=True,
        audio_base64=base64.b64encode(audio).decode("ascii"),
        mime="audio/mpeg",
    )
