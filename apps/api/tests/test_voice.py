"""Phase 6 voice tests: graceful degradation and zero execution power.

The two things these tests pin down:
1. An uninstalled optional dependency is a structured state, never a
   crash — /api/voice/status and /api/voice/say both answer 200 with
   honest availability data.
2. Voice is not an execution path: hitting these endpoints creates no
   approval, no task and provably no bridge call. (Real transcription
   enters the ordinary /api/chat path in the browser, where every
   Phase 2 rule already applies.)
"""

import base64

import pytest
from fastapi.testclient import TestClient

from main import app
from services import voice_service

client = TestClient(app)


# ---------------------------------------------------------------------------
# Status contract
# ---------------------------------------------------------------------------

def test_voice_status_reports_availability_as_data(monkeypatch):
    monkeypatch.setattr(
        voice_service, "tts_status",
        lambda: voice_service.BackendStatus(False, "edge-tts", "pip install edge-tts"),
    )
    response = client.get("/api/voice/status")
    assert response.status_code == 200
    body = response.json()
    assert body["tts"] == {
        "available": False, "backend": "edge-tts",
        "install_hint": "pip install edge-tts",
    }
    # STT is browser-side by design — the status must say so, honestly.
    assert body["stt"]["backend"] == "browser-web-speech"


def test_tts_status_probe_reflects_installed_module():
    # edge-tts is installed in this venv; the probe must see it. When it
    # is absent the same probe returns available=False — no crash either
    # way, which is the whole degradation story.
    status = voice_service.tts_status()
    assert status.backend == "edge-tts"
    assert status.available is (voice_service._module_importable("edge_tts"))


# ---------------------------------------------------------------------------
# Say contract — mocked backends only (no network in tests)
# ---------------------------------------------------------------------------

def test_say_returns_structured_not_installed_state(monkeypatch):
    async def unavailable(text: str) -> bytes:
        raise voice_service.VoiceUnavailable("No TTS backend installed.")

    monkeypatch.setattr(voice_service, "synthesize", unavailable)
    monkeypatch.setattr(
        voice_service, "tts_status",
        lambda: voice_service.BackendStatus(False, "edge-tts", "pip install edge-tts"),
    )
    body = client.post("/api/voice/say", json={"text": "hello"}).json()
    assert body["available"] is False
    assert "No TTS backend" in body["reason"]
    assert body["install_hint"] == "pip install edge-tts"
    assert body["audio_base64"] is None


def test_say_synthesizes_via_mocked_backend(monkeypatch):
    async def fake_synth(text: str) -> bytes:
        return b"FAKEMP3"

    monkeypatch.setattr(voice_service, "synthesize", fake_synth)
    body = client.post("/api/voice/say", json={"text": "speak this"}).json()
    assert body["available"] is True
    assert body["mime"] == "audio/mpeg"
    assert base64.b64decode(body["audio_base64"]) == b"FAKEMP3"


def test_say_bounds_text_length():
    too_long = client.post("/api/voice/say", json={"text": "x" * 1001})
    assert too_long.status_code == 422
    empty = client.post("/api/voice/say", json={"text": ""})
    assert empty.status_code == 422


def test_voice_endpoints_never_create_approvals_or_touch_bridge(monkeypatch):
    """The Phase 2 invariants carry over to voice: no approval rows, and
    the approval service's bridge client is replaced by a recorder that
    must stay empty after every voice call."""
    from memory.approval_store import ApprovalStore
    import services.approval_service as module

    class ExplodingBridge:
        def health(self): raise AssertionError("voice must not probe the bridge")
        def register_grant(self, *a, **k): raise AssertionError("no grants from voice")
        def execute(self, *a, **k): raise AssertionError("voice must not execute")

    fresh_store = ApprovalStore(":memory:")
    original_store = module._default_approval_service.store
    original_bridge = module._default_approval_service._bridge_client
    module._default_approval_service.store = fresh_store
    module._default_approval_service._bridge_client = ExplodingBridge()

    async def fake_synth(text: str) -> bytes:
        return b"x"

    monkeypatch.setattr(voice_service, "synthesize", fake_synth)
    try:
        assert client.get("/api/voice/status").status_code == 200
        assert client.post("/api/voice/say", json={"text": "open my files"}).status_code == 200
        assert fresh_store.list(tenant_id="default") == []
    finally:
        module._default_approval_service.store = original_store
        module._default_approval_service._bridge_client = original_bridge


def test_synthesize_rejects_empty_and_huge_without_backend():
    # Validation happens before any backend use — cheap, deterministic.
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(voice_service.synthesize("   "))
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(voice_service.synthesize("x" * (voice_service.MAX_TTS_CHARS + 1)))
