"""JACC bot launcher with safe Phase 1 bridges.

The original production bot implementation is kept in ``legacy_bot.py``.
This launcher keeps the current Google Sheets flow working while selected
state changes are also mirrored to Supabase during the Phase 1 rollout.
"""

import asyncio
import logging
import os
import traceback

# HTTP client INFO logs include the full Telegram Bot API URL, which contains
# the bot token. Keep request details out of Railway logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import legacy_bot as _legacy
from legacy_bot import *  # noqa: F401,F403 - preserve existing import surface


# This remains OFF until the Phase 1 Accept/Decline callback bridge is ready.
# It lets us deploy and validate the sequential-offer code without changing the
# current production broker broadcast behaviour.
PHASE1_SEQUENTIAL_ENABLED = (
    os.environ.get("PHASE1_SEQUENTIAL_ENABLED", "0").strip() == "1"
)

_original_submit_request = _legacy.submit_request


async def _send_phase1_offer(context, offer, request_data: dict) -> None:
    """Send one guarded Phase 1 offer to the selected broker."""
    if offer.broker_telegram_user_id is None:
        _legacy.logger.warning(
            "Phase 1 offer has no broker Telegram id: offer=%s broker=%s",
            offer.offer_id,
            offer.broker_code,
        )
        return

    service_header = (
        "🏆 *AUCTION CAR ORDER*"
        if offer.service_type == "auction"
        else "🔍 *ကားရှာ ORDER*"
    )
    button_label = (
        "🏆 Auction Order လက်ခံမည်"
        if offer.service_type == "auction"
        else "🔍 ကားရှာ Order လက်ခံမည်"
    )
    keyboard = _legacy.InlineKeyboardMarkup(
        [[
            _legacy.InlineKeyboardButton(
                button_label,
                callback_data=f"p1_accept_{offer.offer_id}",
            ),
            _legacy.InlineKeyboardButton(
                "❌ ငြင်းမည်",
                callback_data=f"p1_decline_{offer.offer_id}",
            ),
        ]]
    )

    await context.bot.send_message(
        chat_id=int(offer.broker_telegram_user_id),
        text=(
            "🔔 *JACC Broker Offer*\n\n"
            f"{service_header}\n"
            f"🆔 `{offer.request_code}`\n"
            f"👷 Broker: `{offer.broker_code}`\n"
            f"🚘 *{request_data.get('car_name', '')}*\n"
            f"📅 နှစ်: {request_data.get('year', '')}\n"
            f"🔧 Grade: {request_data.get('grade', '')}\n"
            f"💰 Budget: {request_data.get('budget', '')}\n"
            f"⭐ Condition: {request_data.get('condition', '')}\n"
            f"⏳ Timeline: {request_data.get('timeline', '')}\n\n"
            "⏱ ၁၀ မိနစ်အတွင်း Accept / Decline လုပ်ပါ။"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def submit_request(context, user_id: int, username: str):
    """Mirror the pending request to Phase 1, then run the legacy flow."""
    req = _legacy.pending_request.get(user_id)
    phase1_request = None
    request_data = dict(req.get("data") or {}) if req else {}

    if req and _legacy.phase1 is not None:
        try:
            phase1_request = (
                await _legacy.phase1.create_request_for_telegram_customer(
                    telegram_user_id=user_id,
                    service_type=(
                        "auction"
                        if request_data.get("service_type") == "auction"
                        else "outside_car"
                    ),
                    form_data={
                        "username": username,
                        "car_name": request_data.get("car_name", ""),
                        "year": request_data.get("year", ""),
                        "grade": request_data.get("grade", ""),
                        "budget": request_data.get("budget", ""),
                        "condition": request_data.get("condition", ""),
                        "timeline": request_data.get("timeline", ""),
                    },
                )
            )
            _legacy.logger.info(
                "Phase 1 request mirrored: %s",
                phase1_request.get("request_code"),
            )

            if PHASE1_SEQUENTIAL_ENABLED:
                offer = await _legacy.phase1.dispatch_next_offer(
                    str(phase1_request["id"])
                )
                if offer is None:
                    _legacy.logger.info(
                        "Phase 1 request waiting for an available broker: %s",
                        phase1_request.get("request_code"),
                    )
                else:
                    await _send_phase1_offer(context, offer, request_data)
                    _legacy.logger.info(
                        "Phase 1 sequential offer sent: request=%s offer=%s broker=%s",
                        offer.request_code,
                        offer.offer_id,
                        offer.broker_code,
                    )
        except _legacy.JaccPhase1Error as exc:
            _legacy.logger.warning(
                "Phase 1 request mirror/dispatch skipped: %s",
                exc,
            )
        except Exception:
            _legacy.logger.exception("Phase 1 request mirror/dispatch failed")

    await _original_submit_request(context, user_id, username)


async def _set_broker_availability(
    telegram_user_id: int,
    accepting_requests: bool,
) -> None:
    if _legacy.phase1 is None:
        return

    try:
        broker = (
            await _legacy.phase1.set_broker_availability_by_telegram_user_id(
                telegram_user_id=telegram_user_id,
                accepting_requests=accepting_requests,
            )
        )
        _legacy.logger.info(
            "Phase 1 broker availability synced: broker=%s accepting=%s",
            broker.get("broker_code"),
            broker.get("accepting_requests"),
        )
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning(
            "Phase 1 broker availability sync skipped: %s",
            exc,
        )
    except Exception:
        _legacy.logger.exception(
            "Phase 1 broker availability sync failed"
        )


async def available_cmd(update, context):
    user_id = str(update.effective_user.id)
    brokers = await _legacy.get_brokers()
    broker = next(
        (b for b in brokers if b.get("telegramId") == user_id),
        None,
    )
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး")
        return

    ok = await _legacy.update_broker(user_id, status="FREE")
    if not ok:
        await update.message.reply_text("❌ Update မအောင်မြင်ပါ")
        return

    await _set_broker_availability(
        telegram_user_id=int(user_id),
        accepting_requests=True,
    )
    await update.message.reply_text(
        f"🟢 *Available ဖြစ်ပြီ*\n\n"
        f"🆔 #{broker['brokerId']}\n"
        "Request လက်ခံနိုင်ပြီ ✅",
        parse_mode="Markdown",
    )


async def busy_cmd(update, context):
    user_id = str(update.effective_user.id)
    brokers = await _legacy.get_brokers()
    broker = next(
        (b for b in brokers if b.get("telegramId") == user_id),
        None,
    )
    if not broker:
        await update.message.reply_text("❌ Broker မဟုတ်ဘူး")
        return

    ok = await _legacy.update_broker(user_id, status="BUSY")
    if not ok:
        await update.message.reply_text("❌ Update မအောင်မြင်ပါ")
        return

    await _set_broker_availability(
        telegram_user_id=int(user_id),
        accepting_requests=False,
    )
    await update.message.reply_text(
        f"🔴 *Busy ဖြစ်ပြီ*\n\n"
        f"🆔 #{broker['brokerId']}\n"
        "Request အသစ် လက်မခံနိုင်တော့ဘူး",
        parse_mode="Markdown",
    )


# Functions defined in legacy_bot resolve these globals at runtime, so
# replacing them here integrates Phase 1 without rewriting the large file.
_legacy.submit_request = submit_request
_legacy.available_cmd = available_cmd
_legacy.busy_cmd = busy_cmd


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
