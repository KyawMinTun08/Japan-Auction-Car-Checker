"""JACC production launcher with an admin Phase 1 queue command.

Extends ``completion_launcher`` and adds:

    /queue

The command lists the oldest/highest-priority requests that are waiting for a
broker or currently have an outstanding broker offer.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

import completion_launcher as _completion


_legacy = _completion._legacy
_existing_command_handler = _legacy.CommandHandler
_original_brokers_cmd = _legacy.brokers_cmd


def _command_handler_with_queue(command, callback, *args, **kwargs):
    """Register /queue beside the existing broker admin command aliases."""
    if command == "brokers":
        command = ["brokers", "brokerfree", "brokerbusy", "queue"]
    return _existing_command_handler(command, callback, *args, **kwargs)


async def _load_phase1_queue(limit: int = 20) -> list[dict[str, Any]]:
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{_legacy.phase1._base_url}/rest/v1/jacc_service_requests"
    params = {
        "status": "in.(waiting_broker,offered)",
        "select": (
            "request_code,status,service_type,priority,created_at,form_data"
        ),
        "order": "priority.desc,created_at.asc",
        "limit": str(limit),
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
            "Phase 1 queue lookup failed "
            f"({response.status_code}): {response.text[:500]}"
        )
    return list(response.json() or [])


def _queue_text(rows: list[dict[str, Any]]) -> str:
    waiting_count = sum(1 for row in rows if row.get("status") == "waiting_broker")
    offered_count = sum(1 for row in rows if row.get("status") == "offered")
    lines = [
        "📋 JACC REQUEST QUEUE",
        "",
        f"⏳ Waiting: {waiting_count}",
        f"📨 Offer sent: {offered_count}",
        f"📊 Showing: {len(rows)}",
        "",
    ]

    for index, row in enumerate(rows, start=1):
        form_data = dict(row.get("form_data") or {})
        service = "AUCTION" if row.get("service_type") == "auction" else "OUTSIDE"
        status = "WAITING" if row.get("status") == "waiting_broker" else "OFFER SENT"
        car_name = str(form_data.get("car_name") or "-")[:60]
        username = str(form_data.get("username") or "-")[:40]
        priority = row.get("priority", 0)
        created_at = str(row.get("created_at") or "").replace("T", " ")[:16]
        lines.extend(
            [
                f"{index}. {row.get('request_code', '-')} | {service} | {status} | P{priority}",
                f"   🚗 {car_name}",
                f"   👤 {username} | 🕒 {created_at}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


async def brokers_admin_cmd(update, context):
    """Keep existing broker commands and serve the admin-only /queue view."""
    message = update.effective_message
    command = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()

    if command != "/queue":
        await _original_brokers_cmd(update, context)
        return

    user = update.effective_user
    if not _legacy.ADMIN_IDS or user.id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    try:
        rows = await _load_phase1_queue()
    except _legacy.JaccPhase1Error as exc:
        _legacy.logger.warning("Phase 1 /queue unavailable: %s", exc)
        await message.reply_text("❌ Queue data မရသေးပါ — ခဏပြန်စမ်းပါ")
        return
    except Exception:
        _legacy.logger.exception("Phase 1 /queue failed")
        await message.reply_text("❌ Queue စစ်ဆေးမှု မအောင်မြင်ပါ")
        return

    if not rows:
        await message.reply_text("✅ Queue ထဲမှာ စောင့်နေတဲ့ Request မရှိပါ")
        return

    await message.reply_text(_queue_text(rows))


# ``legacy_bot.main`` resolves these globals when registering handlers.
_legacy.CommandHandler = _command_handler_with_queue
_legacy.brokers_cmd = brokers_admin_cmd


async def main() -> None:
    await _completion.main()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _legacy.logger.error("FATAL CRASH: %s", exc)
        _legacy.logger.error(traceback.format_exc())
        raise
