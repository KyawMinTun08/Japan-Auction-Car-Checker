"""Safe production launcher for the current JACC Telegram bot.

Adds /admin and /myadmin without rewriting the large production bot.py file.
All existing commands and behaviour remain in bot.py.
"""

from __future__ import annotations

import asyncio
import traceback

import bot as _bot
from telegram.ext import ExtBot


_original_command_handler = _bot.CommandHandler
_original_start = _bot.start
_original_set_my_commands = ExtBot.set_my_commands


async def admin_cmd(update, context):
    """Show the current production admin command panel."""
    user_id = int(update.effective_user.id)
    message = update.effective_message

    if not _bot.ADMIN_IDS or user_id not in _bot.ADMIN_IDS:
        await message.reply_text("🚫 ဒီ command ကို Admin သာ အသုံးပြုနိုင်ပါတယ်။")
        return

    text = (
        "👑 *JACC Admin Panel*\n\n"
        "✅ `/approve @user 30 WEB` — Member approve\n"
        "👥 `/members` — Member list\n"
        "🚫 `/kick ID` — Member kick\n"
        "🔄 `/renew` — Member renew\n"
        "🔑 `/resetpass @user` — Password reset\n"
        "🆔 `/updateid @user oldID newID` — Telegram ID update\n"
        "💳 `/setqr` — Payment QR setup\n"
        "💾 `/backup` — CSV backup\n"
        "📢 `/broadcast` — Broadcast message\n"
        "👷 `/addbroker` — Broker add\n"
        "🚫 `/kickbroker` — Broker remove\n"
        "📋 `/brokers` — Broker list\n"
        "🏆 `/auctionwon` — Auction won\n"
        "❌ `/auctionlost` — Auction lost\n"
        "💸 `/refunddone` — Refund complete\n"
        "🧾 `/chatlog` — Chat log"
    )
    await message.reply_text(text, parse_mode="Markdown")


async def start_router(update, context):
    """Route /start normally and serve /admin aliases."""
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command in {"/admin", "/myadmin"}:
        await admin_cmd(update, context)
        return
    await _original_start(update, context)


def command_handler_with_admin(command, callback, *args, **kwargs):
    """Register /admin through the existing /start handler slot."""
    if command == "start":
        return _original_command_handler(
            ["start", "admin", "myadmin"],
            start_router,
            *args,
            **kwargs,
        )
    return _original_command_handler(command, callback, *args, **kwargs)


async def set_my_commands_with_admin(self, commands, *args, **kwargs):
    """Add /admin only to private admin command scopes."""
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _bot.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    if is_admin_scope and not any(
        getattr(item, "command", "") == "admin" for item in patched
    ):
        patched.append(_bot.BotCommand("admin", "👑 Admin Panel"))

    return await _original_set_my_commands(self, patched, *args, **kwargs)


_bot.CommandHandler = command_handler_with_admin
ExtBot.set_my_commands = set_my_commands_with_admin


if __name__ == "__main__":
    try:
        asyncio.run(_bot.main())
    except KeyboardInterrupt:
        _bot.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _bot.logger.error("FATAL CRASH: %s", exc)
        _bot.logger.error(traceback.format_exc())
        raise
