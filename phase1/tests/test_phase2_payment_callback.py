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


def test_phase3_approve_calls_privileged_backend_and_hides_password(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})
    backend_calls = []

    async def backend(action, **fields):
        backend_calls.append((action, fields))
        return {
            "ok": True,
            "status": "APPROVED",
            "password": "MUST-NOT-APPEAR",
            "activation": {
                "status": "ok",
                "expireDate": "30/11/2026",
                "package": "WEB",
                "duplicate": False,
            },
            "deliveryFailed": False,
        }

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_approve_WP-ABC12345")
    update = SimpleNamespace(callback_query=query)
    result = asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert result["status"] == "APPROVED"
    assert backend_calls == [
        (
            "approveWebPayment",
            {"paymentId": "WP-ABC12345", "adminId": "1"},
        )
    ]
    assert query.markup_removed is True
    admin_text = "\n".join(query.message.messages)
    assert "30/11/2026" in admin_text
    assert "WEB" in admin_text
    assert "MUST-NOT-APPEAR" not in admin_text
    assert len(query.answers) == 1


def test_phase3_backend_failure_keeps_buttons_for_retry(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})

    async def backend(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("network down")

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_approve_WP-ABC12345")
    update = SimpleNamespace(callback_query=query)
    result = asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert result is None
    assert query.markup_removed is False
    assert any("Button ကို မဖယ်ထားပါ" in text for text in query.message.messages)


def test_phase3_activation_rejection_keeps_buttons_for_retry(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})

    async def backend(*args, **kwargs):
        del args, kwargs
        return {
            "ok": False,
            "error": "MEMBERSHIP_ACTIVATION_FAILED",
            "status": "PENDING",
        }

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_approve_WP-ABC12345")
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert query.markup_removed is False
    assert any("PENDING" in text for text in query.message.messages)


def test_phase3_reject_calls_privileged_backend(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})
    backend_calls = []

    async def backend(action, **fields):
        backend_calls.append((action, fields))
        return {"ok": True, "status": "REJECTED"}

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_reject_WP-ABC12345")
    update = SimpleNamespace(callback_query=query)
    result = asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert result["status"] == "REJECTED"
    assert backend_calls == [
        (
            "rejectWebPayment",
            {
                "paymentId": "WP-ABC12345",
                "adminId": "1",
                "reason": "Rejected by administrator",
            },
        )
    ]
    assert query.markup_removed is True
    assert any("Reject" in text for text in query.message.messages)


def test_phase3_non_admin_is_blocked_before_backend(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})
    backend_calls = []

    async def backend(*args, **kwargs):
        backend_calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_approve_WP-ABC12345", user_id=999)
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert backend_calls == []
    assert query.markup_removed is False
    assert len(query.answers) == 1
    assert query.answers[0][1].get("show_alert") is True


def test_phase3_malformed_payment_id_never_reaches_backend(monkeypatch) -> None:
    runtime = runtime_stub(pending_payment={})
    backend_calls = []

    async def backend(*args, **kwargs):
        backend_calls.append((args, kwargs))
        return {"ok": True}

    monkeypatch.setattr(payment_callback, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_post_privileged_sheet", backend)
    payment_callback.install()

    query = QueryStub("webpay_approve_not-valid")
    update = SimpleNamespace(callback_query=query)
    asyncio.run(runtime.button_callback(update, SimpleNamespace()))

    assert backend_calls == []
    assert query.markup_removed is False
    assert any("Payment ID မမှန်" in text for text in query.message.messages)
