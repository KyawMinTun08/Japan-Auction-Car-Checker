"""Runtime bridge for customer request status during the JACC Phase 1 rollout.

Python imports ``sitecustomize`` automatically at startup.  The bridge patches
only ``legacy_bot.mystatus_cmd`` and keeps the existing Google Sheets command as
a safe fallback while Phase 1 sequential assignment is disabled or unavailable.
"""

from __future__ import annotations

import os
from typing import Any

import legacy_bot as _legacy


_original_mystatus_cmd = _legacy.mystatus_cmd

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


_legacy.mystatus_cmd = mystatus_cmd
