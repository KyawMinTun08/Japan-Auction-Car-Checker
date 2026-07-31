"""Final Telegram runtime command patch for JACC.

Python imports ``usercustomize`` after ``sitecustomize``.  This patch therefore
works whether Railway starts ``bot.py`` directly or uses the Procfile launcher.
It preserves the Phase 1 queue bridge and adds the missing admin aliases plus a
clean password-only copy flow.
"""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import ExtBot

import legacy_bot as _legacy


_original_command_handler = _legacy.CommandHandler
_original_start = _legacy.start
_original_set_my_commands = ExtBot.set_my_commands


async def admin_cmd(update, context):
    """Show the JACC admin panel for /admin and /myadmin."""
    message = update.effective_message
    user_id = int(update.effective_user.id)

    if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS:
        await message.reply_text("🚫 ဒီ command ကို Admin သာ အသုံးပြုနိုင်ပါတယ်။")
        return

    await message.reply_text(
        "👑 *JACC Admin Panel*\n\n"
        "📋 `/queue` — Phase 1 Request Queue\n"
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
        "🧾 `/chatlog` — Chat log",
        parse_mode="Markdown",
    )


async def start_router(update, context):
    """Keep /start unchanged and route the two admin aliases."""
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


async def mypassword_cmd(update, context):
    """Send the exact Web password in its own plain-text message."""
    user_id = int(update.effective_user.id)
    message = update.effective_message

    if not await _legacy.is_active_member(user_id):
        await message.reply_text(
            "🔒 Member များသာ သုံးနိုင်ပါသည်\n\nMembership ရယူရန် /start နှိပ်ပါ"
        )
        return

    package = str(await _legacy.get_member_package(user_id) or "").strip().upper()
    if package != "WEB":
        await message.reply_text(
            "🚫 Web Password မရှိပါ\n\n"
            "လက်ရှိ Package: 📱 Standard\n\n"
            "🌐 Web App သုံးဖို့ 💎 Web Premium သို့ Upgrade လုပ်ပါ\n"
            "👉 /renew နှိပ်ပြီး Web Premium ရွေးပါ"
        )
        return

    if not _legacy.SHEET_WEBHOOK:
        await message.reply_text("❌ System error — Admin ကို ဆက်သွယ်ပါ")
        return

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                _legacy.SHEET_WEBHOOK,
                json={"action": "getPassword", "userId": str(user_id)},
                timeout=10,
            )
        response.raise_for_status()
        data = response.json()
        password = str(data.get("password") or "").strip()

        if data.get("status") == "ok" and password:
            await message.reply_text(
                "🔑 Web Password ကို အောက်က message မှာ သီးခြားပို့ထားပါတယ်။\n\n"
                "🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
                "⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့။"
            )
            await context.bot.send_message(chat_id=user_id, text=password)
            return

        await message.reply_text("❌ Password မတွေ့ပါ — Admin ကို ဆက်သွယ်ပါ")
    except Exception:
        _legacy.logger.exception("Patched /mypassword failed")
        await message.reply_text("❌ Error — Admin ကို ဆက်သွယ်ပါ")


def command_handler(command, callback, *args, **kwargs):
    """Add aliases through handler slots already created by legacy_bot.main."""
    if command == "start":
        return _original_command_handler(
            ["start", "admin", "myadmin"],
            start_router,
            *args,
            **kwargs,
        )
    if command == "mypassword":
        callback = mypassword_cmd
    return _original_command_handler(command, callback, *args, **kwargs)


async def set_my_commands(
    self,
    commands,
    scope=None,
    language_code=None,
    *args,
    **kwargs,
):
    """Show Admin Panel and Queue in the private admin command menu."""
    command_list = list(commands)
    if isinstance(scope, BotCommandScopeChat):
        try:
            chat_id = int(scope.chat_id)
        except (TypeError, ValueError):
            chat_id = 0

        if chat_id in _legacy.ADMIN_IDS:
            existing = {item.command for item in command_list}
            if "admin" not in existing:
                command_list.append(BotCommand("admin", "👑 Admin Panel"))
            if "queue" not in existing:
                command_list.append(
                    BotCommand("queue", "📋 Request Queue ကြည့်ရန် (Admin)")
                )

    return await _original_set_my_commands(
        self,
        command_list,
        scope=scope,
        language_code=language_code,
        *args,
        **kwargs,
    )


_legacy.CommandHandler = command_handler
_legacy.mypassword_cmd = mypassword_cmd
ExtBot.set_my_commands = set_my_commands
