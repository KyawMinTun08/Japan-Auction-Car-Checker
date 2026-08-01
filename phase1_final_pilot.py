"""Admin-only final production pilot for JACC Phase 1.

The command combines the two remaining safe verification tasks:
1. Exercise the exact startup proxy-session recovery function against an
   isolated active Supabase assignment.
2. Run ten complete request/offer/accept/complete lifecycles through the real
   Supabase RPCs using isolated synthetic profiles.

All test rows and in-memory test sessions are removed before returning.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from telegram.ext import ExtBot

import completion_launcher as _completion
import phase1_resilience_test as _resilience
import phase1_selftest as _self
import queue_launcher as _queue


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_existing_set_my_commands = ExtBot.set_my_commands
_original_admin_cmd = _queue.admin_cmd
_FINAL_PILOT_LOCK = asyncio.Lock()


def _low_uuid(token: str, index: int) -> str:
    """Return deterministic low-sorting UUIDs for isolated broker selection."""
    tail = f"{token[:10]}{index:02x}"[:12]
    return f"00000000-0000-4000-8000-{tail}"


async def _create_profile_with_id(
    *,
    profile_id: str,
    role: str,
    display_name: str,
    telegram_user_id: int | None = None,
) -> dict:
    rows = await _self._rest(
        "POST",
        "jacc_profiles",
        payload={
            "id": profile_id,
            "role": role,
            "display_name": display_name,
            "telegram_user_id": telegram_user_id,
            "account_active": True,
        },
        prefer="return=representation",
    )
    if not rows:
        raise _self.Phase1SelfTestError("Synthetic profile insert returned no row")
    return rows[0]


async def _run_isolated_restart_recovery(token: str) -> str:
    profile_ids: list[str] = []
    request_ids: list[str] = []
    request_code = f"RRP-{token[:8]}"

    # Negative Telegram IDs are valid bigint test identities and cannot collide
    # with normal Telegram user IDs used by production members.
    number = int(token[:8], 16)
    customer_tg_id = -(8_000_000_000 + number)
    broker_tg_id = -(9_000_000_000 + number)

    try:
        customer_id = str(uuid4())
        broker_id = _low_uuid(token, 240)
        customer = await _create_profile_with_id(
            profile_id=customer_id,
            role="customer",
            display_name=f"__P1_RESTART_CUSTOMER_{token}",
            telegram_user_id=customer_tg_id,
        )
        broker = await _create_profile_with_id(
            profile_id=broker_id,
            role="broker",
            display_name=f"__P1_RESTART_BROKER_{token}",
            telegram_user_id=broker_tg_id,
        )
        profile_ids.extend([str(customer["id"]), str(broker["id"])])

        await _self._rest(
            "POST",
            "jacc_broker_profiles",
            payload={
                "user_id": broker_id,
                "broker_code": f"Z{token[:7]}",
                "account_status": "active",
                "accepting_requests": False,
                "can_auction": True,
                "can_outside_car": True,
            },
            prefer="return=minimal",
        )

        request_rows = await _self._rest(
            "POST",
            "jacc_service_requests",
            payload={
                "request_code": request_code,
                "customer_id": customer_id,
                "service_type": "outside_car",
                "service_channel": "telegram",
                "status": "assigned",
                "assigned_broker_id": broker_id,
                "last_meaningful_update_at": datetime.now(timezone.utc).isoformat(),
                "form_data": {
                    "selftest": True,
                    "selftest_token": token,
                    "selftest_case": "ISOLATED_RESTART_RECOVERY",
                    "username": f"restart_customer_{token}",
                    "car_name": "RESTART-PILOT",
                },
            },
            prefer="return=representation",
        )
        if not request_rows:
            raise _self.Phase1SelfTestError("Restart pilot request insert failed")
        request_id = str(request_rows[0]["id"])
        request_ids.append(request_id)

        offer_rows = await _self._rest(
            "POST",
            "jacc_request_offers",
            payload={
                "request_id": request_id,
                "broker_id": broker_id,
                "sequence_no": 1,
                "status": "accepted",
                "offered_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": datetime.now(timezone.utc).isoformat(),
                "responded_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        if not offer_rows:
            raise _self.Phase1SelfTestError("Restart pilot offer insert failed")

        assignment_rows = await _self._rest(
            "POST",
            "jacc_request_assignments",
            payload={
                "request_id": request_id,
                "broker_id": broker_id,
                "service_type": "outside_car",
                "status": "active",
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        if not assignment_rows:
            raise _self.Phase1SelfTestError("Restart pilot assignment insert failed")

        # Simulate the volatile state loss caused by a Railway process restart,
        # then invoke the exact function called before Telegram polling starts.
        _legacy.proxy_sessions.pop(request_code, None)
        await _completion._restore_phase1_proxy_sessions()

        restored = dict(_legacy.proxy_sessions.get(request_code) or {})
        if (
            restored.get("status") != "ACTIVE"
            or restored.get("restoredAfterRestart") is not True
            or int(restored.get("customerId")) != customer_tg_id
            or str(restored.get("brokerId")) != str(broker_tg_id)
            or str(restored.get("phase1RequestId")) != request_id
            or not restored.get("phase1AssignmentId")
        ):
            raise _self.Phase1SelfTestError(
                f"Restart recovery produced unexpected session: {restored}"
            )

        return "✅ Isolated Railway-style restart recovery restored the active chat session"
    finally:
        _legacy.proxy_sessions.pop(request_code, None)
        await _self._cleanup(profile_ids, request_ids)


async def _complete_pilot_request(request_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await _self._rest(
        "PATCH",
        "jacc_request_assignments",
        params={"request_id": f"eq.{request_id}", "status": "eq.active"},
        payload={
            "status": "completed",
            "ended_at": now,
            "ended_reason": "PHASE1_FINAL_10_REQUEST_PILOT",
        },
        prefer="return=minimal",
    )
    await _self._rest(
        "PATCH",
        "jacc_service_requests",
        params={"id": f"eq.{request_id}"},
        payload={
            "status": "completed",
            "completed_at": now,
            "last_meaningful_update_at": now,
        },
        prefer="return=minimal",
    )


async def _run_ten_request_live_pilot(token: str) -> str:
    profile_ids: list[str] = []
    request_ids: list[str] = []
    broker_ids: list[str] = []
    selected_brokers: list[str] = []

    try:
        # Low-sorting isolated broker UUIDs ensure the dispatch RPC selects only
        # pilot brokers, without changing availability of real brokers.
        for index in range(1, 11):
            broker_id = _low_uuid(token, index)
            broker_ids.append(broker_id)
            broker = await _create_profile_with_id(
                profile_id=broker_id,
                role="broker",
                display_name=f"__P1_10PILOT_BROKER_{index}_{token}",
            )
            profile_ids.append(str(broker["id"]))
            await _self._rest(
                "POST",
                "jacc_broker_profiles",
                payload={
                    "user_id": broker_id,
                    "broker_code": f"P{index:02d}{token[:4]}",
                    "account_status": "active",
                    "accepting_requests": True,
                    "can_auction": True,
                    "can_outside_car": True,
                },
                prefer="return=minimal",
            )

        client = _self._phase1_client()
        for index in range(1, 11):
            customer_id = str(uuid4())
            customer = await _create_profile_with_id(
                profile_id=customer_id,
                role="customer",
                display_name=f"__P1_10PILOT_CUSTOMER_{index}_{token}",
            )
            profile_ids.append(str(customer["id"]))

            service_type = "auction" if index % 2 == 0 else "outside_car"
            request_rows = await _self._rest(
                "POST",
                "jacc_service_requests",
                payload={
                    "request_code": f"P10-{token[:6]}-{index:02d}",
                    "customer_id": customer_id,
                    "service_type": service_type,
                    "service_channel": "telegram",
                    # Keep the request invisible to the 30-second queue worker;
                    # the pilot invokes the production dispatch RPC directly.
                    "status": "paused",
                    "form_data": {
                        "selftest": True,
                        "selftest_token": token,
                        "selftest_case": "FINAL_10_REQUEST_PILOT",
                        "pilot_number": index,
                        "car_name": f"PILOT-CAR-{index:02d}",
                    },
                    "priority": index,
                },
                prefer="return=representation",
            )
            if not request_rows:
                raise _self.Phase1SelfTestError(
                    f"Pilot request {index} insert returned no row"
                )
            request_id = str(request_rows[0]["id"])
            request_ids.append(request_id)

            offer = await client.dispatch_next_offer(request_id)
            if offer is None:
                raise _self.Phase1SelfTestError(
                    f"Pilot request {index} did not receive an offer"
                )
            if str(offer.broker_id) not in set(broker_ids):
                raise _self.Phase1SelfTestError(
                    f"Pilot request {index} selected a non-pilot broker"
                )
            selected_brokers.append(str(offer.broker_id))

            assignment = await client.accept_offer(
                offer_id=str(offer.offer_id),
                broker_id=str(offer.broker_id),
            )
            if str(assignment.get("status")) != "active":
                raise _self.Phase1SelfTestError(
                    f"Pilot request {index} accept did not create active assignment"
                )
            await _complete_pilot_request(request_id)

        id_filter = f"in.({','.join(request_ids)})"
        requests = await _self._rest(
            "GET",
            "jacc_service_requests",
            params={
                "id": id_filter,
                "select": "id,status,request_code,assigned_broker_id",
            },
        ) or []
        offers = await _self._rest(
            "GET",
            "jacc_request_offers",
            params={
                "request_id": id_filter,
                "select": "id,request_id,broker_id,status",
            },
        ) or []
        assignments = await _self._rest(
            "GET",
            "jacc_request_assignments",
            params={
                "request_id": id_filter,
                "select": "id,request_id,broker_id,status,ended_reason",
            },
        ) or []

        if len(requests) != 10 or any(row.get("status") != "completed" for row in requests):
            raise _self.Phase1SelfTestError("Not all ten pilot requests completed")
        if len(offers) != 10 or any(row.get("status") != "accepted" for row in offers):
            raise _self.Phase1SelfTestError("Not all ten pilot offers were accepted")
        if len(assignments) != 10 or any(
            row.get("status") != "completed" for row in assignments
        ):
            raise _self.Phase1SelfTestError("Not all ten assignments completed")
        if len(set(selected_brokers)) != 10:
            raise _self.Phase1SelfTestError(
                f"Fair dispatch did not use ten distinct pilot brokers: {selected_brokers}"
            )

        return (
            "✅ Real Supabase 10-request pilot passed: "
            "10 dispatched, 10 accepted, 10 completed, 10 distinct brokers"
        )
    finally:
        await _self._cleanup(profile_ids, request_ids)


async def phase1finalpilot_cmd(update, context):
    message = update.effective_message
    user = update.effective_user
    if not _legacy.ADMIN_IDS or int(user.id) not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return
    if _FINAL_PILOT_LOCK.locked():
        await message.reply_text("⏳ Final pilot တစ်ခု လည်နေပြီးသားပါ")
        return

    async with _FINAL_PILOT_LOCK:
        token = uuid4().hex[:10]
        await message.reply_text(
            "🚦 JACC Phase 1 final pilot စနေပါပြီ…\n\n"
            "1️⃣ Isolated restart recovery\n"
            "2️⃣ Real Supabase 10-request lifecycle\n\n"
            "Synthetic data ပဲသုံးပြီး ပြီးရင် cleanup လုပ်ပါမယ်။ "
            "၂–၃ မိနစ်ခန့်ကြာနိုင်ပါတယ်။"
        )
        try:
            restart_result = await asyncio.wait_for(
                _run_isolated_restart_recovery(token), timeout=90
            )
            ten_request_result = await asyncio.wait_for(
                _run_ten_request_live_pilot(token), timeout=150
            )
            await message.reply_text(
                "🟢 JACC PHASE 1 FINAL PILOT — PASS\n\n"
                f"{restart_result}\n"
                f"{ten_request_result}\n\n"
                "🧹 Synthetic test data cleanup ပြီးပါပြီ။"
            )
        except asyncio.TimeoutError:
            _legacy.logger.exception("Phase 1 final pilot timed out")
            await message.reply_text(
                "🔴 JACC PHASE 1 FINAL PILOT — TIMEOUT\n\n"
                "Cleanup ကို run လုပ်ထားပါတယ်။ Logs စစ်ရန်လိုပါတယ်။"
            )
        except Exception as exc:
            _legacy.logger.exception("Phase 1 final pilot failed")
            await message.reply_text(
                "🔴 JACC PHASE 1 FINAL PILOT — FAILED\n\n"
                f"{str(exc)[:900]}\n\n"
                "🧹 Synthetic cleanup ကို run လုပ်ထားပါတယ်။"
            )


async def brokers_final_pilot_router(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/phase1finalpilot":
        await phase1finalpilot_cmd(update, context)
        return
    await _resilience.brokers_resilience_router(update, context)


def _command_handler_with_final_pilot(command, callback, *args, **kwargs):
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
                "phase1finalpilot",
            ],
            brokers_final_pilot_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def admin_cmd(update, context):
    await _original_admin_cmd(update, context)
    await update.effective_message.reply_text(
        "🚦 /phase1finalpilot — Isolated restart recovery + real 10-request pilot"
    )


async def _set_my_commands_with_final_pilot(self, commands, *args, **kwargs):
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    existing = {getattr(item, "command", "") for item in patched}
    if is_admin_scope and "phase1finalpilot" not in existing:
        patched.append(
            _legacy.BotCommand(
                "phase1finalpilot",
                "🚦 Phase 1 Final Pilot",
            )
        )
    return await _existing_set_my_commands(self, patched, *args, **kwargs)


_legacy.CommandHandler = _command_handler_with_final_pilot
_queue.admin_cmd = admin_cmd
ExtBot.set_my_commands = _set_my_commands_with_final_pilot
