# Phase 6 Plan — Voice with graceful degradation

## Goal
Voice text enters the **normal chat path** (so every Phase 2 rule applies
unchanged: the model can only *create* pending approvals, never approve or
execute). STT/TTS backends are optional dependencies; every endpoint
answers with a clear structured "not installed" state instead of
crashing. No large model downloads in this session.

## Decisions (locked before coding)
1. **STT lives in the browser** (Web Speech API, zero deps, already the
   documented "web" backend in desktop/config.yaml). The mic button puts
   the transcript into the chat composer; the message then goes through
   `POST /api/chat` like any typed message. No new server-side audio
   pipeline, no microphone permission questions server-side, no model
   downloads. `openai-whisper`/`vosk` remain *owner-installed options*
   (documented sizes: whisper pulls torch ≈ 1–2 GB — far above the 500 MB
   limit; not installed this session).
2. **Server TTS endpoint** (`POST /api/voice/say`) synthesizes speech from
   text for the *browser* to play. This is not a desktop action and does
   not touch the bridge — the bridge `voice_say` tool (speaks on the
   machine) stays exactly as-is: known, ledgered, approval-gated.
   Backend `edge-tts` (small pure-Python wheel) is optional: installed if
   pip works, every path tested with mocks regardless.
3. `GET /api/voice/status` reports availability of both sides — data, not
   errors (same pattern as `/api/desktop/health`).

## Files
- `apps/api/services/voice_service.py` (NEW) — lazy import probes
  (`stt_status()`, `tts_status()`), `synthesize(text, voice)` returning
  mp3 bytes; `VoiceUnavailable` raised only through the status-shaped
  response path, never a 500.
- `apps/api/routes/voice.py` (NEW) — GET /api/voice/status,
  POST /api/voice/say (200 JSON audio base64+mime, or 200
  {available:false, reason, install_hint}); text length-bounded.
- `apps/api/main.py` — include router under /api.
- `apps/web/components/chat/chat-view.tsx` — mic button (Web Speech API,
  feature-detected; hidden when unsupported). Transcript → composer text.
- `apps/web/utils/speech.ts` (NEW) — minimal typed wrapper for
  `webkitSpeechRecognition` (no deps).
- `desktop/aion_desktop/bridge.py` — voice executors use
  `config.yaml voice.stt / voice.tts` instead of hardcoded defaults
  (config decides, like browser headlessness).
- `desktop/aion_desktop/voice.py` — accept backend names from config;
  unchanged degradation semantics.
- `apps/api/tests/test_voice.py` (NEW) — mocked availability probes +
  mocked edge_tts module (sys.modules injection); status contract;
  say-when-uninstalled returns structured state, not crash.
- `desktop/tests/test_voice_executors.py` (NEW) — executors degrade with
  mocked VoiceBridge; config backend names honored.

## Security invariants (tests prove)
- Voice never becomes an execution path: no route touches the bridge;
  Gemini declarations remain calculator/text_analysis/current_datetime
  (existing tests still pass).
- `voice_say`/`voice_listen` remain in `known_desktop_tools` and, if ever
  requested through chat/desktop routes, go through the same
  approval ledger.
- TTS text is bounded and never logged.

## Commands (end of phase)
backend pytest · desktop pytest · npx tsc --noEmit · npm run lint ·
live E2E: GET /api/voice/status, POST /api/voice/say with mocked/real
edge-tts, browser transcript → chat → (protected tool) pending approval
created via the Phase 2 path (proves rules carry over).

## Risks
- Web Speech API is Chromium/Safari-only → feature-detected button, no
  broken UI elsewhere (documented limitation, honest docs).
- edge-tts needs internet at synthesis time; offline → structured error,
  UI falls back silently.
- Installing edge-tts touches .venv only (≈ small wheel); no models.
