from __future__ import annotations

import asyncio
import logging
from datetime import date
from types import SimpleNamespace

import pytest

import phase2_membership_guard as guard


def _runtime_stub(**overrides):
    values = {
        "ADMIN_IDS": [],
        "SHEET_WEBHOOK": "https://example.invalid/webhook",
        "SHEET_SERVER_KEY": "test-server-key",
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


def test_privileged_payload_includes_server_key(monkeypatch) -> None:
    monkeypatch.setattr(guard, "_legacy", _runtime_stub())
    payload = guard.build_privileged_sheet_payload(
        "getPassword", userId="123"
    )
    assert payload == {
        "action": "getPassword",
        "serverKey": "test-server-key",
        "userId": "123",
    }


def test_missing_server_key_fails_before_http(monkeypatch) -> None:
    monkeypatch.setattr(
        guard,
        "_legacy",
        _runtime_stub(SHEET_SERVER_KEY=""),
    )
    monkeypatch.delenv("SHEET_SERVER_KEY", raising=False)

    class ExplodingClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("HTTP client must not be created without a key")

    monkeypatch.setattr(guard.httpx, "AsyncClient", ExplodingClient)
    with pytest.raises(RuntimeError, match="SHEET_SERVER_KEY"):
        asyncio.run(guard._post_privileged_sheet("getMembers"))


def test_get_members_uses_authenticated_payload(monkeypatch) -> None:
    captured = {}

    async def post(action: str, **fields):
        captured.update(action=action, fields=fields)
        return {
            "status": "ok",
            "members": [{"userId": "123", "status": "ACTIVE"}],
        }

    monkeypatch.setattr(guard, "_post_privileged_sheet", post)
    members = asyncio.run(guard._fetch_members())
    assert captured == {"action": "getMembers", "fields": {}}
    assert members[0]["userId"] == "123"


def test_get_password_uses_authenticated_payload(monkeypatch) -> None:
    captured = {}

    async def post(action: str, **fields):
        captured.update(action=action, fields=fields)
        return {"status": "ok", "password": "KMT-EXISTING"}

    monkeypatch.setattr(guard, "_post_privileged_sheet", post)
    password = asyncio.run(guard._fetch_existing_password("123"))
    assert captured == {
        "action": "getPassword",
        "fields": {"userId": "123"},
    }
    assert password == "KMT-EXISTING"


def test_secure_save_uses_canonical_authenticated_contract(monkeypatch) -> None:
    captured = {}

    async def post(action: str, **fields):
        captured.update(action=action, fields=fields)
        return {"status": "ok"}

    monkeypatch.setattr(guard, "_post_privileged_sheet", post)
    saved = asyncio.run(
        guard.save_member_to_sheet_secure(
            "123", "@member", 30, " KMT-NEW ", "premium"
        )
    )
    assert saved is True
    assert captured == {
        "action": "saveMember",
        "fields": {
            "userId": "123",
            "username": "member",
            "days": 30,
            "password": "KMT-NEW",
            "package": "WEB",
        },
    }


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


def test_web_renewal_preserves_existing_password(monkeypatch) -> None:
    runtime = _runtime_stub(
        generate_password=lambda: (_ for _ in ()).throw(
            AssertionError("password must not rotate")
        )
    )
    monkeypatch.setattr(guard, "_legacy", runtime)

    async def existing_password(user_id: str) -> str:
        assert user_id == "123"
        return "KMT-EXISTING"

    monkeypatch.setattr(guard, "_fetch_existing_password", existing_password)
    assert (
        asyncio.run(guard.resolve_membership_password("123", "WEB"))
        == "KMT-EXISTING"
    )


def test_web_upgrade_generates_password_only_when_missing(monkeypatch) -> None:
    runtime = _runtime_stub(generate_password=lambda: "KMT-NEW")
    monkeypatch.setattr(guard, "_legacy", runtime)

    async def no_password(user_id: str) -> str:
        return ""

    monkeypatch.setattr(guard, "_fetch_existing_password", no_password)
    assert asyncio.run(guard.resolve_membership_password("123", "WEB")) == "KMT-NEW"


def test_standard_membership_has_no_web_password(monkeypatch) -> None:
    runtime = _runtime_stub(
        generate_password=lambda: (_ for _ in ()).throw(
            AssertionError("CH must not create a web password")
        )
    )
    monkeypatch.setattr(guard, "_legacy", runtime)
    assert asyncio.run(guard.resolve_membership_password("123", "CH")) == ""


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

    async def password_policy(*args, **kwargs):
        return "KMT-TEST"

    runtime = _runtime_stub(
        ADMIN_IDS=[1],
        generate_password=lambda: "KMT-TEST",
        create_invite_link=create_invite,
        send_approval_dm=send_dm,
    )
    monkeypatch.setattr(guard, "_legacy", runtime)
    monkeypatch.setattr(guard, "resolve_membership_password", password_policy)
    monkeypatch.setattr(guard, "save_member_to_sheet_secure", save_failed)

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

    runtime = _runtime_stub(generate_password=lambda: "KMT-PROMO")
    monkeypatch.setattr(guard, "_legacy", runtime)
    monkeypatch.setattr(guard, "save_member_to_sheet_secure", save_member)

    assert asyncio.run(guard.activate_promo10d(None, 123, "@member")) is True
    assert captured == {
        "user_id": "123",
        "username": "member",
        "days": 10,
        "password": "KMT-PROMO",
        "package": "PROMO10D",
    }


def test_install_replaces_legacy_save_with_secure_version(monkeypatch) -> None:
    runtime = _runtime_stub()
    monkeypatch.setattr(guard, "_legacy", runtime)
    installed = guard.install()
    assert installed.save_member_to_sheet is guard.save_member_to_sheet_secure
    assert runtime.save_member_to_sheet is guard.save_member_to_sheet_secure
