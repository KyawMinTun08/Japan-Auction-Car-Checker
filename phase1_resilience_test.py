"""Admin-only live resilience test for JACC Phase 1.

This command verifies the real Supabase recovery path without touching customer
rows. It creates isolated synthetic data, waits for the deployed recovery worker
to process a deliberately invalid Telegram delivery, verifies retry/dead-letter
state, verifies the 48-hour stale-assignment RPC, and removes all test data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from telegram.ext import ExtBot

import phase1_selftest as _self
import queue_launcher as _queue


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_existing_set_my_commands = ExtBot.set_my_commands
_original_admin_cmd = _queue.admin_cmd
_RESILIENCE_LOCK = asyncio.Lock()


async def _wait_for_outbox(outbox_id: str, wanted: set[str], timeout: float = 55.0):
    deadline = asyncio.get_running_loop().time() + timeout
    last_row = None
    while asyncio.get_running_loop().time() < deadline:
        rows = await _self._rest(
            "GET",
            "jacc_message_outbox",
            params={
                "id": f"eq.{outbox_id}",
                "select": "id,status,attempt_count,max_attempts,available_at,last_error",
                "limit": "1",
            },
        )
        if rows:
            last_row = rows[0]
            if str(last_row.get("status")) in wanted:
                return last_row
        await asyncio.sleep(3)
    raise _self.Phase1SelfTestError(
        f"Outbox timeout waiting for {sorted(wanted)}; last={last_row}"
    )


async def _run_outbox_resilience_test(token: str) -> str:
    rows = await _self._rest(
        "POST",
        "jacc_message_outbox",
        payload={
            "channel": "telegram",
            "message_type": "phase1_resilience_test",
            "payload": {
                "chat_id": "-999999999999999",
                "text": f"JACC synthetic resilience test {token}",
            },
            "dedupe_key": f"phase1-resilience:{token}",
            "status": "queued",
            "priority": 999,
            "max_attempts": 2,
            "available_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=representation",
    )
    if not rows:
        raise _self.Phase1SelfTestError("Synthetic outbox insert returned no row")
    outbox_id = str(rows[0]["id"])

    try:
        first = await _wait_for_outbox(
            outbox_id,
            {"retrying", "failed", "dead_letter"},
        )
        if str(first.get("status")) != "dead_letter":
            await _self._rest(
                "PATCH",
                "jacc_message_outbox",
                params={"id": f"eq.{outbox_id}"},
                payload={
                    "available_at": (
                        datetime.now(timezone.utc) - timedelta(seconds=1)
                    ).isoformat()
                },
                prefer="return=minimal",
            )

        final = await _wait_for_outbox(outbox_id, {"dead_letter"})
        attempts = await _self._rest(
            "GET",
            "jacc_delivery_attempts",
            params={
                "outbox_id": f"eq.{outbox_id}",
                "select": "id,attempt_no,success,error_message",
                "order": "attempt_no.asc",
            },
        )
        if int(final.get("attempt_count") or 0) < 2 or len(attempts or []) < 2:
            raise _self.Phase1SelfTestError(
                "Outbox did not record two controlled delivery attempts"
            )
        return "✅ Real outbox retry → dead-letter worker path passed"
    finally:
        await _self._rest(
            "DELETE",
            "jacc_message_outbox",
            params={"id": f"eq.{outbox_id}"},
            prefer="return=minimal",
        )


async def _run_stale_reassignment_test(token: str) -> str:
    profile_ids: list[str] = []
    request_ids: list[str] = []
    try:
        customer = await _self._create_profile(
            role="customer",
            display_name=f"__P1_RESILIENCE_CUSTOMER_{token}",
        )
        broker = await _self._create_profile(
            role="broker",
            display_name=f"__P1_RESILIENCE_BROKER_{token}",
        )
        profile_ids.extend([str(customer["id"]), str(broker["id"])])
        await _self._create_broker(str(broker["id"]), f"Z{token[:7]}")

        stale_time = datetime.now(timezone.utc) - timedelta(hours=49)
        rows = await _self._rest(
            "POST",
            "jacc_service_requests",
            payload={
                "request_code": f"RST-{token[:8]}",
                "customer_id": str(customer["id"]),
                "service_type": "outside_car",
                "service_channel": "telegram",
                "status": "assigned",
                "assigned_broker_id": str(broker["id"]),
                "last_meaningful_update_at": stale_time.isoformat(),
                "form_data": {
                    "selftest": True,
                    "selftest_token": token,
                    "selftest_case": "STALE_48H",
                },
            },
            prefer="return=representation",
        )
        if not rows:
            raise _self.Phase1SelfTestError("Synthetic stale request insert failed")
        request = rows[0]
        request_id = str(request["id"])
        request_ids.append(request_id)

        assignments = await _self._rest(
            "POST",
            "jacc_request_assignments",
            payload={
                "request_id": request_id,
                "broker_id": str(broker["id"]),
                "service_type": "outside_car",
                "status": "active",
                "assigned_at": stale_time.isoformat(),
            },
            prefer="return=representation",
        )
        if not assignments:
            raise _self.Phase1SelfTestError("Synthetic stale assignment insert failed")
        assignment_id = str(assignments[0]["id"])

        stale_rows = await _self._phase1_client().reassign_stale_requests()
        if request_id not in {str(row.get("request_id")) for row in stale_rows}:
            raise _self.Phase1SelfTestError("48-hour RPC did not return test request")

        request_rows = await _self._rest(
            "GET",
            "jacc_service_requests",
            params={
                "id": f"eq.{request_id}",
                "select": "status,assigned_broker_id,last_meaningful_update_at",
                "limit": "1",
            },
        )
        assignment_rows = await _self._rest(
            "GET",
            "jacc_request_assignments",
            params={
                "id": f"eq.{assignment_id}",
                "select": "status,ended_reason,ended_at",
                "limit": "1",
            },
        )
        if not request_rows or not assignment_rows:
            raise _self.Phase1SelfTestError("Stale result rows missing")

        request_after = request_rows[0]
        assignment_after = assignment_rows[0]
        if (
            str(request_after.get("status")) != "reassigned"
            or request_after.get("assigned_broker_id") is not None
            or str(assignment_after.get("status")) != "reassigned"
            or str(assignment_after.get("ended_reason"))
            != "48_HOUR_NO_MEANINGFUL_UPDATE"
        ):
            raise _self.Phase1SelfTestError(
                "48-hour stale reassignment produced unexpected state"
            )
        return "✅ Real 48-hour stale reassignment RPC passed"
    finally:
        await _self._cleanup(profile_ids, request_ids)


async def phase1resiliencetest_cmd(update, context):
    message = update.effective_message
    user = update.effective_user
    if not _legacy.ADMIN_IDS or int(user.id) not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return
    if _RESILIENCE_LOCK.locked():
        await message.reply_text("⏳ Resilience test တစ်ခု လည်နေပြီးသားပါ")
        return

    async with _RESILIENCE_LOCK:
        token = uuid4().hex[:10]
        await message.reply_text(
            "🧯 Phase 1 live resilience test စနေပါပြီ…\n"
            "Real recovery worker + synthetic database rows ကိုသုံးပြီး cleanup လုပ်ပါမယ်။\n"
            "အများဆုံး ၂ မိနစ်ခန့်ကြာနိုင်ပါတယ်။"
        )
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    _run_outbox_resilience_test(token),
                    _run_stale_reassignment_test(token),
                ),
                timeout=140,
            )
            await message.reply_text(
                "🟢 JACC PHASE 1 LIVE RESILIENCE TEST — PASS\n\n"
                + "\n".join(results)
                + "\n\n🧹 Synthetic test data cleanup ပြီးပါပြီ။"
            )
        except asyncio.TimeoutError:
            await message.reply_text(
                "🔴 Resilience test timeout ဖြစ်ပါတယ် — worker/logs စစ်ရန်လိုပါတယ်"
            )
        except Exception as exc:
            _legacy.logger.exception("Phase 1 live resilience test failed")
            await message.reply_text(
                "🔴 JACC PHASE 1 LIVE RESILIENCE TEST — FAILED\n\n"
                f"{str(exc)[:900]}\n\n"
                "🧹 Synthetic cleanup ကို run လုပ်ထားပါတယ်။"
            )


async def brokers_resilience_router(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/phase1resiliencetest":
        await phase1resiliencetest_cmd(update, context)
        return
    await _self.brokers_selftest_router(update, context)


def _command_handler_with_resilience(command, callback, *args, **kwargs):
    if command == "brokers":
        return _existing_command_handler(
            [
                "brokers",
                "brokerfree",
                "brokerbusy",
                "queue",
                "phase1check",
                "phase1selftest",
                "phase1resiliencetest",
            ],
            brokers_resilience_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def admin_cmd(update, context):
    await _original_admin_cmd(update, context)
    await update.effective_message.reply_text(
        "🧯 /phase1resiliencetest — Real outbox retry/dead-letter + 48h stale test"
    )


async def _set_my_commands_with_resilience(self, commands, *args, **kwargs):
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    existing = {getattr(item, "command", "") for item in patched}
    if is_admin_scope and "phase1resiliencetest" not in existing:
        patched.append(
            _legacy.BotCommand(
                "phase1resiliencetest",
                "🧯 Phase 1 Live Resilience Test",
            )
        )
    return await _existing_set_my_commands(self, patched, *args, **kwargs)


_legacy.CommandHandler = _command_handler_with_resilience
_queue.admin_cmd = admin_cmd
ExtBot.set_my_commands = _set_my_commands_with_resilience
