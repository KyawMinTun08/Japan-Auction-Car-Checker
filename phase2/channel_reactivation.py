"""Telegram channel reactivation for renewed JACC members.

Staged Phase 2 module. Install it before ``legacy_bot.main()`` registers
handlers. It repairs the Telegram-side ban/kick state after membership renewal
so a valid member can use the newly generated channel invite without an admin
manually unbanning the account.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Awaitable, Callable


_legacy: Any | None = None
_original_send_approval_dm: Callable[..., Awaitable[Any]] | None = None
_original_channel_cmd: Callable[..., Awaitable[Any]] | None = None

_MEMBER_STATUSES = {"member", "administrator", "creator", "owner", "restricted"}
_BANNED_STATUSES = {"kicked", "banned"}


def _runtime() -> Any:
    global _legacy
    if _legacy is None:
        import legacy_bot

        _legacy = legacy_bot
    return _legacy


def _chat_member_status(chat_member: object) -> str:
    return str(getattr(chat_member, "status", "") or "").strip().lower()


async def restore_channel_rejoin(context, member_id: int) -> bool:
    """Remove an old Telegram ban/kick while leaving current members untouched.

    ``only_if_banned=True`` makes the operation idempotent. A member who is
    already inside the channel is never removed. When Telegram cannot return a
    membership object, an unban attempt is still made because old kicked users
    are exactly the accounts this repair targets.
    """
    runtime = _runtime()
    member_id = int(member_id)
    channel_id = runtime.CHANNEL_ID
    should_unban = False

    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=channel_id,
            user_id=member_id,
        )
        status = _chat_member_status(chat_member)
        if status in _MEMBER_STATUSES:
            runtime.logger.info(
                "channel reactivation skipped; member %s already has status %s",
                member_id,
                status,
            )
            return True
        should_unban = status in _BANNED_STATUSES
        if not should_unban:
            # LEFT/unknown non-banned users can use an invite normally.
            return True
    except Exception as exc:
        runtime.logger.info(
            "channel status lookup unavailable for %s; trying safe unban: %s",
            member_id,
            exc,
        )
        should_unban = True

    if not should_unban:
        return True

    try:
        await context.bot.unban_chat_member(
            chat_id=channel_id,
            user_id=member_id,
            only_if_banned=True,
        )
        runtime.logger.info(
            "channel rejoin restored for renewed member %s", member_id
        )
        return True
    except Exception as exc:
        runtime.logger.error(
            "channel rejoin restore failed for %s: %s", member_id, exc
        )
        return False


async def _notify_reactivation_failure(context, member_id: int) -> None:
    runtime = _runtime()
    customer_text = (
        "✅ Membership သက်တမ်းတိုးပြီးပါပြီ။\n\n"
        "⚠️ Channel အဟောင်း Ban/Kick ကို Bot က ယခုအချိန်မှာ မဖြုတ်နိုင်သေးပါ။\n"
        "ခဏနေရင် /channel ကို ပြန်နှိပ်ပါ။"
    )
    try:
        await context.bot.send_message(chat_id=int(member_id), text=customer_text)
    except Exception as exc:
        runtime.logger.error(
            "channel restore failure customer notice failed for %s: %s",
            member_id,
            exc,
        )

    notify_admins = getattr(runtime, "notify_admins", None)
    if notify_admins:
        try:
            await notify_admins(
                context,
                "⚠️ Channel auto-unban မအောင်မြင်ပါ။ "
                f"Member ID: {int(member_id)}. Bot channel permissions စစ်ပါ။",
            )
        except Exception as exc:
            runtime.logger.error(
                "channel restore failure admin notice failed for %s: %s",
                member_id,
                exc,
            )


async def send_approval_dm(
    context,
    member_id: int,
    months: int,
    password: str,
    invite_url: str,
    package: str = "CH",
):
    """Restore channel access before delivering the renewal/approval DM."""
    runtime = _runtime()
    original = _original_send_approval_dm
    if original is None:
        raise RuntimeError("channel reactivation is not installed")

    restored = await restore_channel_rejoin(context, int(member_id))
    if restored:
        # A link created before unban becomes usable after the Telegram ban is
        # removed. If the caller had no link, create a fresh one now.
        if not invite_url:
            invite_url = await runtime.create_invite_link(
                context,
                max(1, int(months)) * 30,
            )
        return await original(
            context,
            int(member_id),
            int(months),
            password,
            invite_url,
            package=package,
        )

    # Never send a link that is known to be unusable while the account remains
    # banned. Membership remains active; /channel can retry the repair later.
    await original(
        context,
        int(member_id),
        int(months),
        password,
        "",
        package=package,
    )
    await _notify_reactivation_failure(context, int(member_id))
    return None


async def channel_cmd(update, context):
    """Self-heal an old ban before the existing /channel command creates a link."""
    runtime = _runtime()
    original = _original_channel_cmd
    if original is None:
        raise RuntimeError("channel reactivation is not installed")

    user_id = int(update.effective_user.id)
    if await runtime.is_active_member(user_id):
        restored = await restore_channel_rejoin(context, user_id)
        if not restored:
            await update.message.reply_text(
                "✅ Membership Active ဖြစ်ပါတယ်။\n\n"
                "⚠️ Channel Ban/Kick ကို Bot က မဖြုတ်နိုင်သေးပါ။ "
                "ခဏနေရင် /channel ပြန်နှိပ်ပါ။"
            )
            await _notify_reactivation_failure(context, user_id)
            return None

    return await original(update, context)


def install() -> SimpleNamespace:
    """Patch the legacy runtime before Telegram handlers are registered."""
    global _original_send_approval_dm, _original_channel_cmd

    runtime = _runtime()
    if _original_send_approval_dm is None:
        _original_send_approval_dm = runtime.send_approval_dm
    if _original_channel_cmd is None:
        _original_channel_cmd = runtime.channel_cmd

    runtime.send_approval_dm = send_approval_dm
    runtime.channel_cmd = channel_cmd

    return SimpleNamespace(
        restore_channel_rejoin=restore_channel_rejoin,
        send_approval_dm=send_approval_dm,
        channel_cmd=channel_cmd,
    )
