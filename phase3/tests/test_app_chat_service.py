from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from phase3.app_chat.service import (
    AppChatService,
    ChatConfig,
    ChatInputError,
    VerifiedActor,
    _safe_rpc_error,
    _uuid_text,
)


ACTOR = VerifiedActor(
    profile_id="11111111-1111-4111-8111-111111111111",
    telegram_user_id=123456789,
    role="customer",
    member_user_id="123456789",
)
THREAD_ID = "22222222-2222-4222-8222-222222222222"
MESSAGE_ID = "33333333-3333-4333-8333-333333333333"
CLIENT_MESSAGE_ID = "44444444-4444-4444-8444-444444444444"


class FakeVerifier:
    async def verify(self, payload):
        assert payload["auth"]["token"] == "token"
        return ACTOR


class FakeStore:
    def __init__(self):
        self.calls = []

    async def rpc(self, name, payload):
        self.calls.append((name, payload))
        if name == "jacc_chat_send_text":
            return [{
                "message_id": MESSAGE_ID,
                "sender_id": ACTOR.profile_id,
                "sender_role": "customer",
                "source": "app",
                "message_type": "text",
                "body": payload["p_body"],
                "created_at": "2026-08-05T12:00:00+00:00",
            }]
        if name == "jacc_chat_open_by_request_code":
            return [{
                "thread_id": THREAD_ID,
                "request_code": payload["p_request_code"],
                "status": "open",
            }]
        if name == "jacc_chat_list_threads":
            return []
        if name == "jacc_chat_list_messages":
            return []
        if name == "jacc_chat_mark_read":
            return 0
        if name == "jacc_chat_close":
            return "closed"
        raise AssertionError(f"unexpected RPC: {name}")


def make_service(store=None):
    config = ChatConfig(
        sheet_webhook="https://example.invalid/apps-script",
        supabase_url="https://example.invalid",
        service_role_key="server-only-test-key",
        allowed_origins=frozenset({"https://example.com"}),
    )
    return AppChatService(
        config,
        verifier=FakeVerifier(),
        store=store or FakeStore(),
    )


def test_send_text_is_bounded_and_calls_service_role_rpc():
    store = FakeStore()
    service = make_service(store)

    result = asyncio.run(service._send_text({
        "threadId": THREAD_ID,
        "clientMessageId": CLIENT_MESSAGE_ID,
        "body": "  hello broker  ",
    }, ACTOR))

    assert result["ok"] is True
    assert result["message"]["body"] == "hello broker"
    assert store.calls == [(
        "jacc_chat_send_text",
        {
            "p_thread_id": THREAD_ID,
            "p_actor_id": ACTOR.profile_id,
            "p_client_message_id": CLIENT_MESSAGE_ID,
            "p_body": "hello broker",
            "p_source": "app",
        },
    )]


@pytest.mark.parametrize("body", ["", " ", "x" * 4001])
def test_send_text_rejects_empty_or_oversized_body(body):
    service = make_service()
    with pytest.raises(ChatInputError, match="message_length_invalid"):
        asyncio.run(service._send_text({
            "threadId": THREAD_ID,
            "clientMessageId": CLIENT_MESSAGE_ID,
            "body": body,
        }, ACTOR))


def test_open_thread_normalizes_request_code():
    store = FakeStore()
    service = make_service(store)

    result = asyncio.run(service._open_thread({
        "requestCode": " a260805-000001 ",
    }, ACTOR))

    assert result["thread"]["request_code"] == "A260805-000001"
    assert store.calls[0][1]["p_actor_id"] == ACTOR.profile_id


@pytest.mark.parametrize("value", [None, "", "not-a-uuid"])
def test_uuid_parser_rejects_invalid_values(value):
    with pytest.raises(ChatInputError):
        _uuid_text(value, "bad_uuid")


def test_uuid_parser_returns_canonical_text():
    assert _uuid_text(THREAD_ID.upper(), "bad_uuid") == THREAD_ID


def test_rpc_errors_are_redacted_to_public_codes():
    assert _safe_rpc_error(
        'database detail: CHAT_ACCESS_DENIED on public.jacc_chat_threads',
        400,
    ) == "chat_access_denied"
    assert _safe_rpc_error(
        'secret internal relation detail',
        500,
    ) == "chat_backend_http_500"


def test_staged_migration_is_private_and_non_destructive():
    migration = Path("phase3/sql/001_app_chat.sql").read_text(encoding="utf-8")
    lowered = migration.lower()

    assert "enable row level security" in lowered
    assert "revoke all on table public.jacc_chat_messages" in lowered
    assert "grant execute on function public.jacc_chat_send_text" in lowered
    assert "unique (thread_id, sender_id, client_message_id)" in lowered
    assert "drop table" not in lowered
    assert "truncate " not in lowered
    assert "service_role_key" not in lowered


def test_browser_client_contains_no_server_credentials_or_direct_supabase_url():
    client = Path("phase3/app_chat/client.js").read_text(encoding="utf-8")
    lowered = client.lower()

    assert "supabase_service_role_key" not in lowered
    assert "service_role" not in lowered
    assert "/api/v1/chat/send" in client
    assert "JACCDeviceBinding" in client


def test_phase3_is_not_imported_by_current_production_launchers():
    for path in (
        "phase1_production_launcher.py",
        "phase2_production_launcher.py",
        "safe_queue_launcher.py",
        "queue_launcher.py",
    ):
        text = Path(path).read_text(encoding="utf-8")
        assert "phase3.app_chat" not in text
        assert "install_chat_routes" not in text
