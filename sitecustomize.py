"""Runtime bridges for the JACC Phase 1 rollout.

Python imports ``sitecustomize`` automatically at startup. The bridges patch the
active ``legacy_bot`` runtime used by Railway, while preserving the existing
Google Sheets commands as safe fallbacks.
"""

from __future__ import annotations

import os
from typing import Any

import legacy_bot as _legacy
from telegram.ext import ExtBot


_original_mystatus_cmd = _legacy.mystatus_cmd
_original_brokers_cmd = _legacy.brokers_cmd
_original_command_handler = _legacy.CommandHandler
_original_set_my_commands = ExtBot.set_my_commands

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


async def _get_latest_phase1_request(
    telegram_user_id: int,
) -> dict[str, Any] | None:
    if _legacy.phase1 is None:
        return None

    profile = await _legacy.phase1.get_profile_by_telegram_user_id(
        telegram_user_id
    )
    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "customer_id": f"eq.{profile['id']}",
        "select": (
            "id,request_code,service_type,status,form_data,"
            "assigned_broker_id,created_at,updated_at"
        ),
        "order": "created_at.desc",
        "limit": "1",
    }

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
            f"Phase 1 status lookup failed ({response.status_code}): "
            f"{response.text[:500]}"
        )

    rows = response.json()
    return rows[0] if rows else None


async def _get_phase1_broker_code(broker_id: str | None) -> str | None:
    if not broker_id or _legacy.phase1 is None:
        return None

    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_broker_profiles"
    params = {
        "user_id": f"eq.{broker_id}",
        "select": "broker_code",
        "limit": "1",
    }
    async with _legacy.httpx.AsyncClient(
        timeout=_legacy.phase1._timeout
    ) as client:
        response = await client.get(
            url,
            headers=_legacy.phase1._headers,
            params=params,
        )

    if response.is_error:
        return None
    rows = response.json()
    return str(rows[0]["broker_code"]) if rows else None


async def mystatus_cmd(update, context):
    """Show the latest Supabase request when Phase 1 is active."""
    if os.environ.get("PHASE1_SEQUENTIAL_ENABLED", "0").strip() != "1":
        await _original_mystatus_cmd(update, context)
        return

    user_id = int(update.effective_user.id)

    if user_id in _legacy.pending_request:
        await _original_mystatus_cmd(update, context)
        return

    if not await _legacy.is_active_member(user_id):
        await update.message.reply_text("🔒 Member များသာ သုံးနိုင်ပါသည်")
        return

    try:
        request = await _get_latest_phase1_request(user_id)
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning(
            "Phase 1 /mystatus fallback for user=%s: %s",
            user_id,
            exc,
        )
        await _original_mystatus_cmd(update, context)
        return
    except Exception:
        _legacy.logger.exception(
            "Phase 1 /mystatus failed for user=%s",
            user_id,
        )
        await _original_mystatus_cmd(update, context)
        return

    if not request:
        await _original_mystatus_cmd(update, context)
        return

    request_data = dict(request.get("form_data") or {})
    status = str(request.get("status") or "submitted")
    status_label = _STATUS_LABELS.get(status, f"📊 {status}")
    service_label = (
        "🏆 Auction Car"
        if request.get("service_type") == "auction"
        else "🔍 Outside Car"
    )
    broker_code = await _get_phase1_broker_code(
        request.get("assigned_broker_id")
    )

    lines = [
        "📋 Request Status",
        "",
        f"🆔 {request.get('request_code', '-')}",
        f"📌 {service_label}",
        f"🚘 {request_data.get('car_name', '-')}",
        f"📊 {status_label}",
    ]
    if broker_code:
        lines.append(f"👷 Broker: #{broker_code}")

    await update.message.reply_text("\n".join(lines))


async def _load_phase1_queue(limit: int = 20) -> list[dict[str, Any]]:
    """Load waiting and offered requests for the admin queue view."""
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "status": "in.(waiting_broker,offered)",
        "select": (
            "request_code,status,service_type,priority,created_at,form_data"
        ),
        "order": "priority.desc,created_at.asc",
        "limit": str(limit),
    }
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
            "Phase 1 queue lookup failed "
            f"({response.status_code}): {response.text[:500]}"
        )
    return list(response.json() or [])


def _queue_text(rows: list[dict[str, Any]]) -> str:
    waiting_count = sum(
        1 for row in rows if row.get("status") == "waiting_broker"
    )
    offered_count = sum(
        1 for row in rows if row.get("status") == "offered"
    )
    lines = [
        "📋 JACC REQUEST QUEUE",
        "",
        f"⏳ Waiting: {waiting_count}",
        f"📨 Offer sent: {offered_count}",
        f"📊 Showing: {len(rows)}",
        "",
    ]

    for index, row in enumerate(rows, start=1):
        form_data = dict(row.get("form_data") or {})
        service = (
            "AUCTION"
            if row.get("service_type") == "auction"
            else "OUTSIDE"
        )
        status = (
            "WAITING"
            if row.get("status") == "waiting_broker"
            else "OFFER SENT"
        )
        car_name = str(form_data.get("car_name") or "-")[:60]
        username = str(form_data.get("username") or "-")[:40]
        priority = row.get("priority", 0)
        created_at = str(row.get("created_at") or "").replace("T", " ")[:16]
        lines.extend(
            [
                (
                    f"{index}. {row.get('request_code', '-')} | "
                    f"{service} | {status} | P{priority}"
                ),
                f"   🚗 {car_name}",
                f"   👤 {username} | 🕒 {created_at}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


async def brokers_cmd(update, context):
    """Serve /queue and preserve the existing /brokers command."""
    message = update.effective_message
    command = (
        (message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )

    if command != "/queue":
        await _original_brokers_cmd(update, context)
        return

    user = update.effective_user
    if not _legacy.ADMIN_IDS or user.id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    try:
        rows = await _load_phase1_queue()
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning("Phase 1 /queue unavailable: %s", exc)
        await message.reply_text("❌ Queue data မရသေးပါ — ခဏပြန်စမ်းပါ")
        return
    except Exception:
        _legacy.logger.exception("Phase 1 /queue failed")
        await message.reply_text("❌ Queue စစ်ဆေးမှု မအောင်မြင်ပါ")
        return

    if not rows:
        await message.reply_text("✅ Queue ထဲမှာ စောင့်နေတဲ့ Request မရှိပါ")
        return

    await message.reply_text(_queue_text(rows))


def _command_handler_with_queue(command, callback, *args, **kwargs):
    """Register /queue through the existing /brokers handler slot."""
    if command == "brokers":
        command = ["brokers", "queue"]
    return _original_command_handler(command, callback, *args, **kwargs)


async def _set_my_commands_with_admin_queue(self, commands, *args, **kwargs):
    """Add /queue to Telegram's visible command menu for admin chat scopes."""
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched_commands = list(commands)
    if is_admin_scope and not any(
        getattr(command, "command", "") == "queue"
        for command in patched_commands
    ):
        patched_commands.append(
            _legacy.BotCommand(
                "queue",
                "📋 Waiting Request Queue (Admin)",
            )
        )

    return await _original_set_my_commands(
        self,
        patched_commands,
        *args,
        **kwargs,
    )


_legacy.mystatus_cmd = mystatus_cmd
_legacy.brokers_cmd = brokers_cmd
_legacy.CommandHandler = _command_handler_with_queue
ExtBot.set_my_commands = _set_my_commands_with_admin_queue
