"""JACC production launcher with Phase 1 admin broker controls.

Adds two admin-only command aliases without modifying the large legacy bot:

    /brokerfree <broker-code|username|telegram-id>
    /brokerbusy <broker-code|username|telegram-id>

The existing /brokers command continues to work unchanged.
"""

from __future__ import annotations

import asyncio
import traceback

import bot as _bot


_legacy = _bot._legacy
_telegram_command_handler = _legacy.CommandHandler
_original_brokers_cmd = _legacy.brokers_cmd


def _command_handler_with_broker_admin_aliases(command, callback, *args, **kwargs):
    """Register admin aliases together with the existing /brokers handler."""
    if command == "brokers":
        command = ["brokers", "brokerfree", "brokerbusy"]
    return _telegram_command_handler(command, callback, *args, **kwargs)


def _normalise_target(value: str) -> str:
    return value.strip().lstrip("@").lower()


def _find_broker(brokers: list[dict], target: str) -> dict | None:
    wanted = _normalise_target(target)
    for broker in brokers:
        candidates = {
            _normalise_target(str(broker.get("brokerId", ""))),
            _normalise_target(str(broker.get("username", ""))),
            _normalise_target(str(broker.get("telegramId", ""))),
        }
        if wanted in candidates:
            return broker
    return None


async def brokers_admin_cmd(update, context):
    """Keep /brokers and add admin-only FREE/BUSY overrides."""
    message = update.effective_message
    user = update.effective_user
    command = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()

    if command == "/brokers":
        await _original_brokers_cmd(update, context)
        return

    if not _legacy.ADMIN_IDS or user.id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    if not context.args:
        usage = (
            "/brokerfree B4LVV"
            if command == "/brokerfree"
            else "/brokerbusy B4LVV"
        )
        await message.reply_text(f"အသုံးပြုပုံ: `{usage}`", parse_mode="Markdown")
        return

    desired_free = command == "/brokerfree"
    target = context.args[0]
    brokers = await _legacy.get_brokers()
    broker = _find_broker(brokers, target)
    if not broker:
        await message.reply_text(f"❌ Broker `{target}` မတွေ့ပါ", parse_mode="Markdown")
        return

    telegram_id = str(broker.get("telegramId", "")).strip()
    if not telegram_id.isdigit():
        await message.reply_text("❌ Broker Telegram ID မမှန်ပါ")
        return

    legacy_status = "FREE" if desired_free else "BUSY"
    updated = await _legacy.update_broker(telegram_id, status=legacy_status)
    if not updated:
        await message.reply_text("❌ Google Sheet status update မအောင်မြင်ပါ")
        return

    await _bot._set_broker_availability(
        telegram_user_id=int(telegram_id),
        accepting_requests=desired_free,
    )

    emoji = "🟢" if desired_free else "🔴"
    label = "FREE / Available" if desired_free else "BUSY"
    broker_code = broker.get("brokerId", "B???")
    username = broker.get("username", "")

    await message.reply_text(
        f"{emoji} *Broker status ပြောင်းပြီးပါပြီ*\n\n"
        f"🆔 `#{broker_code}`\n"
        f"👤 @{username}\n"
        f"📌 Status: *{label}*",
        parse_mode="Markdown",
    )

    try:
        await context.bot.send_message(
            chat_id=int(telegram_id),
            text=(
                f"{emoji} *Admin က Broker status ပြောင်းထားပါတယ်*\n\n"
                f"🆔 `#{broker_code}`\n"
                f"📌 Status: *{label}*"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        _legacy.logger.exception(
            "Admin broker status DM failed: broker=%s telegram_id=%s",
            broker_code,
            telegram_id,
        )


# legacy_bot.main resolves these globals when it builds handlers.
_legacy.CommandHandler = _command_handler_with_broker_admin_aliases
_legacy.brokers_cmd = brokers_admin_cmd


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
