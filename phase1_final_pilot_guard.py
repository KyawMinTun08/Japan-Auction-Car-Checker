"""Migration-aware wrapper for the JACC Phase 1 final pilot.

The first production pilot exposed an older deployed Supabase function with
ambiguous ``request_id`` references. This wrapper keeps the pilot safe and
returns a phone-friendly migration instruction instead of a raw PostgreSQL
error until migration 008 is applied.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import phase1_final_pilot as _pilot


async def phase1finalpilot_cmd(update, context):
    message = update.effective_message
    user = update.effective_user

    if not _pilot._legacy.ADMIN_IDS or int(user.id) not in _pilot._legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return
    if _pilot._FINAL_PILOT_LOCK.locked():
        await message.reply_text("⏳ Final pilot တစ်ခု လည်နေပြီးသားပါ")
        return

    async with _pilot._FINAL_PILOT_LOCK:
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
                _pilot._run_isolated_restart_recovery(token), timeout=90
            )
            ten_request_result = await asyncio.wait_for(
                _pilot._run_ten_request_live_pilot(token), timeout=150
            )
            await message.reply_text(
                "🟢 JACC PHASE 1 FINAL PILOT — PASS\n\n"
                f"{restart_result}\n"
                f"{ten_request_result}\n\n"
                "🧹 Synthetic test data cleanup ပြီးပါပြီ။"
            )
        except asyncio.TimeoutError:
            _pilot._legacy.logger.exception("Phase 1 final pilot timed out")
            await message.reply_text(
                "🔴 JACC PHASE 1 FINAL PILOT — TIMEOUT\n\n"
                "Cleanup ကို run လုပ်ထားပါတယ်။ Logs စစ်ရန်လိုပါတယ်။"
            )
        except Exception as exc:
            _pilot._legacy.logger.exception("Phase 1 final pilot failed")
            error_text = str(exc)
            lowered = error_text.lower()
            migration_missing = (
                "42702" in error_text
                or "request_id" in lowered and "ambiguous" in lowered
            )
            if migration_missing:
                await message.reply_text(
                    "🟡 JACC PHASE 1 FINAL PILOT — MIGRATION REQUIRED\n\n"
                    "Production Supabase မှာ migration 008 မတင်ရသေးပါ။\n\n"
                    "Laptop ရောက်ရင် SQL Editor မှာ—\n"
                    "phase1/sql/008_fix_dispatch_offer_ambiguity.sql\n"
                    "ကို Run လုပ်ပြီး /phase1finalpilot ပြန်ပို့ပါ။\n\n"
                    "🧹 Synthetic cleanup ကို run လုပ်ထားပါတယ်။"
                )
                return

            await message.reply_text(
                "🔴 JACC PHASE 1 FINAL PILOT — FAILED\n\n"
                f"{error_text[:900]}\n\n"
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
    await _pilot._resilience.brokers_resilience_router(update, context)


# The CommandHandler patch in phase1_final_pilot resolves this module global
# later when legacy_bot.main registers handlers.
_pilot.phase1finalpilot_cmd = phase1finalpilot_cmd
_pilot.brokers_final_pilot_router = brokers_final_pilot_router
