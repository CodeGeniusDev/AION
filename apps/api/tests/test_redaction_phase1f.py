"""Phase 1F: Secret Guard — request-boundary tests.

Assert the contract of routes/chat.py: the REDACTED text — never the raw
credential — is what gets persisted to the conversation store, what the
workflow pipeline and the mocked Gemini service receive, what the
chat-driven approval hook sees and what lands in alert previews. All
stores are fresh in-memory instances via monkeypatch; the real app is
never touched. Detection itself is table-tested in
test_redaction_unit_phase1f.py.
"""

import types
from types import MethodType

import pytest
from fastapi.testclient import TestClient

import routes.chat as chat_routes
import services.chat_approval as chat_approval_mod
import services.gemini as gemini_mod
from main import app
from memory.alert_store import AlertStore
from memory.conversation_store import ConversationStore
from security.redaction import redact_text

client = TestClient(app)


@pytest.fixture
def env(monkeypatch):
    """Fresh in-memory stores + recorded model calls. The real app's
    conversation/alert stores and any live Gemini call can never be hit."""
    conversation_store = ConversationStore(":memory:")
    alert_store = AlertStore(":memory:")
    monkeypatch.setattr(chat_routes, "conversation_store", conversation_store)
    monkeypatch.setattr(chat_routes, "alert_store", alert_store)

    model_calls: list[tuple[str, str]] = []

    async def fake_generate(self, role_instruction: str, prompt: str) -> None:
        model_calls.append((role_instruction, prompt))
        return None  # keeps development_mode behaviour intact

    monkeypatch.setattr(gemini_mod.GeminiService, "generate", fake_generate)

    approval_seen: list[str] = []

    async def fake_approval(message: str, **kwargs):
        approval_seen.append(message)
        return None

    monkeypatch.setattr(
        chat_approval_mod, "handle_chat_desktop_request", fake_approval,
    )
    # Also record what the pipeline receives as the request.
    run_seen: list[str] = []
    real_run = chat_routes.workflow_runner.run

    async def recording_run(self, request, *args, **kwargs):  # bound via MethodType
        run_seen.append(request.message)
        return await real_run(request, *args, **kwargs)

    monkeypatch.setattr(
        chat_routes.workflow_runner, "run", MethodType(recording_run, chat_routes.workflow_runner),
    )

    yield types.SimpleNamespace(
        conversation_store=conversation_store,
        alert_store=alert_store,
        model_calls=model_calls,
        approval_seen=approval_seen,
        run_seen=run_seen,
    )


def _conversation_messages(env) -> list[dict]:
    rows = env.conversation_store.list_conversations(limit=10)
    assert len(rows) == 1
    return [
        {"content": m.content, "role": m.role}
        for m in env.conversation_store.get_messages(rows[0].conversation_id)
    ]


def test_endpoint_returns_warnings_and_redacted_echo(env) -> None:
    response = client.post(
        "/api/chat", json={"message": "my password is hunter2, can you help?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "hunter2" not in body["answer"]
    assert body["warnings"] == ["password removed"]


def test_redacted_text_is_what_gets_persisted(env) -> None:
    client.post("/api/chat", json={"message": "password: hunter2"})
    stored = _conversation_messages(env)[0]["content"]
    assert stored == "password: [REDACTED: password]"
    assert "hunter2" not in stored


def test_model_service_receives_only_redacted_prompt(env) -> None:
    secret = "sk-live-abcdef1234567890abcdef1234567890"
    client.post("/api/chat", json={"message": f"{secret} summarize this"})
    # Whatever the pipeline did, the raw key never reached the model layer.
    for role_instruction, prompt in env.model_calls:
        assert secret not in role_instruction + prompt
    assert env.run_seen, "pipeline never ran"
    assert all(secret not in m for m in env.run_seen)
    assert "[REDACTED: API key]" in env.run_seen[0]


def test_approval_hook_and_alerts_never_see_the_secret(env) -> None:
    client.post("/api/chat", json={"message": "password: hunter2 delete the file"})
    assert all("hunter2" not in m for m in env.approval_seen)
    alerts = env.alert_store.list_all()
    assert alerts
    for alert in alerts:
        assert "hunter2" not in alert["title"] + alert["description"]


def test_benign_message_is_untouched_end_to_end(env) -> None:
    response = client.post("/api/chat", json={"message": "explain password reset flow"})
    assert response.status_code == 200
    assert response.json()["warnings"] == []
    stored = _conversation_messages(env)[0]["content"]
    assert stored == "explain password reset flow"


def test_multiple_secrets_report_every_kind(env) -> None:
    response = client.post(
        "/api/chat",
        json={"message": "password: hunter2 and card 4111 1111 1111 1111"},
    )
    assert response.json()["warnings"] == ["password removed", "card number removed"]
    stored = _conversation_messages(env)[0]["content"]
    assert stored == redact_text("password: hunter2 and card 4111 1111 1111 1111").text
