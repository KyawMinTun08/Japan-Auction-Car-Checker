"""JACC bot launcher with safe Phase 1 bridges.

The original production bot implementation is kept in ``legacy_bot.py``.
This launcher keeps the current Google Sheets flow available as a fallback while
Phase 1 sequential broker offers are enabled through an environment flag.
"""

import asyncio
import logging
import os
import traceback
from typing import Any

# HTTP client INFO logs can include the full Telegram Bot API URL, which contains
# the bot token. Keep request details out of Railway logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import legacy_bot as _legacy
from legacy_bot import *  # noqa: F401,F403 - preserve existing import surface


# Keep this OFF until a broker is marked /available and the pilot is ready.
PHASE1_SEQUENTIAL_ENABLED = (
    os.environ.get("PHASE1_SEQUENTIAL_ENABLED", "0").strip() == "1"
)

_original_submit_request = _legacy.submit_request
_original_button_callback = _legacy.button_callback


async def _phase1_get_single(
    table: str,
    *,
    filters: dict[str, str],
    select: str,
) -> dict[str, Any]:
    """Read one Phase 1 row through the server-side Supabase connection."""
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    params = {**filters, "select": select, "limit": "1"}
    async with _legacy.httpx.AsyncClient(
        timeout=_legacy.phase1._timeout
    ) as client:
        response = await client.get(
            url,
            headers=_legacy.phase1._headers,
            params=params,
        )

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Phase 1 lookup failed ({response.status_code}): "
            f"{response.text[:500]}"
        )

    rows = response.json()
    if not rows:
        raise _legacy.JaccPhase1Error(
            f"PHASE1_ROW_NOT_FOUND:{table}"
        )
    return rows[0]


async def _get_offer_context(offer_id: str) -> dict[str, Any]:
    offer = await _phase1_get_single(
        "jacc_request_offers",
        filters={"id": f"eq.{offer_id}"},
        select="id,request_id,broker_id,status,expires_at",
    )
    request = await _phase1_get_single(
        "jacc_service_requests",
        filters={"id": f"eq.{offer['request_id']}"},
        select=(
            "id,request_code,customer_id,service_type,service_channel,"
            "status,form_data"
        ),
    )
    customer = await _phase1_get_single(
        "jacc_profiles",
        filters={"id": f"eq.{request['customer_id']}"},
        select="id,display_name,telegram_user_id,account_active",
    )
    broker = await _phase1_get_single(
        "jacc_broker_profiles",
        filters={"user_id": f"eq.{offer['broker_id']}"},
        select="user_id,broker_code,account_status,accepting_requests",
    )
    return {
        "offer": offer,
        "request": request,
        "customer": customer,
        "broker": broker,
    }


def _friendly_phase1_error(exc: Exception) -> str:
    message = str(exc).upper()
    if "OFFER_EXPIRED" in message or "VALID_PENDING_OFFER_NOT_FOUND" in message:
        return "⏱ Offer သက်တမ်းကုန်သွားပြီ"
    if "OFFER_NOT_PENDING" in message:
        return "ဒီ Offer ကို အရင်တုံ့ပြန်ပြီးသားပါ"
    if "OFFER_NOT_OWNED_BY_BROKER" in message:
        return "ဒီ Offer က သင့်အတွက်မဟုတ်ပါ"
    if "REQUEST_ALREADY_ASSIGNED" in message:
        return "ဒီ Request ကို အခြား Broker လက်ခံပြီးပါပြီ"
    if "BROKER_SERVICE_CAPACITY_FULL" in message:
        return "ဒီ Service အမျိုးအစားအတွက် သင့် Slot ပြည့်နေပါတယ်"
    return "Phase 1 လုပ်ဆောင်မှု မအောင်မြင်ပါ"


async def _send_phase1_offer(context, offer, request_data: dict) -> bool:
    """Send one 10-minute Phase 1 offer to the selected broker."""
    if offer.broker_telegram_user_id is None:
        _legacy.logger.warning(
            "Phase 1 offer has no broker Telegram id: offer=%s broker=%s",
            offer.offer_id,
            offer.broker_code,
        )
        return False

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
    return True


async def _save_request_to_legacy_sheet(
    *,
    request_code: str,
    user_id: int,
    username: str,
    request_data: dict[str, Any],
) -> None:
    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(
                _legacy.SHEET_WEBHOOK,
                json={
                    "action": "addRequest",
                    "reqId": request_code,
                    "customerId": str(user_id),
                    "username": username,
                    "carType": (
                        "Auction"
                        if request_data.get("service_type") == "auction"
                        else "Search"
                    ),
                    "budget": request_data.get("budget", ""),
                    "year": request_data.get("year", ""),
                    "grade": request_data.get("grade", ""),
                    "condition": request_data.get("condition", ""),
                    "timeline": request_data.get("timeline", ""),
                },
                timeout=10,
            )
    except Exception:
        _legacy.logger.exception(
            "Phase 1 request backup to Google Sheet failed: %s",
            request_code,
        )


async def submit_request(context, user_id: int, username: str):
    """Use one sequential Phase 1 offer, with the legacy flow as fallback."""
    req = _legacy.pending_request.get(user_id)
    request_data = dict(req.get("data") or {}) if req else {}

    if (
        not PHASE1_SEQUENTIAL_ENABLED
        or not req
        or _legacy.phase1 is None
    ):
        # During rollout, continue mirroring for validation while preserving the
        # existing production behaviour.
        if req and _legacy.phase1 is not None:
            try:
                mirrored = await _legacy.phase1.create_request_for_telegram_customer(
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
                _legacy.logger.info(
                    "Phase 1 request mirrored: %s",
                    mirrored.get("request_code"),
                )
            except _legacy.JaccPhase1Error as exc:
                _legacy.logger.warning(
                    "Phase 1 request mirror skipped: %s",
                    exc,
                )
            except Exception:
                _legacy.logger.exception("Phase 1 request mirror failed")
        await _original_submit_request(context, user_id, username)
        return

    try:
        phase1_request = await _legacy.phase1.create_request_for_telegram_customer(
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
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning(
            "Phase 1 sequential submit unavailable; legacy fallback: %s",
            exc,
        )
        await _original_submit_request(context, user_id, username)
        return
    except Exception:
        _legacy.logger.exception(
            "Phase 1 sequential submit failed; legacy fallback"
        )
        await _original_submit_request(context, user_id, username)
        return

    # The central database now owns this request. Do not call the legacy submit
    # function because it broadcasts the same request to every broker.
    _legacy.pending_request.pop(user_id, None)
    request_code = str(phase1_request["request_code"])

    await _save_request_to_legacy_sheet(
        request_code=request_code,
        user_id=user_id,
        username=username,
        request_data=request_data,
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅ *Request တင်ပြီ!*\n\n"
            f"🆔 Request ID: `{request_code}`\n"
            f"🚗 {request_data.get('car_name', '')}\n"
            f"💰 {request_data.get('budget', '')}\n\n"
            "Broker ရွေးချယ်နေပါတယ် ⏳"
        ),
        parse_mode="Markdown",
    )

    try:
        offer = await _legacy.phase1.dispatch_next_offer(
            str(phase1_request["id"])
        )
        if offer is None:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "⏳ လက်ရှိ Available Broker မရှိသေးပါ။\n"
                    "Broker Available ဖြစ်တာနဲ့ အလိုအလျောက်ပို့ပါမယ်။"
                ),
            )
            _legacy.logger.info(
                "Phase 1 request waiting for broker: %s",
                request_code,
            )
        else:
            await _send_phase1_offer(context, offer, request_data)
            _legacy.logger.info(
                "Phase 1 sequential offer sent: request=%s offer=%s broker=%s",
                offer.request_code,
                offer.offer_id,
                offer.broker_code,
            )
    except Exception:
        _legacy.logger.exception(
            "Phase 1 initial offer dispatch failed: %s",
            request_code,
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="⏳ Request သိမ်းပြီးပါပြီ။ Broker ချိတ်ဆက်မှုကို စောင့်နေပါတယ်။",
        )

    await _legacy.notify_admins(
        context,
        (
            "📥 *Phase 1 Request အသစ်*\n\n"
            f"🆔 `{request_code}`\n"
            f"📌 {'🏆 လေလံ' if request_data.get('service_type') == 'auction' else '🔍 ကားရှာ'}\n"
            f"👤 @{username}\n"
            f"🚘 {request_data.get('car_name', '')}\n"
            f"💰 {request_data.get('budget', '')}"
        ),
    )


async def _handle_phase1_accept(update, context, offer_id: str) -> None:
    query = update.callback_query
    broker_tg_id = int(query.from_user.id)

    try:
        profile = await _legacy.phase1.get_profile_by_telegram_user_id(
            broker_tg_id
        )
        if profile.get("role") not in {"broker", "lead_broker"}:
            raise _legacy.JaccPhase1Error("PROFILE_IS_NOT_A_BROKER")

        offer_context = await _get_offer_context(offer_id)
        offer = offer_context["offer"]
        request = offer_context["request"]
        customer = offer_context["customer"]
        broker_profile = offer_context["broker"]

        if str(offer["broker_id"]) != str(profile["id"]):
            raise _legacy.JaccPhase1Error("OFFER_NOT_OWNED_BY_BROKER")

        await _legacy.phase1.accept_offer(
            offer_id=offer_id,
            broker_id=str(profile["id"]),
        )
    except _legacy.JaccPhase1Error as exc:
        await query.answer(_friendly_phase1_error(exc), show_alert=True)
        return
    except Exception:
        _legacy.logger.exception("Phase 1 accept callback failed")
        await query.answer("Accept မအောင်မြင်ပါ", show_alert=True)
        return

    request_code = str(request["request_code"])
    customer_tg_id = customer.get("telegram_user_id")
    request_data = dict(request.get("form_data") or {})
    legacy_brokers = await _legacy.get_brokers()
    legacy_broker = next(
        (
            b
            for b in legacy_brokers
            if str(b.get("telegramId", "")) == str(broker_tg_id)
        ),
        {
            "brokerId": broker_profile.get("broker_code", "B???"),
            "username": query.from_user.username or "",
            "rating": 0,
            "deals": 0,
        },
    )

    service_status = (
        "HAS_AUCTION"
        if request.get("service_type") == "auction"
        else "HAS_SEARCH"
    )
    await _legacy.update_broker(str(broker_tg_id), status=service_status)

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(
                _legacy.SHEET_WEBHOOK,
                json={
                    "action": "updateRequest",
                    "reqId": request_code,
                    "status": "MATCHED",
                    "brokerId": legacy_broker.get("brokerId"),
                },
                timeout=10,
            )
    except Exception:
        _legacy.logger.exception(
            "Phase 1 accept Google Sheet backup update failed"
        )

    _legacy.proxy_sessions[request_code] = {
        "customerId": customer_tg_id,
        "customerUsername": request_data.get("username", ""),
        "brokerId": str(broker_tg_id),
        "brokerObj": legacy_broker,
        "reqId": request_code,
        "status": "ACTIVE",
        "startTime": _legacy.datetime.now().isoformat(),
        "phase1RequestId": str(request["id"]),
        "phase1OfferId": offer_id,
    }

    await query.answer("Request လက်ခံပြီးပါပြီ")
    await query.edit_message_text(
        (
            "✅ *Request လက်ခံပြီ!*\n\n"
            f"🆔 `{request_code}`\n"
            f"🚗 {request_data.get('car_name', '')}\n"
            f"💰 {request_data.get('budget', '')}\n\n"
            "💬 Customer ကို message ပို့နိုင်ပြီ"
        ),
        parse_mode="Markdown",
    )

    if customer_tg_id:
        await context.bot.send_message(
            chat_id=int(customer_tg_id),
            text=(
                "🎉 *Broker ရှာပေးနေပြီ!*\n\n"
                f"🆔 Request: `{request_code}`\n"
                f"👷 Broker #{legacy_broker.get('brokerId', broker_profile.get('broker_code'))} "
                "က သင့် Request လက်ခံပြီ\n\n"
                "ကားရှာပေးနေပါတယ် ⏳"
            ),
            parse_mode="Markdown",
        )

    await _legacy.notify_admins(
        context,
        (
            "🤝 *Phase 1 Broker Accept*\n\n"
            f"🆔 `{request_code}`\n"
            f"👷 `{broker_profile.get('broker_code')}`\n"
            f"👤 Customer: @{request_data.get('username', '')}"
        ),
    )


async def _handle_phase1_decline(update, context, offer_id: str) -> None:
    query = update.callback_query
    broker_tg_id = int(query.from_user.id)

    try:
        profile = await _legacy.phase1.get_profile_by_telegram_user_id(
            broker_tg_id
        )
        if profile.get("role") not in {"broker", "lead_broker"}:
            raise _legacy.JaccPhase1Error("PROFILE_IS_NOT_A_BROKER")

        offer_context = await _get_offer_context(offer_id)
        offer = offer_context["offer"]
        request = offer_context["request"]
        if str(offer["broker_id"]) != str(profile["id"]):
            raise _legacy.JaccPhase1Error("OFFER_NOT_OWNED_BY_BROKER")

        request_id = await _legacy.phase1.decline_offer(
            offer_id=offer_id,
            broker_id=str(profile["id"]),
            reason="BROKER_DECLINED_IN_TELEGRAM",
        )
        next_offer = await _legacy.phase1.dispatch_next_offer(request_id)
    except _legacy.JaccPhase1Error as exc:
        await query.answer(_friendly_phase1_error(exc), show_alert=True)
        return
    except Exception:
        _legacy.logger.exception("Phase 1 decline callback failed")
        await query.answer("Decline မအောင်မြင်ပါ", show_alert=True)
        return

    await query.answer("Request ငြင်းပယ်ပြီးပါပြီ")
    await query.edit_message_text(
        (
            "❌ *Request ငြင်းပယ်ပြီ*\n\n"
            f"🆔 `{request['request_code']}`\n\n"
            "နောက် Broker ဆီ ဆက်ပို့နေပါတယ်။"
        ),
        parse_mode="Markdown",
    )

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(
                _legacy.SHEET_WEBHOOK,
                json={
                    "action": "incrementDecline",
                    "telegramId": str(broker_tg_id),
                },
                timeout=10,
            )
    except Exception:
        _legacy.logger.exception(
            "Phase 1 decline Google Sheet backup update failed"
        )

    if next_offer is not None:
        await _send_phase1_offer(
            context,
            next_offer,
            dict(request.get("form_data") or {}),
        )
        _legacy.logger.info(
            "Phase 1 next offer sent after decline: request=%s broker=%s",
            next_offer.request_code,
            next_offer.broker_code,
        )
    else:
        customer_tg_id = offer_context["customer"].get("telegram_user_id")
        if customer_tg_id:
            await context.bot.send_message(
                chat_id=int(customer_tg_id),
                text=(
                    f"⏳ Request `{request['request_code']}` အတွက် "
                    "နောက် Available Broker ကို စောင့်နေပါတယ်။"
                ),
                parse_mode="Markdown",
            )


async def button_callback(update, context):
    query = update.callback_query
    data = query.data or ""

    if data.startswith("p1_accept_"):
        if _legacy.phase1 is None:
            await query.answer("Phase 1 မချိတ်ရသေးပါ", show_alert=True)
            return
        await _handle_phase1_accept(
            update,
            context,
            data.replace("p1_accept_", "", 1),
        )
        return

    if data.startswith("p1_decline_"):
        if _legacy.phase1 is None:
            await query.answer("Phase 1 မချိတ်ရသေးပါ", show_alert=True)
            return
        await _handle_phase1_decline(
            update,
            context,
            data.replace("p1_decline_", "", 1),
        )
        return

    await _original_button_callback(update, context)


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


# Functions defined in legacy_bot resolve these globals at runtime, so replacing
# them here integrates Phase 1 without rewriting the large production file.
_legacy.submit_request = submit_request
_legacy.button_callback = button_callback
_legacy.available_cmd = available_cmd
_legacy.busy_cmd = busy_cmd

# Python's automatic sitecustomize loading is not guaranteed in every Railway
# launch layout. Import it explicitly before legacy_bot.main registers handlers.
import sitecustomize as _phase1_runtime_patches  # noqa: F401,E402


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
