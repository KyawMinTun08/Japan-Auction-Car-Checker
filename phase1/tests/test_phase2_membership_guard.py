from __future__ import annotations

import asyncio
import logging
from datetime import date
from types import SimpleNamespace

import phase2_membership_guard as guard


def _runtime_stub(**overrides):
    values = {
        "ADMIN_IDS": [],
        "SHEET_WEBHOOK": "https://example.invalid/webhook",
        "logger": logging.getLogger("phase2-membership-test"),
        "PLAN_NAMES": {"CH": "Standard", "WEB": "Web Premium"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalise_member_id_accepts_sheet_number_formats() -> None:
    assert guard.normalise_member_id(123456789) == "123456789"
    assert guard.normalise_member_id(123456789.0) == "123456789"
    assert guard.normalise_member_id("123456789.0") == "123456789"
    assert guard.normalise_member_id(" 123456789 ") == "123456789"


def test_package_aliases_are_canonical() -> None:
    assert guard.normalise_member_package("standard") == "CH"
    assert guard.normalise_member_package("CH-PROMO") == "CH"
    assert guard.normalise_member_package("premium") == "WEB"
    assert guard.normalise_member_package("WEB_PREMIUM") == "WEB"
    assert guard.normalise_member_package("promo-10d") == "PROMO10D"


def test_active_row_requires_status_and_non_expired_date() -> None:
    today = date(2026, 8, 1)
    assert guard.member_row_is_active(
        {"status": " active ", "expireDate": "01/08/2026"},
        today=today,
    )
    assert not guard.member_row_is_active(
        {"status": "ACTIVE", "expireDate": "31/07/2026"},
        today=today,
    )
    assert not guard.member_row_is_active(
        {"status": "EXPIRED", "expireDate": "02/08/2026"},
        today=today,
    )
    assert not guard.member_row_is_active(
        {"status": "ACTIVE", "expireDate": "not-a-date"},
        today=today,
    )


def test_customer_access_fails_closed_when_sheet_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(guard, "_legacy", _runtime_stub())

    async def broken_fetch():
        raise RuntimeError("sheet unavailable")

    monkeypatch.setattr(guard, "_fetch_members", broken_fetch)
    assert asyncio.run(guard.is_active_member(123)) is False
    assert asyncio.run(guard.get_member_package(123)) is None


def test_channel_removal_check_fails_safe_when_sheet_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(guard, "_legacy", _runtime_stub())

    async def broken_fetch():
        raise RuntimeError("sheet unavailable")

    monkeypatch.setattr(guard, "_fetch_members", broken_fetch)
    assert asyncio.run(guard.is_valid_member(123)) is True


class _Message:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.messages.append((text, kwargs))


class _Bot:
    async def get_chat(self, user_id: int):
        return SimpleNamespace(username="member", first_name="Member")


def test_approval_stops_when_sheet_save_fails(monkeypatch) -> None:
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=1),
        message=message,
    )
    context = SimpleNamespace(args=["123", "1", "WEB"], bot=_Bot())

    calls = {"invite": 0, "dm": 0}

    async def save_failed(*args, **kwargs):
        return False

    async def create_invite(*args, **kwargs):
        calls["invite"] += 1
        return "https://example.invalid/invite"

    async def send_dm(*args, **kwargs):
        calls["dm"] += 1

    runtime = _runtime_stub(
        ADMIN_IDS=[1],
        generate_password=lambda: "KMT-TEST",
        save_member_to_sheet=save_failed,
        create_invite_link=create_invite,
        send_approval_dm=send_dm,
    )
    monkeypatch.setattr(guard, "_legacy", runtime)

    asyncio.run(guard.approve_member(update, context))

    assert calls == {"invite": 0, "dm": 0}
    assert any("approve မလုပ်ရသေး" in text for text, _ in message.messages)


def test_promo_uses_canonical_save_member_contract(monkeypatch) -> None:
    captured = {}

    async def save_member(user_id, username, days, password, package):
        captured.update(
            user_id=user_id,
            username=username,
            days=days,
            password=password,
            package=package,
        )
        return True

    runtime = _runtime_stub(
        save_member_to_sheet=save_member,
        generate_password=lambda: "KMT-PROMO",
    )
    monkeypatch.setattr(guard, "_legacy", runtime)

    assert asyncio.run(guard.activate_promo10d(None, 123, "@member")) is True
    assert captured == {
        "user_id": "123",
        "username": "member",
        "days": 10,
        "password": "KMT-PROMO",
        "package": "PROMO10D",
    }
