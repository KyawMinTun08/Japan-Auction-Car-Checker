"""JACC production launcher with Phase 1 completion synchronisation.

Extends ``admin_launcher`` so a confirmed Broker ``/endchat`` action marks
the matching Supabase request and assignment as completed.
"""

from __future__ import annotations

import asyncio
import traceback

import admin_launcher as _admin


_bot = _admin._bot
_legacy = _admin._legacy
_original_button_callback = _legacy.button_callback


async def _sync_phase1_completion(session: dict, broker_telegram_id: int) -> None:
    """Mark the Phase 1 request complete after legacy end-chat succeeds."""
    if _legacy.phase1 is None:
        return

    request_id = str(session.get("phase1RequestId", "")).strip()
    if not request_id:
        # Legacy-only sessions do not have a safe one-to-one Phase 1 mapping.
        return

    request = await _bot._phase1_get_single(
        "jacc_service_requests",
        filters={"id": f"eq.{request_id}"},
        select="id,request_code,status,assigned_broker_id",
    )
    old_status = str(request.get("status") or "assigned")
    if old_status == "completed":
        return

    now_iso = _legacy.datetime.utcnow().isoformat() + "Z"

    await _admin._phase1_patch(
        "jacc_request_offers",
        filters={
            "request_id": f"eq.{request_id}",
            "status": "eq.pending",
        },
        values={
            "status": "cancelled",
            "responded_at": now_iso,
        },
    )
    await _admin._phase1_patch(
        "jacc_request_assignments",
        filters={
            "request_id": f"eq.{request_id}",
            "status": "eq.active",
        },
        values={
            "status": "completed",
            "ended_at": now_iso,
            "ended_reason": "BROKER_ENDED_CHAT_IN_TELEGRAM",
        },
    )
    await _admin._phase1_patch(
        "jacc_service_requests",
        filters={"id": f"eq.{request_id}"},
        values={
            "status": "completed",
            "completed_at": now_iso,
            "last_meaningful_update_at": now_iso,
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
                "new_status": "completed",
                "changed_by": request.get("assigned_broker_id"),
                "reason": "Broker completed session through Telegram /endchat",
            },
        )

    if history_response.is_error:
        raise _legacy.JaccPhase1Error(
            "Phase 1 completion history insert failed "
            f"({history_response.status_code}): "
            f"{history_response.text[:500]}"
        )

    await _bot._set_broker_availability(
        telegram_user_id=broker_telegram_id,
        accepting_requests=True,
    )
    _legacy.logger.info(
        "Phase 1 request completion synced: request=%s",
        request.get("request_code"),
    )


async def button_callback(update, context):
    """Run the existing callback, then sync confirmed end-chat completion."""
    query = update.callback_query
    data = query.data or ""

    if not data.startswith("endchat_yes_"):
        await _original_button_callback(update, context)
        return

    request_code = data.replace("endchat_yes_", "", 1)
    broker_telegram_id = int(query.from_user.id)
    session = dict(_legacy.proxy_sessions.get(request_code) or {})

    try:
        await _original_button_callback(update, context)
    finally:
        # The legacy callback removes the session only when completion succeeds.
        if session and request_code not in _legacy.proxy_sessions:
            try:
                await _sync_phase1_completion(
                    session,
                    broker_telegram_id,
                )
            except _legacy.JaccPhase1Error as exc:
                _legacy.logger.warning(
                    "Phase 1 completion sync skipped: %s",
                    exc,
                )
            except Exception:
                _legacy.logger.exception(
                    "Phase 1 completion sync failed"
                )


# legacy_bot.main resolves this global when it builds the callback handler.
_legacy.button_callback = button_callback


if __name__ == "__main__":
    try:
        asyncio.run(_legacy.main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
