"""Direct runtime bridges for the JACC Railway bot.

This module is imported before ``legacy_bot.main`` registers handlers. Keep all
critical command patches in this single module so Railway does not depend on
``usercustomize`` auto-loading.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any

import legacy_bot as _legacy
from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import ExtBot


# ---------------------------------------------------------------------------
# ONE CANONICAL REQUEST ID
# ---------------------------------------------------------------------------
# During mirror rollout, Phase 1 creates the canonical request code first and
# the legacy submit function used to generate a second random R/A code. Capture
# the Phase 1 code in the current async context and make the legacy generator
# reuse it. ContextVar keeps concurrent customer requests isolated.
if not getattr(_legacy, "_canonical_request_id_patch_installed", False):
    _CANONICAL_REQUEST_CODE: ContextVar[str] = ContextVar(
        "jacc_canonical_request_code",
        default="",
    )
    _ORIGINAL_RANDOM_CHOICES = _legacy.random.choices

    def _canonical_aware_choices(
        population,
        weights=None,
        *,
        cum_weights=None,
        k=1,
    ):
        request_code = _CANONICAL_REQUEST_CODE.get()
        if (
            request_code
            and population == _legacy.string.digits
            and k == 6
            and request_code[:1] in {"R", "A"}
        ):
            # legacy_bot builds: service_prefix + ''.join(random.choices(...))
            # Returning the rest of the canonical code preserves the full code.
            _CANONICAL_REQUEST_CODE.set("")
            return [request_code[1:]]
        return _ORIGINAL_RANDOM_CHOICES(
            population,
            weights=weights,
            cum_weights=cum_weights,
            k=k,
        )

    _legacy.random.choices = _canonical_aware_choices

    if _legacy.phase1 is not None:
        _ORIGINAL_CREATE_REQUEST = (
            _legacy.phase1.create_request_for_telegram_customer
        )

        async def _create_request_and_capture_code(*args, **kwargs):
            result = await _ORIGINAL_CREATE_REQUEST(*args, **kwargs)
            request_code = str(result.get("request_code") or "").strip().upper()
            if request_code:
                _CANONICAL_REQUEST_CODE.set(request_code)
            return result

        _legacy.phase1.create_request_for_telegram_customer = (
            _create_request_and_capture_code
        )

    _legacy._canonical_request_id_patch_installed = True


_BASE_COMMAND_HANDLER = _legacy.CommandHandler
_BASE_SET_MY_COMMANDS = ExtBot.set_my_commands
_ORIGINAL_START = _legacy.start
_ORIGINAL_MYSTATUS = _legacy.mystatus_cmd
_ORIGINAL_BROKERS = _legacy.brokers_cmd

_STATUS_LABELS = {
    "submitted": "📥 Request တင်ပြီး",
    "waiting_broker": "⏳ Available Broker စောင့်နေ",
    "offered": "📨 Broker ဆီ Offer ပို့ထား",
    "assigned": "🤝 Broker လက်ခံပြီး",
    "consulting": "💬 ဆွေးနွေးနေ",
    "searching": "🔎 ကားရှာဖွေနေ",
    "car_found": "🚗 ကားတွေ့ပြီ",
    "waiting_customer": "👤 Customer အဖြေစောင့်နေ",
    "waiting_payment": "💳 ငွေပေးချေမှုစောင့်နေ",
    "payment_verifying": "🔍 ငွေပေးချေမှုစစ်ဆေးနေ",
    "payment_confirmed": "✅ ငွေပေးချေမှုအတည်ပြုပြီး",
    "price_approval": "💰 ဈေးနှုန်းအတည်ပြုချက်စောင့်နေ",
    "auction_pending": "🏆 လေလံစောင့်နေ",
    "won": "🎉 လေလံအောင်မြင်",
    "lost": "❌ လေလံမအောင်မြင်",
    "negotiating": "🤝 ဈေးနှုန်းညှိနှိုင်းနေ",
    "inspection_pending": "🔧 စစ်ဆေးမှုစောင့်နေ",
    "reserved": "📌 ကား Reserve လုပ်ထား",
    "purchased": "🛒 ဝယ်ယူပြီး",
    "paused": "⏸ ယာယီရပ်ထား",
    "completed": "✅ ပြီးဆုံးပြီ",
    "cancelled": "❌ Cancel ဖြစ်ပြီ",
    "closed_inactive": "🔒 ပိတ်ထားပြီ",
    "disputed": "⚠️ ပြဿနာစစ်ဆေးနေ",
    "reassigned": "🔄 Broker အသစ်ပြောင်းနေ",
}


async def admin_cmd(update, context):
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
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command in {"/admin", "/myadmin"}:
        await admin_cmd(update, context)
        return
    await _ORIGINAL_START(update, context)


async def mypassword_cmd(update, context):
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
                json={"action": "getPassword", "userId": str(user_id), "serverKey": _legacy.SHEET_SERVER_KEY},
                timeout=40,
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
        _legacy.logger.exception("Direct /mypassword patch failed")
        await message.reply_text("❌ Error — Admin ကို ဆက်သွယ်ပါ")


async def _latest_phase1_request(telegram_user_id: int) -> dict[str, Any] | None:
    if _legacy.phase1 is None:
        return None
    profile = await _legacy.phase1.get_profile_by_telegram_user_id(telegram_user_id)
    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "customer_id": f"eq.{profile['id']}",
        "select": "id,request_code,service_type,status,form_data,assigned_broker_id,created_at,updated_at",
        "order": "created_at.desc",
        "limit": "1",
    }
    async with _legacy.httpx.AsyncClient(timeout=_legacy.phase1._timeout) as client:
        response = await client.get(url, headers=_legacy.phase1._headers, params=params)
    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Phase 1 status lookup failed ({response.status_code}): {response.text[:500]}"
        )
    rows = response.json()
    return rows[0] if rows else None


async def _phase1_broker_code(broker_id: str | None) -> str | None:
    if not broker_id or _legacy.phase1 is None:
        return None
    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_broker_profiles"
    params = {"user_id": f"eq.{broker_id}", "select": "broker_code", "limit": "1"}
    async with _legacy.httpx.AsyncClient(timeout=_legacy.phase1._timeout) as client:
        response = await client.get(url, headers=_legacy.phase1._headers, params=params)
    if response.is_error:
        return None
    rows = response.json()
    return str(rows[0]["broker_code"]) if rows else None


async def mystatus_cmd(update, context):
    if os.environ.get("PHASE1_SEQUENTIAL_ENABLED", "0").strip() != "1":
        await _ORIGINAL_MYSTATUS(update, context)
        return

    user_id = int(update.effective_user.id)
    if user_id in _legacy.pending_request:
        await _ORIGINAL_MYSTATUS(update, context)
        return
    if not await _legacy.is_active_member(user_id):
        await update.effective_message.reply_text("🔒 Member များသာ သုံးနိုင်ပါသည်")
        return

    try:
        request = await _latest_phase1_request(user_id)
    except Exception:
        _legacy.logger.exception("Phase 1 /mystatus fallback")
        await _ORIGINAL_MYSTATUS(update, context)
        return
    if not request:
        await _ORIGINAL_MYSTATUS(update, context)
        return

    form_data = dict(request.get("form_data") or {})
    status = str(request.get("status") or "submitted")
    service = "🏆 Auction Car" if request.get("service_type") == "auction" else "🔍 Outside Car"
    lines = [
        "📋 Request Status",
        "",
        f"🆔 {request.get('request_code', '-')}",
        f"📌 {service}",
        f"🚘 {form_data.get('car_name', '-')}",
        f"📊 {_STATUS_LABELS.get(status, status)}",
    ]
    broker_code = await _phase1_broker_code(request.get("assigned_broker_id"))
    if broker_code:
        lines.append(f"👷 Broker: #{broker_code}")
    await update.effective_message.reply_text("\n".join(lines))


async def _load_queue(limit: int = 20) -> list[dict[str, Any]]:
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")
    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "status": "in.(waiting_broker,offered)",
        "select": "request_code,status,service_type,priority,created_at,form_data",
        "order": "priority.desc,created_at.asc",
        "limit": str(limit),
    }
    async with _legacy.httpx.AsyncClient(timeout=_legacy.phase1._timeout) as client:
        response = await client.get(url, headers=_legacy.phase1._headers, params=params)
    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Phase 1 queue lookup failed ({response.status_code}): {response.text[:500]}"
        )
    return list(response.json() or [])


def _queue_text(rows: list[dict[str, Any]]) -> str:
    lines = ["📋 JACC REQUEST QUEUE", ""]
    for index, row in enumerate(rows, start=1):
        form_data = dict(row.get("form_data") or {})
        service = "AUCTION" if row.get("service_type") == "auction" else "OUTSIDE"
        status = "WAITING" if row.get("status") == "waiting_broker" else "OFFER SENT"
        lines.extend([
            f"{index}. {row.get('request_code', '-')} | {service} | {status} | P{row.get('priority', 0)}",
            f"   🚗 {str(form_data.get('car_name') or '-')[:60]}",
            f"   👤 {str(form_data.get('username') or '-')[:40]}",
            "",
        ])
    return "\n".join(lines).rstrip()


async def brokers_cmd(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command != "/queue":
        await _ORIGINAL_BROKERS(update, context)
        return
    if not _legacy.ADMIN_IDS or int(update.effective_user.id) not in _legacy.ADMIN_IDS:
        await update.effective_message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return
    try:
        rows = await _load_queue()
    except Exception:
        _legacy.logger.exception("Phase 1 /queue failed")
        await update.effective_message.reply_text("❌ Queue စစ်ဆေးမှု မအောင်မြင်ပါ")
        return
    if not rows:
        await update.effective_message.reply_text("✅ Queue ထဲမှာ စောင့်နေတဲ့ Request မရှိပါ")
        return
    await update.effective_message.reply_text(_queue_text(rows))


def command_handler(command, callback, *args, **kwargs):
    if command == "start":
        return _BASE_COMMAND_HANDLER(
            ["start", "admin", "myadmin"], start_router, *args, **kwargs
        )
    if command == "mypassword":
        callback = mypassword_cmd
    if command == "brokers":
        command = ["brokers", "queue"]
        callback = brokers_cmd
    return _BASE_COMMAND_HANDLER(command, callback, *args, **kwargs)


async def set_my_commands(self, commands, scope=None, language_code=None, *args, **kwargs):
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
                command_list.append(BotCommand("queue", "📋 Request Queue ကြည့်ရန် (Admin)"))
    return await _BASE_SET_MY_COMMANDS(
        self,
        command_list,
        scope=scope,
        language_code=language_code,
        *args,
        **kwargs,
    )


_legacy.CommandHandler = command_handler
_legacy.mypassword_cmd = mypassword_cmd
_legacy.mystatus_cmd = mystatus_cmd
_legacy.brokers_cmd = brokers_cmd
ExtBot.set_my_commands = set_my_commands
