"""Admin-only production health command for JACC Phase 1.

Imported by ``phase1_production_launcher.py`` after the existing runtime patches
and before ``legacy_bot.main`` registers handlers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

import queue_launcher as _queue
from telegram.ext import ExtBot


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_existing_set_my_commands = ExtBot.set_my_commands
_original_admin_cmd = _queue.admin_cmd


async def _get_rows(
    table: str,
    *,
    select: str,
    params: dict[str, str] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    query = dict(params or {})
    query.update({"select": select, "limit": str(limit)})
    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    async with _legacy.httpx.AsyncClient(
        timeout=_legacy.phase1._timeout
    ) as client:
        response = await client.get(
            url,
            headers=_legacy.phase1._headers,
            params=query,
        )

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Health lookup failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )
    return list(response.json() or [])


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _age_label(value: Any) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "မရှိသေး"
    seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


async def _health_snapshot() -> dict[str, Any]:
    requests = await _get_rows(
        "jacc_service_requests",
        select="id,status,request_code,updated_at",
        params={
            "status": (
                "in.(submitted,waiting_broker,offered,assigned,consulting,"
                "searching,car_found,waiting_customer,waiting_payment,"
                "payment_verifying,payment_confirmed,price_approval,"
                "auction_pending,negotiating,inspection_pending,reserved,"
                "purchased,paused,reassigned,disputed)"
            )
        },
    )
    offers = await _get_rows(
        "jacc_request_offers",
        select="id,status,expires_at",
        params={"status": "eq.pending"},
    )
    outbox = await _get_rows(
        "jacc_message_outbox",
        select="id,status,locked_at,attempt_count,max_attempts,available_at",
        params={
            "status": "in.(queued,processing,failed,retrying,dead_letter)"
        },
    )
    brokers = await _get_rows(
        "jacc_broker_profiles",
        select="user_id,account_status,accepting_requests,broker_code",
    )
    backups = await _get_rows(
        "jacc_backup_runs",
        select="id,status,started_at,completed_at,backup_type",
        params={"order": "started_at.desc"},
        limit=1,
    )
    restores = await _get_rows(
        "jacc_restore_tests",
        select="id,status,started_at,completed_at,environment",
        params={"order": "started_at.desc"},
        limit=1,
    )

    request_counts = Counter(str(row.get("status") or "unknown") for row in requests)
    outbox_counts = Counter(str(row.get("status") or "unknown") for row in outbox)
    now = datetime.now(timezone.utc)
    stuck_processing = 0
    for row in outbox:
        if row.get("status") != "processing":
            continue
        locked_at = _parse_time(row.get("locked_at"))
        if locked_at and (now - locked_at).total_seconds() > 600:
            stuck_processing += 1

    accepting_brokers = sum(
        1
        for row in brokers
        if bool(row.get("accepting_requests"))
        and str(row.get("account_status") or "active") == "active"
    )

    problems: list[str] = []
    warnings: list[str] = []
    if outbox_counts.get("dead_letter", 0):
        problems.append("Dead-letter message ရှိ")
    if stuck_processing:
        problems.append("Outbox processing lock 10m ကျော်ရှိ")
    if not brokers:
        problems.append("Supabase Broker profile မရှိ")
    elif accepting_brokers == 0:
        warnings.append("Available Broker မရှိ")
    if outbox_counts.get("retrying", 0) or outbox_counts.get("failed", 0):
        warnings.append("Retry စောင့်နေတဲ့ message ရှိ")
    if not backups:
        warnings.append("Backup evidence မရှိသေး")
    if not restores:
        warnings.append("Restore test evidence မရှိသေး")

    state = "RED" if problems else ("YELLOW" if warnings else "GREEN")
    return {
        "state": state,
        "problems": problems,
        "warnings": warnings,
        "request_counts": request_counts,
        "pending_offers": len(offers),
        "outbox_counts": outbox_counts,
        "stuck_processing": stuck_processing,
        "brokers_total": len(brokers),
        "accepting_brokers": accepting_brokers,
        "latest_backup": backups[0] if backups else None,
        "latest_restore": restores[0] if restores else None,
    }


async def phase1check_cmd(update, context):
    message = update.effective_message
    user_id = int(update.effective_user.id)
    if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    try:
        snapshot = await _health_snapshot()
    except Exception as exc:
        _legacy.logger.exception("Phase 1 health check failed")
        await message.reply_text(
            "🔴 Phase 1 Health Check မအောင်မြင်ပါ\n\n"
            f"Error: {str(exc)[:500]}"
        )
        return

    icons = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
    requests = snapshot["request_counts"]
    outbox = snapshot["outbox_counts"]
    backup = snapshot["latest_backup"]
    restore = snapshot["latest_restore"]

    lines = [
        f"{icons[snapshot['state']]} JACC PHASE 1 HEALTH — {snapshot['state']}",
        "",
        "📋 Active Requests",
        f"• Waiting: {requests.get('waiting_broker', 0)}",
        f"• Offered: {requests.get('offered', 0)}",
        f"• Assigned/Working: {sum(requests.get(name, 0) for name in ('assigned', 'consulting', 'searching', 'car_found', 'waiting_customer', 'waiting_payment', 'payment_verifying', 'payment_confirmed', 'price_approval', 'auction_pending', 'negotiating', 'inspection_pending', 'reserved', 'purchased', 'paused', 'reassigned', 'disputed'))}",
        f"• Pending offers: {snapshot['pending_offers']}",
        "",
        "👷 Brokers",
        f"• Total: {snapshot['brokers_total']}",
        f"• Available: {snapshot['accepting_brokers']}",
        "",
        "📨 Message Outbox",
        f"• Queued: {outbox.get('queued', 0)}",
        f"• Retrying/Failed: {outbox.get('retrying', 0) + outbox.get('failed', 0)}",
        f"• Processing: {outbox.get('processing', 0)}",
        f"• Stuck >10m: {snapshot['stuck_processing']}",
        f"• Dead letter: {outbox.get('dead_letter', 0)}",
        "",
        "💾 Recovery Evidence",
        (
            f"• Backup: {backup.get('status')} ({_age_label(backup.get('completed_at') or backup.get('started_at'))})"
            if backup
            else "• Backup: မရှိသေး"
        ),
        (
            f"• Restore test: {restore.get('status')} ({_age_label(restore.get('completed_at') or restore.get('started_at'))})"
            if restore
            else "• Restore test: မရှိသေး"
        ),
    ]

    if snapshot["problems"]:
        lines.extend(["", "🚨 Problems"])
        lines.extend(f"• {item}" for item in snapshot["problems"])
    if snapshot["warnings"]:
        lines.extend(["", "⚠️ Warnings"])
        lines.extend(f"• {item}" for item in snapshot["warnings"])

    await message.reply_text("\n".join(lines))


async def brokers_health_router(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/phase1check":
        await phase1check_cmd(update, context)
        return
    await _queue.brokers_admin_cmd(update, context)


def _command_handler_with_health(command, callback, *args, **kwargs):
    if command == "brokers":
        return _existing_command_handler(
            ["brokers", "brokerfree", "brokerbusy", "queue", "phase1check"],
            brokers_health_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def admin_cmd(update, context):
    await _original_admin_cmd(update, context)
    await update.effective_message.reply_text(
        "🩺 /phase1check — Phase 1 Health စစ်ရန်"
    )


async def _set_my_commands_with_health(self, commands, *args, **kwargs):
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    existing = {getattr(item, "command", "") for item in patched}
    if is_admin_scope and "phase1check" not in existing:
        patched.append(
            _legacy.BotCommand("phase1check", "🩺 Phase 1 Health စစ်ရန်")
        )
    return await _existing_set_my_commands(self, patched, *args, **kwargs)


_legacy.CommandHandler = _command_handler_with_health
_queue.admin_cmd = admin_cmd
ExtBot.set_my_commands = _set_my_commands_with_health
