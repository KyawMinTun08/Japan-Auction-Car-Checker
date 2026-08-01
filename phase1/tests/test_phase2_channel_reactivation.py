from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import phase2.channel_reactivation as react


def _runtime_stub(**overrides):
    async def active_member(user_id: int) -> bool:
        return True

    values = {
        "CHANNEL_ID": "-1001234567890",
        "logger": logging.getLogger("phase2-channel-reactivation-test"),
        "is_active_member": active_member,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Bot:
    def __init__(self, *, status="left", lookup_error=None, unban_error=None):
        self.status = status
        self.lookup_error = lookup_error
        self.unban_error = unban_error
        self.calls: list[tuple] = []
        self.messages: list[tuple[int, str]] = []

    async def get_chat_member(self, *, chat_id, user_id):
        self.calls.append(("get_chat_member", chat_id, user_id))
        if self.lookup_error:
            raise self.lookup_error
        return SimpleNamespace(status=self.status)

    async def unban_chat_member(
        self, *, chat_id, user_id, only_if_banned=False
    ):
        self.calls.append(
            ("unban_chat_member", chat_id, user_id, only_if_banned)
        )
        if self.unban_error:
            raise self.unban_error
        return True

    async def send_message(self, *, chat_id, text, **kwargs):
        self.calls.append(("send_message", chat_id))
        self.messages.append((int(chat_id), text))
        return SimpleNamespace(message_id=1)


class _Message:
    def __init__(self):
        self.messages: list[str] = []

    async def reply_text(self, text: str, **kwargs):
        self.messages.append(text)


def _context(bot):
    return SimpleNamespace(bot=bot)


def test_banned_member_is_unbanned_idempotently(monkeypatch) -> None:
    bot = _Bot(status="kicked")
    monkeypatch.setattr(react, "_legacy", _runtime_stub())

    assert asyncio.run(react.restore_channel_rejoin(_context(bot), 123)) is True
    assert bot.calls == [
        ("get_chat_member", "-1001234567890", 123),
        ("unban_chat_member", "-1001234567890", 123, True),
    ]


def test_existing_channel_member_is_never_removed(monkeypatch) -> None:
    bot = _Bot(status="member")
    monkeypatch.setattr(react, "_legacy", _runtime_stub())

    assert asyncio.run(react.restore_channel_rejoin(_context(bot), 123)) is True
    assert bot.calls == [("get_chat_member", "-1001234567890", 123)]


def test_unknown_lookup_still_attempts_safe_unban(monkeypatch) -> None:
    bot = _Bot(lookup_error=RuntimeError("member not readable"))
    monkeypatch.setattr(react, "_legacy", _runtime_stub())

    assert asyncio.run(react.restore_channel_rejoin(_context(bot), 123)) is True
    assert bot.calls[-1] == (
        "unban_chat_member",
        "-1001234567890",
        123,
        True,
    )


def test_approval_dm_restores_channel_before_sending_link(monkeypatch) -> None:
    bot = _Bot(status="banned")
    order: list[str] = []
    captured = {}

    original_unban = bot.unban_chat_member

    async def ordered_unban(**kwargs):
        order.append("unban")
        return await original_unban(**kwargs)

    bot.unban_chat_member = ordered_unban

    async def original_send(
        context, member_id, months, password, invite_url, package="CH"
    ):
        order.append("send")
        captured.update(
            member_id=member_id,
            months=months,
            password=password,
            invite_url=invite_url,
            package=package,
        )

    runtime = _runtime_stub(create_invite_link=None)
    monkeypatch.setattr(react, "_legacy", runtime)
    monkeypatch.setattr(react, "_original_send_approval_dm", original_send)

    asyncio.run(
        react.send_approval_dm(
            _context(bot),
            123,
            1,
            "KMT-EXISTING",
            "https://example.invalid/invite",
            package="WEB",
        )
    )

    assert order == ["unban", "send"]
    assert captured["invite_url"] == "https://example.invalid/invite"
    assert captured["package"] == "WEB"


def test_failed_unban_never_sends_known_broken_invite(monkeypatch) -> None:
    bot = _Bot(status="kicked", unban_error=RuntimeError("missing permission"))
    captured = {}
    admin_notices: list[str] = []

    async def original_send(
        context, member_id, months, password, invite_url, package="CH"
    ):
        captured["invite_url"] = invite_url

    async def notify_admins(context, text):
        admin_notices.append(text)

    runtime = _runtime_stub(notify_admins=notify_admins)
    monkeypatch.setattr(react, "_legacy", runtime)
    monkeypatch.setattr(react, "_original_send_approval_dm", original_send)

    asyncio.run(
        react.send_approval_dm(
            _context(bot),
            123,
            1,
            "",
            "https://example.invalid/broken",
            package="CH",
        )
    )

    assert captured["invite_url"] == ""
    assert bot.messages
    assert admin_notices


def test_channel_command_repairs_old_ban_then_runs_existing_command(monkeypatch) -> None:
    bot = _Bot(status="kicked")
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    original_calls: list[int] = []

    async def original_channel_cmd(update, context):
        original_calls.append(update.effective_user.id)

    runtime = _runtime_stub()
    monkeypatch.setattr(react, "_legacy", runtime)
    monkeypatch.setattr(react, "_original_channel_cmd", original_channel_cmd)

    asyncio.run(react.channel_cmd(update, _context(bot)))

    assert original_calls == [123]
    assert (
        "unban_chat_member",
        "-1001234567890",
        123,
        True,
    ) in bot.calls


def test_install_patches_approval_dm_and_channel_command(monkeypatch) -> None:
    async def old_send(*args, **kwargs):
        return None

    async def old_channel(*args, **kwargs):
        return None

    runtime = _runtime_stub(
        send_approval_dm=old_send,
        channel_cmd=old_channel,
    )
    monkeypatch.setattr(react, "_legacy", runtime)
    monkeypatch.setattr(react, "_original_send_approval_dm", None)
    monkeypatch.setattr(react, "_original_channel_cmd", None)

    installed = react.install()

    assert runtime.send_approval_dm is react.send_approval_dm
    assert runtime.channel_cmd is react.channel_cmd
    assert installed.restore_channel_rejoin is react.restore_channel_rejoin
