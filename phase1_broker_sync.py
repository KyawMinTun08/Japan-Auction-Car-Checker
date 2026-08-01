"""Keep legacy Telegram broker status synchronized with JACC Phase 1.

Legacy /addbroker, /available and /busy originally updated only Google Sheets.
Phase 1 dispatch reads Supabase, so a broker could appear FREE in Telegram while
remaining unavailable (or missing) in the central assignment database.
"""

from __future__ import annotations

from typing import Any

import legacy_bot as _legacy


_original_addbroker_cmd = _legacy.addbroker_cmd


class BrokerSyncError(RuntimeError):
    pass


def _phase1_client():
    client = _legacy.phase1
    if client is None:
        raise BrokerSyncError("PHASE1_NOT_CONFIGURED")
    return client


async def _rest(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str | None = None,
) -> Any:
    client = _phase1_client()
    headers = dict(client._headers)
    if prefer:
        headers["Prefer"] = prefer

    url = f"{client._base_url}/rest/v1/{table}"
    async with _legacy.httpx.AsyncClient(timeout=client._timeout) as session:
        response = await session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=payload,
        )

    if response.is_error:
        raise BrokerSyncError(
            f"{method} {table} failed ({response.status_code}): "
            f"{response.text[:700]}"
        )
    if not response.content:
        return None
    return response.json()


async def _get_legacy_broker(telegram_user_id: int | str) -> dict[str, Any] | None:
    wanted = str(telegram_user_id).strip()
    brokers = await _legacy.get_brokers()
    return next(
        (
            broker
            for broker in brokers
            if str(broker.get("telegramId", "")).strip() == wanted
        ),
        None,
    )


def _clean_username(value: Any, telegram_user_id: int) -> str:
    username = str(value or "").strip().lstrip("@")
    return username or f"Broker {telegram_user_id}"


def _clean_broker_code(value: Any, telegram_user_id: int) -> str:
    code = str(value or "").strip().lstrip("#").upper()
    return code or f"B{str(telegram_user_id)[-5:]}"


async def _ensure_phase1_broker(
    *,
    telegram_user_id: int,
    username: str,
    broker_code: str,
    accepting_requests: bool,
) -> dict[str, Any]:
    profile_rows = await _rest(
        "GET",
        "jacc_profiles",
        params={
            "telegram_user_id": f"eq.{telegram_user_id}",
            "select": "id,role,display_name,telegram_user_id,account_active",
            "limit": "1",
        },
    ) or []

    display_name = _clean_username(username, telegram_user_id)
    if profile_rows:
        profile = dict(profile_rows[0])
        role = str(profile.get("role") or "customer")
        profile_values: dict[str, Any] = {
            "display_name": display_name,
            "account_active": True,
        }
        if role not in {"broker", "lead_broker", "admin"}:
            profile_values["role"] = "broker"
        updated = await _rest(
            "PATCH",
            "jacc_profiles",
            params={"id": f"eq.{profile['id']}"},
            payload=profile_values,
            prefer="return=representation",
        ) or []
        if updated:
            profile = dict(updated[0])
    else:
        created = await _rest(
            "POST",
            "jacc_profiles",
            payload={
                "role": "broker",
                "display_name": display_name,
                "telegram_user_id": telegram_user_id,
                "account_active": True,
            },
            prefer="return=representation",
        ) or []
        if not created:
            raise BrokerSyncError("BROKER_PROFILE_CREATE_RETURNED_NO_ROW")
        profile = dict(created[0])

    user_id = str(profile["id"])
    broker_rows = await _rest(
        "GET",
        "jacc_broker_profiles",
        params={
            "user_id": f"eq.{user_id}",
            "select": (
                "user_id,broker_code,account_status,accepting_requests,"
                "can_auction,can_outside_car"
            ),
            "limit": "1",
        },
    ) or []

    clean_code = _clean_broker_code(broker_code, telegram_user_id)
    if not broker_rows:
        created_broker = await _rest(
            "POST",
            "jacc_broker_profiles",
            payload={
                "user_id": user_id,
                "broker_code": clean_code,
                "account_status": "probation",
                "accepting_requests": accepting_requests,
                "can_auction": True,
                "can_outside_car": True,
            },
            prefer="return=representation",
        ) or []
        if not created_broker:
            raise BrokerSyncError("JACC_BROKER_CREATE_RETURNED_NO_ROW")
        broker = dict(created_broker[0])
    else:
        broker = dict(broker_rows[0])
        status = str(broker.get("account_status") or "pending_review")
        if accepting_requests and status in {
            "temporarily_suspended",
            "banned",
            "resigned",
        }:
            raise BrokerSyncError(f"BROKER_ACCOUNT_NOT_AVAILABLE:{status}")

        values: dict[str, Any] = {
            "accepting_requests": accepting_requests,
            "can_auction": True,
            "can_outside_car": True,
        }
        if status in {"pending_review", "offline"}:
            values["account_status"] = "probation"

        updated_broker = await _rest(
            "PATCH",
            "jacc_broker_profiles",
            params={"user_id": f"eq.{user_id}"},
            payload=values,
            prefer="return=representation",
        ) or []
        if updated_broker:
            broker = dict(updated_broker[0])

    return {
        "profile_id": user_id,
        "broker_code": str(broker.get("broker_code") or clean_code),
        "account_status": str(broker.get("account_status") or "probation"),
        "accepting_requests": bool(broker.get("accepting_requests")),
    }


async def available_cmd(update, context):
    message = update.effective_message
    telegram_user_id = int(update.effective_user.id)
    legacy_broker = await _get_legacy_broker(telegram_user_id)
    if not legacy_broker:
        await message.reply_text("❌ Broker မဟုတ်ဘူး")
        return

    updated = await _legacy.update_broker(str(telegram_user_id), status="FREE")
    if not updated:
        await message.reply_text("❌ Broker status update မအောင်မြင်ပါ")
        return

    try:
        synced = await _ensure_phase1_broker(
            telegram_user_id=telegram_user_id,
            username=str(legacy_broker.get("username") or ""),
            broker_code=str(legacy_broker.get("brokerId") or ""),
            accepting_requests=True,
        )
    except Exception as exc:
        _legacy.logger.exception("Phase 1 broker /available sync failed")
        await message.reply_text(
            "⚠️ Google Sheet မှာ Available ဖြစ်ပေမယ့် Phase 1 sync မအောင်မြင်ပါ။\n"
            f"Error: {str(exc)[:500]}"
        )
        return

    await message.reply_text(
        "🟢 *Available ဖြစ်ပြီ*\n\n"
        f"🆔 `#{synced['broker_code']}`\n"
        "✅ Google Sheet: FREE\n"
        "✅ Phase 1: Available\n\n"
        "⏱ Waiting Request ရှိရင် 30–60 စက္ကန့်အတွင်း Offer ရနိုင်ပါတယ်။",
        parse_mode="Markdown",
    )


async def busy_cmd(update, context):
    message = update.effective_message
    telegram_user_id = int(update.effective_user.id)
    legacy_broker = await _get_legacy_broker(telegram_user_id)
    if not legacy_broker:
        await message.reply_text("❌ Broker မဟုတ်ဘူး")
        return

    updated = await _legacy.update_broker(str(telegram_user_id), status="BUSY")
    if not updated:
        await message.reply_text("❌ Broker status update မအောင်မြင်ပါ")
        return

    try:
        synced = await _ensure_phase1_broker(
            telegram_user_id=telegram_user_id,
            username=str(legacy_broker.get("username") or ""),
            broker_code=str(legacy_broker.get("brokerId") or ""),
            accepting_requests=False,
        )
    except Exception as exc:
        _legacy.logger.exception("Phase 1 broker /busy sync failed")
        await message.reply_text(
            "⚠️ Google Sheet မှာ BUSY ဖြစ်ပေမယ့် Phase 1 sync မအောင်မြင်ပါ။\n"
            f"Error: {str(exc)[:500]}"
        )
        return

    await message.reply_text(
        "🔴 *BUSY ဖြစ်ပြီ*\n\n"
        f"🆔 `#{synced['broker_code']}`\n"
        "✅ Google Sheet: BUSY\n"
        "✅ Phase 1: Not accepting requests",
        parse_mode="Markdown",
    )


async def addbroker_cmd(update, context):
    # Keep the established Google Sheet add/DM flow first.
    await _original_addbroker_cmd(update, context)

    if len(context.args) < 2:
        return
    username = str(context.args[0] or "").strip().lstrip("@")
    telegram_id_text = str(context.args[1] or "").strip()
    if not telegram_id_text.isdigit():
        return

    telegram_user_id = int(telegram_id_text)
    legacy_broker = await _get_legacy_broker(telegram_user_id)
    if not legacy_broker:
        return

    try:
        synced = await _ensure_phase1_broker(
            telegram_user_id=telegram_user_id,
            username=str(legacy_broker.get("username") or username),
            broker_code=str(legacy_broker.get("brokerId") or ""),
            accepting_requests=False,
        )
        await update.effective_message.reply_text(
            "✅ Phase 1 Broker profile sync ပြီးပါပြီ။\n"
            f"🆔 #{synced['broker_code']}\n"
            "Broker က /available ပို့ပြီးမှ Offer လက်ခံပါမယ်။"
        )
    except Exception as exc:
        _legacy.logger.exception("New broker Phase 1 sync failed")
        await update.effective_message.reply_text(
            "⚠️ Google Sheet Broker ထည့်ပြီးပေမယ့် Phase 1 sync မအောင်မြင်ပါ။\n"
            f"Error: {str(exc)[:500]}"
        )


# legacy_bot.main resolves these names when Telegram handlers are registered.
_legacy.addbroker_cmd = addbroker_cmd
_legacy.available_cmd = available_cmd
_legacy.busy_cmd = busy_cmd
