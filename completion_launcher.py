"""JACC production launcher with Phase 1 completion and restart recovery.

Extends ``admin_launcher`` so a confirmed Broker ``/endchat`` action marks
the matching Supabase request and assignment as completed. On process startup,
active Phase 1 assignments are also restored into the legacy in-memory proxy
session cache so Railway restarts do not break customer-broker messaging.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

import admin_launcher as _admin


_bot = _admin._bot
_legacy = _admin._legacy
_original_button_callback = _legacy.button_callback


async def _phase1_get_many(
    table: str,
    *,
    filters: dict[str, str],
    select: str,
    order: str | None = None,
) -> list[dict[str, Any]]:
    """Read a list of Phase 1 rows through the service-role connection."""
    if _legacy.phase1 is None:
        return []

    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    params: dict[str, str] = {**filters, "select": select}
    if order:
        params["order"] = order

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
            f"Phase 1 recovery lookup failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )

    rows = response.json()
    return list(rows or [])


async def _restore_phase1_proxy_sessions() -> int:
    """Rebuild active Telegram proxy sessions from Supabase after a restart."""
    if _legacy.phase1 is None:
        _legacy.logger.info("Phase 1 session recovery skipped: not configured")
        return 0

    assignments = await _phase1_get_many(
        "jacc_request_assignments",
        filters={"status": "eq.active"},
        select="id,request_id,broker_id,service_type,assigned_at,status",
        order="assigned_at.asc",
    )
    if not assignments:
        _legacy.logger.info("Phase 1 session recovery: no active assignments")
        return 0

    restored = 0
    restored_broker_ids: set[str] = set()
    active_request_statuses = {
        "assigned",
        "consulting",
        "searching",
        "car_found",
        "waiting_customer",
        "waiting_payment",
        "payment_verifying",
        "payment_confirmed",
        "price_approval",
        "auction_pending",
        "won",
        "lost",
        "negotiating",
        "inspection_pending",
        "reserved",
        "purchased",
        "paused",
        "reassigned",
    }

    for assignment in assignments:
        try:
            request = await _bot._phase1_get_single(
                "jacc_service_requests",
                filters={"id": f"eq.{assignment['request_id']}"},
                select=(
                    "id,request_code,customer_id,service_type,status,form_data,"
                    "assigned_broker_id"
                ),
            )
            if str(request.get("status")) not in active_request_statuses:
                _legacy.logger.warning(
                    "Skipping inconsistent active assignment request=%s status=%s",
                    request.get("request_code"),
                    request.get("status"),
                )
                continue

            customer = await _bot._phase1_get_single(
                "jacc_profiles",
                filters={"id": f"eq.{request['customer_id']}"},
                select="id,display_name,telegram_user_id,account_active",
            )
            broker_user = await _bot._phase1_get_single(
                "jacc_profiles",
                filters={"id": f"eq.{assignment['broker_id']}"},
                select="id,display_name,telegram_user_id,account_active",
            )
            broker_profile = await _bot._phase1_get_single(
                "jacc_broker_profiles",
                filters={"user_id": f"eq.{assignment['broker_id']}"},
                select=(
                    "user_id,broker_code,account_status,rating,deals_count,"
                    "accepting_requests"
                ),
            )

            customer_tg_id = customer.get("telegram_user_id")
            broker_tg_id = broker_user.get("telegram_user_id")
            if customer_tg_id is None or broker_tg_id is None:
                _legacy.logger.warning(
                    "Cannot restore request=%s: missing Telegram identity",
                    request.get("request_code"),
                )
                continue
            if not customer.get("account_active") or not broker_user.get("account_active"):
                _legacy.logger.warning(
                    "Cannot restore request=%s: inactive account",
                    request.get("request_code"),
                )
                continue
            if str(broker_profile.get("account_status")) not in {"active", "probation"}:
                _legacy.logger.warning(
                    "Cannot restore request=%s: broker status=%s",
                    request.get("request_code"),
                    broker_profile.get("account_status"),
                )
                continue

            request_code = str(request["request_code"])
            form_data = dict(request.get("form_data") or {})
            service_type = (
                "auction"
                if str(request.get("service_type")) == "auction"
                else "search"
            )
            broker_tg_text = str(broker_tg_id)

            accepted_offers = await _phase1_get_many(
                "jacc_request_offers",
                filters={
                    "request_id": f"eq.{request['id']}",
                    "broker_id": f"eq.{assignment['broker_id']}",
                    "status": "eq.accepted",
                    "limit": "1",
                },
                select="id",
                order="responded_at.desc",
            )
            offer_id = str(accepted_offers[0]["id"]) if accepted_offers else ""

            _legacy.proxy_sessions[request_code] = {
                "customerId": int(customer_tg_id),
                "customerUsername": form_data.get("username", ""),
                "brokerId": broker_tg_text,
                "brokerObj": {
                    "brokerId": broker_profile.get("broker_code", "B???"),
                    "username": broker_user.get("display_name", ""),
                    "rating": broker_profile.get("rating", 0),
                    "deals": broker_profile.get("deals_count", 0),
                },
                "reqId": request_code,
                "status": "ACTIVE",
                "serviceType": service_type,
                "startTime": assignment.get("assigned_at") or "",
                "phase1RequestId": str(request["id"]),
                "phase1OfferId": offer_id,
                "phase1AssignmentId": str(assignment["id"]),
                "restoredAfterRestart": True,
            }
            restored_broker_ids.add(broker_tg_text)
            restored += 1
        except Exception:
            _legacy.logger.exception(
                "Failed to restore Phase 1 assignment=%s",
                assignment.get("id"),
            )

    # Keep the legacy Google Sheet capacity display aligned, but preserve an
    # explicit BUSY/BANNED/KICKED choice made by an admin or broker.
    if restored_broker_ids:
        legacy_brokers = await _legacy.get_brokers()
        broker_rows = {
            str(item.get("telegramId", "")): item
            for item in legacy_brokers
        }
        for broker_tg_id in restored_broker_ids:
            current_status = str(
                broker_rows.get(broker_tg_id, {}).get("status", "")
            ).upper()
            if current_status in {"BUSY", "BANNED", "KICKED"}:
                continue
            recovered_status = _legacy.recalc_broker_status(broker_tg_id)
            await _legacy.update_broker(
                broker_tg_id,
                status=recovered_status,
            )

    _legacy.logger.info(
        "Phase 1 session recovery complete restored=%s active_assignments=%s",
        restored,
        len(assignments),
    )
    return restored


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


async def main() -> None:
    try:
        await _restore_phase1_proxy_sessions()
    except Exception:
        # Recovery failure must not prevent the Telegram bot from starting.
        _legacy.logger.exception("Phase 1 startup session recovery failed")
    await _legacy.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
