"""Admin-only Telegram /resetdevice command for JACC Web device binding.

This runtime patch keeps the large legacy bot untouched. It is imported by the
production launcher after queue_launcher has installed its existing command
patches and before legacy_bot.main() registers handlers.
"""

from __future__ import annotations

import os

import queue_launcher as _queue
from telegram.ext import ExtBot


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_original_resetpass_cmd = _legacy.resetpass_cmd
_existing_set_my_commands = ExtBot.set_my_commands


def _sheet_payload(action: str, **values) -> dict:
    """Build a protected Apps Script payload without exposing the server key."""
    payload = {"action": action, **values}
    server_key = os.environ.get("SHEET_SERVER_KEY", "").strip()
    if server_key:
        payload["serverKey"] = server_key
    return payload


async def resetdevice_cmd(update, context):
    """Clear one member's registered Web/PWA device binding."""
    message = update.effective_message
    user_id = int(update.effective_user.id)

    # Fail closed if ADMIN_IDS is missing or the caller is not an admin.
    if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    if not context.args:
        await message.reply_text(
            "အသုံးပြုပုံ: `/resetdevice 123456789`\n\n"
            "Member ရဲ့ Telegram User ID ကို ထည့်ပါ။",
            parse_mode="Markdown",
        )
        return

    target = str(context.args[0] or "").strip().replace(".0", "")
    if not target.isdigit():
        await message.reply_text(
            "❌ User ID မမှန်ပါ\n\n"
            "ဥပမာ: `/resetdevice 123456789`",
            parse_mode="Markdown",
        )
        return

    if not _legacy.SHEET_WEBHOOK:
        await message.reply_text("❌ SHEET_WEBHOOK မသတ်မှတ်ထားပါ")
        return

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                _legacy.SHEET_WEBHOOK,
                json=_sheet_payload("resetMemberDevice", userId=target),
                timeout=15,
            )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        _legacy.logger.error("resetdevice request failed: %s", exc)
        await message.reply_text(
            "❌ Device Reset မအောင်မြင်ပါ\n"
            "Apps Script / Network ကို စစ်ပြီး ပြန်စမ်းပါ။"
        )
        return

    status = str(data.get("status") or "").lower()
    result_message = str(data.get("message") or data.get("msg") or "").lower()

    if status == "ok":
        await message.reply_text(
            "✅ *Device Reset Complete*\n\n"
            f"👤 User ID: `{target}`\n\n"
            "📱 Customer က သုံးမယ့် device အသစ်နဲ့ Website ကို Login "
            "ပြန်ဝင်နိုင်ပါပြီ။",
            parse_mode="Markdown",
        )
        return

    if result_message in {"member_not_found", "not_found"}:
        await message.reply_text(
            f"❌ Member မတွေ့ပါ\n👤 User ID: `{target}`",
            parse_mode="Markdown",
        )
        return

    if result_message in {"unauthorized", "server_key_not_configured"}:
        await message.reply_text(
            "❌ Device Reset authorization မအောင်မြင်ပါ\n"
            "Railway `SHEET_SERVER_KEY` နဲ့ Apps Script `JACC_SERVER_KEY` "
            "တူ/မတူ စစ်ပါ။",
            parse_mode="Markdown",
        )
        return

    if result_message == "device_binding_not_configured":
        await message.reply_text(
            "❌ Device Binding configuration မပြီးသေးပါ\n"
            "Apps Script Script Properties ထဲက `JACC_DEVICE_HASH_SECRET` "
            "နဲ့ binding mode ကို စစ်ပါ။",
            parse_mode="Markdown",
        )
        return

    await message.reply_text(
        "❌ Device Reset မအောင်မြင်ပါ\n"
        f"Backend: `{result_message or 'unknown_error'}`",
        parse_mode="Markdown",
    )


async def resetpass_or_device_router(update, context):
    """Share one registered handler between /resetpass and /resetdevice."""
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/resetdevice":
        await resetdevice_cmd(update, context)
        return
    await _original_resetpass_cmd(update, context)


def _command_handler_with_device_reset(command, callback, *args, **kwargs):
    """Register /resetdevice beside the existing /resetpass handler."""
    if command == "resetpass":
        return _existing_command_handler(
            ["resetpass", "resetdevice"],
            resetpass_or_device_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def _set_my_commands_with_device_reset(self, commands, *args, **kwargs):
    """Show /resetdevice in admin Telegram command menus only."""
    patched = list(commands)
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)

    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    if is_admin_scope:
        existing = {str(command.command).lower() for command in patched}
        if "resetdevice" not in existing:
            patched.append(
                _legacy.BotCommand(
                    "resetdevice",
                    "📱 Member device reset (Admin)",
                )
            )

    return await _existing_set_my_commands(self, patched, *args, **kwargs)


# legacy_bot.main resolves these globals only when it starts registering
# handlers, so applying the patch here is enough and remains reversible.
_legacy.CommandHandler = _command_handler_with_device_reset
_legacy.resetdevice_cmd = resetdevice_cmd
ExtBot.set_my_commands = _set_my_commands_with_device_reset
