"""JACC production launcher with Phase 1 admin broker controls.

Adds admin-only broker availability aliases and keeps customer cancellation
state consistent between the legacy Google Sheet flow and Supabase Phase 1.
"""

from __future__ import annotations

import asyncio
import traceback

import bot as _bot


_legacy = _bot._legacy
_telegram_command_handler = _legacy.CommandHandler
_original_brokers_cmd = _legacy.brokers_cmd
_original_cancelrequest_cmd = _legacy.cancelrequest_cmd


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


async def _phase1_latest_open_request(telegram_user_id: int) -> dict | None:
    """Return the customer's latest non-terminal Phase 1 request."""
    if _legacy.phase1 is None:
        return None

    profile = await _legacy.phase1.get_profile_by_telegram_user_id(
        telegram_user_id
    )
    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "customer_id": f"eq.{profile['id']}",
        "status": "not.in.(completed,cancelled,closed_inactive)",
        "select": "id,request_code,status,assigned_broker_id",
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
            f"Phase 1 cancel lookup failed ({response.status_code}): "
            f"{response.text[:500]}"
        )

    rows = response.json()
    if not rows:
        return None
    request = rows[0]
    request["customer_id"] = str(profile["id"])
    return request


async def _phase1_patch(
    table: str,
    *,
    filters: dict[str, str],
    values: dict,
) -> None:
    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    headers = {
        **_legacy.phase1._headers,
        "Prefer": "return=minimal",
    }
    async with _legacy.httpx.AsyncClient(
        timeout=_legacy.phase1._timeout
    ) as client:
        response = await client.patch(
            url,
            headers=headers,
            params=filters,
            json=values,
        )

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Phase 1 cancel patch failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )


async def _sync_phase1_customer_cancel(telegram_user_id: int) -> None:
    """Close offers, assignment and request after a confirmed legacy cancel."""
    request = await _phase1_latest_open_request(telegram_user_id)
    if request is None:
        return

    request_id = str(request["id"])
    old_status = str(request.get("status") or "submitted")
    now_iso = _legacy.datetime.utcnow().isoformat() + "Z"

    await _phase1_patch(
        "jacc_request_offers",
        filters={
            "request_id": f"eq.{request_id}",
            "status": "eq.pending",
        },
        values={"status": "cancelled", "responded_at": now_iso},
    )
    await _phase1_patch(
        "jacc_request_assignments",
        filters={
            "request_id": f"eq.{request_id}",
            "status": "eq.active",
        },
        values={
            "status": "cancelled",
            "ended_at": now_iso,
            "ended_reason": "CUSTOMER_CANCELLED_IN_TELEGRAM",
        },
    )
    await _phase1_patch(
        "jacc_service_requests",
        filters={"id": f"eq.{request_id}"},
        values={
            "status": "cancelled",
            "assigned_broker_id": None,
        },
    )

    history_url = (
        f"{_legacy.phase1._base_url}/rest/v1/"
        "jacc_request_status_history"
    )
    history_headers = {
        **_legacy.phase1._headers,
        "Prefer": "return=minimal",
    }
    async with _legacy.httpx.AsyncClient(
        timeout=_legacy.phase1._timeout
    ) as client:
        history_response = await client.post(
            history_url,
            headers=history_headers,
            json={
                "request_id": request_id,
                "old_status": old_status,
                "new_status": "cancelled",
                "changed_by": request["customer_id"],
                "reason": "Customer cancelled through Telegram /cancelrequest",
            },
        )

    if history_response.is_error:
        raise _legacy.JaccPhase1Error(
            "Phase 1 cancel history insert failed "
            f"({history_response.status_code}): "
            f"{history_response.text[:500]}"
        )

    _legacy.logger.info(
        "Phase 1 customer cancellation synced: request=%s",
        request.get("request_code"),
    )


async def cancelrequest_cmd(update, context):
    """Run the existing cancel flow, then mirror confirmed cancellation."""
    user_id = int(update.effective_user.id)
    str_uid = str(user_id)
    session_data = next(
        (
            (sid, session)
            for sid, session in _legacy.proxy_sessions.items()
            if str(session.get("customerId", "")) == str_uid
            and session.get("status") == "ACTIVE"
        ),
        None,
    )

    await _original_cancelrequest_cmd(update, context)

    # Pending form cancellation or deposit-blocked cancellation must not touch
    # Supabase. A removed active session confirms the legacy cancel succeeded.
    if session_data is None:
        return
    session_id, session = session_data
    if session_id in _legacy.proxy_sessions:
        return

    try:
        await _sync_phase1_customer_cancel(user_id)
        broker_tg_id = str(session.get("brokerId", ""))
        if broker_tg_id.isdigit():
            await _bot._set_broker_availability(
                telegram_user_id=int(broker_tg_id),
                accepting_requests=True,
            )
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning(
            "Phase 1 customer cancel sync skipped: %s",
            exc,
        )
    except Exception:
        _legacy.logger.exception("Phase 1 customer cancel sync failed")


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

    # Sheet update above already succeeded; Supabase mirror is secondary.
    # A failure here must not swallow the admin's confirmation — the Sheet
    # (source of truth for the bot) is already correct — but the admin does
    # need to know the two systems have drifted apart.
    supabase_synced = True
    try:
        await _bot._set_broker_availability(
            telegram_user_id=int(telegram_id),
            accepting_requests=desired_free,
        )
    except Exception:
        supabase_synced = False
        _legacy.logger.exception(
            "Supabase broker availability sync failed for %s", telegram_id
        )

    emoji = "🟢" if desired_free else "🔴"
    label = "FREE / Available" if desired_free else "BUSY"
    broker_code = broker.get("brokerId", "B???")
    username = broker.get("username", "")

    await message.reply_text(
        f"{emoji} *Broker status ပြောင်းပြီးပါပြီ*\n\n"
        f"🆔 `#{broker_code}`\n"
        f"👤 @{username}\n"
        f"📌 Status: *{label}*"
        + ("" if supabase_synced else "\n\n⚠️ Supabase sync မအောင်မြင်ပါ — Sheet ကတော့ update ဖြစ်ပြီးပါပြီ"),
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
_legacy.cancelrequest_cmd = cancelrequest_cmd


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
