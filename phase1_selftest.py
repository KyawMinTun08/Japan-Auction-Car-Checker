"""Admin-only database self-test for JACC Phase 1.

The test creates isolated synthetic customers, brokers, requests and offers.
Synthetic brokers remain unavailable, so assignment workers cannot route real
requests to them. All synthetic rows are removed before the command returns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
from telegram.ext import ExtBot

import phase1_healthcheck as _health
import queue_launcher as _queue


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_existing_set_my_commands = ExtBot.set_my_commands
_original_admin_cmd = _queue.admin_cmd
_SELFTEST_LOCK = asyncio.Lock()


class Phase1SelfTestError(RuntimeError):
    pass


def _phase1_client():
    client = _legacy.phase1
    if client is None:
        raise Phase1SelfTestError("PHASE1_NOT_CONFIGURED")
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
    async with httpx.AsyncClient(timeout=client._timeout) as session:
        response = await session.request(
            method,
            url,
            headers=headers,
            params=params,
            json=payload,
        )

    if response.is_error:
        raise Phase1SelfTestError(
            f"{method} {table} failed ({response.status_code}): "
            f"{response.text[:700]}"
        )
    if not response.content:
        return None
    return response.json()


async def _create_profile(*, role: str, display_name: str) -> dict[str, Any]:
    rows = await _rest(
        "POST",
        "jacc_profiles",
        payload={
            "role": role,
            "display_name": display_name,
            "telegram_user_id": None,
            "account_active": True,
        },
        prefer="return=representation",
    )
    if not rows:
        raise Phase1SelfTestError("Synthetic profile insert returned no row")
    return rows[0]


async def _create_broker(profile_id: str, broker_code: str) -> None:
    # Keep accepting_requests false. Workers will never select test brokers.
    await _rest(
        "POST",
        "jacc_broker_profiles",
        payload={
            "user_id": profile_id,
            "broker_code": broker_code,
            "account_status": "active",
            "accepting_requests": False,
            "can_auction": True,
            "can_outside_car": True,
        },
        prefer="return=minimal",
    )


async def _create_paused_request(
    customer_id: str,
    token: str,
    case: str,
    number: int,
) -> dict[str, Any]:
    rows = await _rest(
        "POST",
        "jacc_service_requests",
        payload={
            "request_code": f"TST-{token[:8]}-{number}",
            "customer_id": customer_id,
            "service_type": "outside_car",
            "service_channel": "telegram",
            "status": "paused",
            "form_data": {
                "selftest": True,
                "selftest_token": token,
                "selftest_case": case,
                "car_name": f"SELFTEST-{case}",
            },
            "priority": 0,
        },
        prefer="return=representation",
    )
    if not rows:
        raise Phase1SelfTestError(f"Synthetic request insert failed for {case}")
    return rows[0]


async def _insert_offer(
    *,
    request_id: str,
    broker_id: str,
    sequence_no: int,
    expired: bool = False,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires_at = now - timedelta(minutes=1) if expired else now + timedelta(minutes=10)
    rows = await _rest(
        "POST",
        "jacc_request_offers",
        payload={
            "request_id": request_id,
            "broker_id": broker_id,
            "sequence_no": sequence_no,
            "status": "pending",
            "offered_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        prefer="return=representation",
    )
    if not rows:
        raise Phase1SelfTestError("Synthetic offer insert returned no row")
    await _rest(
        "PATCH",
        "jacc_service_requests",
        params={"id": f"eq.{request_id}"},
        payload={"status": "offered"},
        prefer="return=minimal",
    )
    return rows[0]


async def _patch_request_status(request_id: str, status: str) -> None:
    await _rest(
        "PATCH",
        "jacc_service_requests",
        params={"id": f"eq.{request_id}"},
        payload={"status": status},
        prefer="return=minimal",
    )


async def _row_status(table: str, row_id: str) -> str | None:
    rows = await _rest(
        "GET",
        table,
        params={"id": f"eq.{row_id}", "select": "status", "limit": "1"},
    )
    return str(rows[0].get("status")) if rows else None


async def _delete_test_requests(request_ids: list[str]) -> None:
    ids = list(dict.fromkeys(value for value in request_ids if value))
    if not ids:
        return
    in_filter = f"in.({','.join(ids)})"
    await _rest(
        "DELETE",
        "jacc_message_outbox",
        params={"request_id": in_filter},
        prefer="return=minimal",
    )
    await _rest(
        "DELETE",
        "jacc_service_requests",
        params={"id": in_filter},
        prefer="return=minimal",
    )


async def _cleanup(profile_ids: list[str], request_ids: list[str]) -> None:
    try:
        await _delete_test_requests(request_ids)
    except Exception:
        _legacy.logger.exception("Phase 1 self-test request cleanup failed")

    ids = list(dict.fromkeys(value for value in profile_ids if value))
    if not ids:
        return
    try:
        await _rest(
            "DELETE",
            "jacc_profiles",
            params={"id": f"in.({','.join(ids)})"},
            prefer="return=minimal",
        )
    except Exception:
        _legacy.logger.exception("Phase 1 self-test profile cleanup failed")


async def _run_selftest() -> list[str]:
    token = uuid4().hex[:10]
    profile_ids: list[str] = []
    request_ids: list[str] = []
    results: list[str] = []

    try:
        customer_a = await _create_profile(
            role="customer", display_name=f"__P1_TEST_CUSTOMER_A_{token}"
        )
        customer_b = await _create_profile(
            role="customer", display_name=f"__P1_TEST_CUSTOMER_B_{token}"
        )
        broker_a = await _create_profile(
            role="broker", display_name=f"__P1_TEST_BROKER_A_{token}"
        )
        broker_b = await _create_profile(
            role="broker", display_name=f"__P1_TEST_BROKER_B_{token}"
        )
        profile_ids.extend(
            [customer_a["id"], customer_b["id"], broker_a["id"], broker_b["id"]]
        )
        await _create_broker(broker_a["id"], f"T{token[:6]}A")
        await _create_broker(broker_b["id"], f"T{token[:6]}B")

        # 1) Decline RPC must close the first offer and return request to queue.
        request_decline = await _create_paused_request(
            customer_a["id"], token, "DECLINE", 1
        )
        request_ids.append(request_decline["id"])
        first_offer = await _insert_offer(
            request_id=request_decline["id"],
            broker_id=broker_a["id"],
            sequence_no=1,
        )
        returned_request_id = await _phase1_client().decline_offer(
            offer_id=first_offer["id"],
            broker_id=broker_a["id"],
            reason="PHASE1_SELFTEST_DECLINE",
        )
        if returned_request_id != request_decline["id"]:
            raise Phase1SelfTestError("Decline RPC returned the wrong request")
        if await _row_status("jacc_request_offers", first_offer["id"]) != "declined":
            raise Phase1SelfTestError("Declined offer status was not persisted")

        # Pause before inserting the next sequence so workers cannot claim it.
        await _patch_request_status(request_decline["id"], "paused")
        second_offer = await _insert_offer(
            request_id=request_decline["id"],
            broker_id=broker_b["id"],
            sequence_no=2,
        )
        if second_offer["broker_id"] == first_offer["broker_id"]:
            raise Phase1SelfTestError("Sequential handoff did not change broker")
        results.append("✅ Decline persisted and next sequence moved to another broker")
        await _delete_test_requests([request_decline["id"]])

        # 2) Two simultaneous accepts on one offer: exactly one may win.
        request_accept = await _create_paused_request(
            customer_a["id"], token, "CONCURRENCY", 2
        )
        request_ids.append(request_accept["id"])
        accept_offer = await _insert_offer(
            request_id=request_accept["id"],
            broker_id=broker_a["id"],
            sequence_no=1,
        )
        accept_results = await asyncio.gather(
            _phase1_client().accept_offer(
                offer_id=accept_offer["id"], broker_id=broker_a["id"]
            ),
            _phase1_client().accept_offer(
                offer_id=accept_offer["id"], broker_id=broker_a["id"]
            ),
            return_exceptions=True,
        )
        success_count = sum(
            1
            for value in accept_results
            if isinstance(value, dict) and bool(value.get("id"))
        )
        rejected_count = sum(1 for value in accept_results if isinstance(value, Exception))
        if success_count != 1 or rejected_count != 1:
            raise Phase1SelfTestError(
                "Concurrent accept lock failed: "
                f"success={success_count}, rejected={rejected_count}"
            )
        results.append("✅ Concurrent double-accept lock allowed one winner only")

        # 3) Same broker cannot accept a second outside-car assignment.
        request_capacity = await _create_paused_request(
            customer_b["id"], token, "CAPACITY", 3
        )
        request_ids.append(request_capacity["id"])
        full_offer = await _insert_offer(
            request_id=request_capacity["id"],
            broker_id=broker_a["id"],
            sequence_no=1,
        )
        capacity_blocked = False
        try:
            await _phase1_client().accept_offer(
                offer_id=full_offer["id"], broker_id=broker_a["id"]
            )
        except Exception as exc:
            capacity_blocked = "BROKER_SERVICE_CAPACITY_FULL" in str(exc)
        if not capacity_blocked:
            raise Phase1SelfTestError("Broker capacity guard did not reject second job")

        await _rest(
            "PATCH",
            "jacc_request_offers",
            params={"id": f"eq.{full_offer['id']}"},
            payload={
                "status": "cancelled",
                "responded_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=minimal",
        )
        await _patch_request_status(request_capacity["id"], "paused")
        alternate_offer = await _insert_offer(
            request_id=request_capacity["id"],
            broker_id=broker_b["id"],
            sequence_no=2,
        )
        alternate_assignment = await _phase1_client().accept_offer(
            offer_id=alternate_offer["id"], broker_id=broker_b["id"]
        )
        if not alternate_assignment.get("id"):
            raise Phase1SelfTestError("Alternate broker could not accept capacity handoff")
        results.append("✅ Capacity guard blocked broker A and allowed broker B")
        await _delete_test_requests([request_accept["id"], request_capacity["id"]])

        # 4) Expired pending offer must become expired and request return to queue.
        request_expiry = await _create_paused_request(
            customer_a["id"], token, "EXPIRY", 4
        )
        request_ids.append(request_expiry["id"])
        expiry_offer = await _insert_offer(
            request_id=request_expiry["id"],
            broker_id=broker_a["id"],
            sequence_no=1,
            expired=True,
        )
        expired_requests = await _phase1_client().expire_pending_offers()
        offer_status = await _row_status("jacc_request_offers", expiry_offer["id"])
        request_status = await _row_status("jacc_service_requests", request_expiry["id"])
        if offer_status != "expired" or request_status != "waiting_broker":
            raise Phase1SelfTestError(
                "Offer expiry rule failed: "
                f"offer={offer_status}, request={request_status}"
            )
        if request_expiry["id"] not in expired_requests:
            raise Phase1SelfTestError("Expiry RPC did not return the test request")
        results.append("✅ Expired offer returned request to waiting_broker")

        return results
    finally:
        await _cleanup(profile_ids, request_ids)


async def phase1selftest_cmd(update, context):
    message = update.effective_message
    user = update.effective_user
    if not _legacy.ADMIN_IDS or int(user.id) not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return
    if _SELFTEST_LOCK.locked():
        await message.reply_text("⏳ Phase 1 Self-test တစ်ခု လည်နေပြီးသားပါ")
        return

    async with _SELFTEST_LOCK:
        await message.reply_text(
            "🧪 Phase 1 database self-test စနေပါပြီ…\n"
            "Synthetic data ပဲသုံးပြီး ပြီးရင် အလိုအလျောက် cleanup လုပ်ပါမယ်။"
        )
        try:
            results = await asyncio.wait_for(_run_selftest(), timeout=90)
            await message.reply_text(
                "🟢 JACC PHASE 1 DATABASE SELF-TEST — PASS\n\n"
                + "\n".join(results)
                + "\n\n🧹 Synthetic test data cleanup ပြီးပါပြီ။"
            )
        except asyncio.TimeoutError:
            await message.reply_text("🔴 Self-test timeout ဖြစ်ပါတယ် — logs စစ်ရန်လိုပါတယ်")
        except Exception as exc:
            _legacy.logger.exception("Phase 1 database self-test failed")
            await message.reply_text(
                "🔴 JACC PHASE 1 DATABASE SELF-TEST — FAILED\n\n"
                f"{str(exc)[:900]}\n\n"
                "🧹 Synthetic data cleanup ကို run လုပ်ထားပါတယ်။"
            )


async def brokers_selftest_router(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/phase1selftest":
        await phase1selftest_cmd(update, context)
        return
    await _health.brokers_health_router(update, context)


def _command_handler_with_selftest(command, callback, *args, **kwargs):
    if command == "brokers":
        return _existing_command_handler(
            [
                "brokers",
                "brokerfree",
                "brokerbusy",
                "queue",
                "phase1check",
                "phase1selftest",
            ],
            brokers_selftest_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def admin_cmd(update, context):
    await _original_admin_cmd(update, context)
    await update.effective_message.reply_text(
        "🧪 /phase1selftest — Database concurrency/capacity/expiry self-test"
    )


async def _set_my_commands_with_selftest(self, commands, *args, **kwargs):
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    existing = {getattr(item, "command", "") for item in patched}
    if is_admin_scope and "phase1selftest" not in existing:
        patched.append(
            _legacy.BotCommand(
                "phase1selftest",
                "🧪 Phase 1 Database Self-test",
            )
        )
    return await _existing_set_my_commands(self, patched, *args, **kwargs)


_legacy.CommandHandler = _command_handler_with_selftest
_queue.admin_cmd = admin_cmd
ExtBot.set_my_commands = _set_my_commands_with_selftest
