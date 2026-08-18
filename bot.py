"""JACC bot compatibility wrapper with Phase 1 request safety guards.

The previous production launcher is preserved in ``bot_core.py``. This wrapper
re-exports its complete module surface, prevents duplicate legacy Request IDs,
and keeps customer cancellation synchronized with the central Supabase queue.
"""

from __future__ import annotations

from typing import Any

import bot_core as _core


# Preserve every public and private attribute expected by admin_launcher,
# completion_launcher, and queue_launcher.
for _name, _value in vars(_core).items():
    if _name not in {
        "__name__",
        "__file__",
        "__package__",
        "__spec__",
        "__loader__",
        "__cached__",
        "__builtins__",
    }:
        globals()[_name] = _value


_original_submit_request = _core.submit_request
_original_cancelrequest_cmd = _core._legacy.cancelrequest_cmd


async def _active_phase1_request(telegram_user_id: int) -> dict[str, Any] | None:
    """Return the member's newest open central request, when one exists."""
    if _core._legacy.phase1 is None:
        return None

    profile = await _core._legacy.phase1.get_profile_by_telegram_user_id(
        telegram_user_id
    )
    url = (
        f"{_core._legacy.phase1._base_url}/rest/v1/"
        "jacc_service_requests"
    )
    params = {
        "customer_id": f"eq.{profile['id']}",
        "status": "not.in.(completed,cancelled,closed_inactive)",
        "select": (
            "id,request_code,customer_id,assigned_broker_id,status,"
            "service_type,form_data,created_at"
        ),
        "order": "created_at.desc",
        "limit": "1",
    }
    async with _core._legacy.httpx.AsyncClient(
        timeout=_core._legacy.phase1._timeout
    ) as client:
        response = await client.get(
            url,
            headers=_core._legacy.phase1._headers,
            params=params,
        )

    if response.is_error:
        raise _core._legacy.JaccPhase1Error(
            "Active request lookup failed "
            f"({response.status_code}): {response.text[:500]}"
        )

    rows = response.json()
    return rows[0] if rows else None


async def _phase1_patch(
    table: str,
    *,
    filters: dict[str, str],
    values: dict[str, Any],
) -> None:
    """Patch Phase 1 rows using the server-side service-role connection."""
    phase1 = _core._legacy.phase1
    if phase1 is None:
        raise _core._legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{phase1._base_url}/rest/v1/{table}"
    headers = {**phase1._headers, "Prefer": "return=minimal"}
    async with _core._legacy.httpx.AsyncClient(
        timeout=phase1._timeout
    ) as client:
        response = await client.patch(
            url,
            headers=headers,
            params=filters,
            json=values,
        )

    if response.is_error:
        raise _core._legacy.JaccPhase1Error(
            f"Phase 1 patch failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )


async def _cancel_unassigned_phase1_request(request: dict[str, Any]) -> None:
    """Cancel a waiting/offered request and any outstanding broker offer."""
    phase1 = _core._legacy.phase1
    if phase1 is None:
        raise _core._legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    request_id = str(request["id"])
    old_status = str(request.get("status") or "waiting_broker")
    now_iso = _core._legacy.datetime.utcnow().isoformat() + "Z"

    await _phase1_patch(
        "jacc_request_offers",
        filters={"request_id": f"eq.{request_id}", "status": "eq.pending"},
        values={"status": "cancelled", "responded_at": now_iso},
    )
    await _phase1_patch(
        "jacc_request_assignments",
        filters={"request_id": f"eq.{request_id}", "status": "eq.active"},
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
            "completed_at": now_iso,
            "last_meaningful_update_at": now_iso,
        },
    )

    history_url = f"{phase1._base_url}/rest/v1/jacc_request_status_history"
    history_headers = {**phase1._headers, "Prefer": "return=minimal"}
    async with _core._legacy.httpx.AsyncClient(
        timeout=phase1._timeout
    ) as client:
        history_response = await client.post(
            history_url,
            headers=history_headers,
            json={
                "request_id": request_id,
                "old_status": old_status,
                "new_status": "cancelled",
                "changed_by": request.get("customer_id"),
                "reason": "Customer cancelled through Telegram /cancelrequest",
            },
        )

    if history_response.is_error:
        raise _core._legacy.JaccPhase1Error(
            "Phase 1 cancellation history insert failed "
            f"({history_response.status_code}): "
            f"{history_response.text[:500]}"
        )


async def submit_request(context, user_id: int, username: str):
    """Block duplicate legacy requests when the central request is still open."""
    try:
        active = await _active_phase1_request(int(user_id))
    except Exception:
        # A temporary lookup failure must not break the existing production flow.
        _core._legacy.logger.exception(
            "Active request duplicate guard lookup failed"
        )
        active = None

    if active:
        request_code = str(active.get("request_code") or "-")
        status = str(active.get("status") or "-")
        form_data = dict(active.get("form_data") or {})
        car_name = str(form_data.get("car_name") or "-")

        # Clear the just-completed form so it cannot be submitted again later.
        _core._legacy.pending_request.pop(int(user_id), None)

        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                "⚠️ *Active Request ရှိပြီးသားပါ*\n\n"
                f"🆔 Request ID: `{request_code}`\n"
                f"🚗 {car_name}\n"
                f"📊 Status: `{status}`\n\n"
                "လက်ရှိ Request ပြီးဆုံး/Cancel ဖြစ်ပြီးမှ Request အသစ်တင်နိုင်ပါမယ်။\n"
                "အခြေအနေကြည့်ရန် /mystatus"
            ),
            parse_mode="Markdown",
        )
        _core._legacy.logger.info(
            "Duplicate request blocked: user=%s active_request=%s",
            user_id,
            request_code,
        )
        return

    await _original_submit_request(context, user_id, username)


async def cancelrequest_cmd(update, context):
    """Cancel waiting/offered Phase 1 requests before using the legacy flow."""
    user_id = int(update.effective_user.id)

    # While the member is still filling the form, preserve the original quick
    # cancel behaviour and do not touch an older central request.
    if user_id in _core._legacy.pending_request:
        await _original_cancelrequest_cmd(update, context)
        return

    try:
        active = await _active_phase1_request(user_id)
    except Exception:
        _core._legacy.logger.exception("Phase 1 cancel lookup failed")
        await update.effective_message.reply_text(
            "❌ Cancel စစ်ဆေးမှု မအောင်မြင်ပါ — ခဏပြန်စမ်းပါ"
        )
        return

    if active and str(active.get("status")) in {"waiting_broker", "offered"}:
        request_code = str(active.get("request_code") or "-")
        try:
            await _cancel_unassigned_phase1_request(active)
        except Exception:
            _core._legacy.logger.exception(
                "Phase 1 request cancellation failed: %s",
                request_code,
            )
            await update.effective_message.reply_text(
                "❌ Request Cancel မအောင်မြင်ပါ — ခဏပြန်စမ်းပါ"
            )
            return

        # Remove any stale legacy in-memory copy and timer for the same code.
        for session_id, session in list(_core._legacy.proxy_sessions.items()):
            if str(session.get("reqId") or session_id) == request_code:
                _core._legacy.proxy_sessions.pop(session_id, None)
        _core._legacy.cancel_request_timer(request_code)

        try:
            async with _core._legacy.httpx.AsyncClient(
                follow_redirects=True
            ) as client:
                await client.post(
                    _core._legacy.SHEET_WEBHOOK,
                    json={
                        "action": "updateRequest",
                        "reqId": request_code,
                        "customerId": str(user_id),
                        "status": "CANCELLED_BY_CUSTOMER",
                    },
                    timeout=10,
                )
        except Exception:
            _core._legacy.logger.exception(
                "Legacy Sheet cancellation mirror failed: %s",
                request_code,
            )

        await update.effective_message.reply_text(
            "❌ *Request Cancel ပြီ*\n\n"
            f"🆔 `{request_code}`\n\n"
            "✅ Queue ထဲကနေ ဖယ်ရှားပြီးပါပြီ\n"
            "ပြန်တင်ရန်: /carrequest",
            parse_mode="Markdown",
        )
        await _core._legacy.notify_admins(
            context,
            "❌ *Phase 1 Customer Cancel*\n\n"
            f"🆔 `{request_code}`\n"
            f"👤 `{user_id}`",
        )
        return

    # Assigned/deposit-aware sessions keep the original cancellation rules.
    await _original_cancelrequest_cmd(update, context)


# Legacy handler registration resolves these attributes at runtime.
_core.submit_request = submit_request
_core._legacy.submit_request = submit_request
_core.cancelrequest_cmd = cancelrequest_cmd
_core._legacy.cancelrequest_cmd = cancelrequest_cmd
