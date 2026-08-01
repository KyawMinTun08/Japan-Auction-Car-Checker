from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

import phase2_membership_guard
from phase2 import payment_callback


class MessageStub:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        del kwargs
        self.messages.append(text)


class QueryStub:
    def __init__(self, data: str, user_id: int = 1) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = MessageStub()
        self.answers: list[tuple[tuple, dict]] = []
        self.markup_removed = False

    async def answer(self, *args, **kwargs) -> None:
        self.answers.append((args, kwargs))

    async def edit_message_reply_markup(self, **kwargs) -> None:
        assert kwargs == {"reply_markup": None}
        self.markup_removed = True


def runtime_stub(*, pending_payment: dict[int, dict], original=None):
    if original is None:
        async def original(update, context):
            del update, context
            return "legacy"

    async def create_invite_link(context, days):
        del context
        return f"https://example.invalid/invite/{days}"

    async def send_approval_dm(*args, **kwargs):
        del args, kwargs

    return SimpleNamespace(
        ADMIN_IDS=[1],
        PLAN_NAMES={"CH": "Standard", "WEB": "Web Premium"},
        pending_payment=pending_payment,
        create_invite_link=create_invite_link,
        send_approval_dm=send_approval_dm,
        button_callback=original,
        logger=logging.getLogger("phase2-payment-callback-test"),
    )


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch):
    monkeypatch.setattr(payment_callback, "_legacy", None)
    monkeypatch.setattr(payment_callback, "_original_button_callback", None)


def payment_data() -> dict:
    return {
        "name": "Member",
        "username": "@member",
        "package": "WEB",
        "months": 2,
        "amount": 55000,
        "method": "kpay",
        "action": "renew",
        "slip_info": {
            "TRANSACTION_NO": "TX-123",
            "AMOUNT": "55000",
            "DATE": "01/08/2026",
            "TIME": "18:30",
        },
    }


def test_non_payment_callback_delegates_unchanged(monkeypatch) -> None:
    calls = []

    async def original(update, context):
        calls.append((update, context))
        return "legacy-result"

    runtime = runtime_stub(pending_payment={}, original=original)
    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    payment_callback.install()

    query = QueryStub("req_budget_100000")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()

    result = asyncio.run(runtime.button_callback(update, context))

    assert result == "legacy-result"
    assert calls == [(update, context)]
    assert query.answers == []


def test_backend_failure_keeps_payment_for_safe_retry(monkeypatch) -> None:
    pending = {123: payment_data()}
    runtime = runtime_stub(pending_payment=pending)
    invite_calls = []
    dm_calls = []

    async def create_invite(*args, **kwargs):
        invite_calls.append((args, kwargs))
        return "should-not-be-created"

    async def send_dm(*args, **kwargs):
        dm_calls.append((args, kwargs))

    async def backend_down(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("network down")

    async def password(member_id, package):
        assert member_id == "123"
        assert package == "WEB"
        return "SECRET-PASSWORD"

    runtime.create_invite_link = create_invite
    runtime.send_approval_dm = send_dm
    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(
        phase2_membership_guard,
        "_post_privileged_sheet",
        backend_down,
    )
    monkeypatch.setattr(
        phase2_membership_guard,
        "resolve_membership_password",
        password,
    )
    payment_callback.install()

    query = QueryStub("slip_ok_123")
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert 123 in pending
    assert invite_calls == []
    assert dm_calls == []
    assert any("Payment data မဖျက်ထားပါ" in text for text in query.message.messages)
    assert query.markup_removed is False


def test_success_uses_backend_expiry_and_clears_only_completed_payment(monkeypatch) -> None:
    pending = {123: payment_data()}
    runtime = runtime_stub(pending_payment=pending)
    dm_calls = []
    backend_calls = []

    async def backend(action, **fields):
        backend_calls.append((action, fields))
        return {
            "status": "ok",
            "expireDate": "30/11/2026",
            "package": "WEB",
            "password": "AUTHORITATIVE-PASSWORD",
            "duplicate": False,
        }

    async def password(member_id, package):
        del member_id, package
        return "PROPOSED-PASSWORD"

    async def send_dm(context, member_id, months, password, invite_url, package):
        dm_calls.append(
            {
                "context": context,
                "member_id": member_id,
                "months": months,
                "password": password,
                "invite_url": invite_url,
                "package": package,
            }
        )

    runtime.send_approval_dm = send_dm
    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(
        phase2_membership_guard,
        "_post_privileged_sheet",
        backend,
    )
    monkeypatch.setattr(
        phase2_membership_guard,
        "resolve_membership_password",
        password,
    )
    payment_callback.install()

    query = QueryStub("slip_ok_123")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(name="context")
    result = asyncio.run(runtime.button_callback(update, context))

    assert result.expire_date == "30/11/2026"
    assert 123 not in pending
    assert backend_calls[0][0] == "approveMembershipPayment"
    assert backend_calls[0][1]["membershipAction"] == "renew"
    assert dm_calls == [
        {
            "context": context,
            "member_id": 123,
            "months": 2,
            "password": "AUTHORITATIVE-PASSWORD",
            "invite_url": "https://example.invalid/invite/60",
            "package": "WEB",
        }
    ]
    admin_text = "\n".join(query.message.messages)
    assert "30/11/2026" in admin_text
    assert "AUTHORITATIVE-PASSWORD" not in admin_text
    assert "01/10/2026" not in admin_text
    assert query.markup_removed is True


def test_duplicate_backend_result_reports_no_double_extension(monkeypatch) -> None:
    pending = {123: payment_data()}
    runtime = runtime_stub(pending_payment=pending)

    async def backend(action, **fields):
        del action, fields
        return {
            "status": "ok",
            "expireDate": "30/11/2026",
            "package": "WEB",
            "password": "EXISTING",
            "duplicate": True,
        }

    async def password(member_id, package):
        del member_id, package
        return "EXISTING"

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(
        phase2_membership_guard,
        "_post_privileged_sheet",
        backend,
    )
    monkeypatch.setattr(
        phase2_membership_guard,
        "resolve_membership_password",
        password,
    )
    payment_callback.install()

    query = QueryStub("slip_ok_123")
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert any("သက်တမ်းကို ထပ်မတိုးပါ" in text for text in query.message.messages)
    assert 123 not in pending


def test_non_admin_cannot_approve(monkeypatch) -> None:
    pending = {123: payment_data()}
    runtime = runtime_stub(pending_payment=pending)
    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    payment_callback.install()

    query = QueryStub("slip_ok_123", user_id=999)
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert 123 in pending
    assert len(query.answers) == 1
    assert query.answers[0][1].get("show_alert") is True
