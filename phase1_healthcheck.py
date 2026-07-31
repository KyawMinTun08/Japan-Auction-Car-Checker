"""Admin health, logical backup, and restore verification for JACC Phase 1.

Railway starts ``queue_launcher.py`` directly. That launcher imports this module
before ``legacy_bot.main`` registers handlers, so the command bridges below are
part of the active production runtime.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO
import hashlib
import json
import secrets
import string
from typing import Any

import pyzipper
import queue_launcher as _queue
from telegram.ext import ExtBot


_legacy = _queue._legacy
_existing_command_handler = _legacy.CommandHandler
_existing_set_my_commands = ExtBot.set_my_commands
_original_admin_cmd = _queue.admin_cmd
_original_backup_cmd = _legacy.backup_cmd

_BACKUP_FORMAT = "jacc-phase1-logical-backup-v1"
_BACKUP_TABLES = (
    "jacc_profiles",
    "jacc_memberships",
    "jacc_broker_profiles",
    "jacc_service_requests",
    "jacc_request_offers",
    "jacc_request_assignments",
    "jacc_request_updates",
    "jacc_request_status_history",
    "jacc_audit_logs",
    "jacc_message_outbox",
    "jacc_delivery_attempts",
)


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
        timeout=max(30.0, _legacy.phase1._timeout)
    ) as client:
        response = await client.get(
            url,
            headers=_legacy.phase1._headers,
            params=query,
        )

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Lookup failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )
    return list(response.json() or [])


async def _get_all_rows(table: str, *, batch_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = await _get_rows(
            table,
            select="*",
            params={"offset": str(offset)},
            limit=batch_size,
        )
        rows.extend(batch)
        if len(batch) < batch_size:
            return rows
        offset += batch_size


async def _post_row(table: str, values: dict[str, Any]) -> dict[str, Any] | None:
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    headers = {**_legacy.phase1._headers, "Prefer": "return=representation"}
    async with _legacy.httpx.AsyncClient(
        timeout=max(30.0, _legacy.phase1._timeout)
    ) as client:
        response = await client.post(url, headers=headers, json=values)

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Insert failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )
    data = response.json() if response.content else []
    return data[0] if isinstance(data, list) and data else None


async def _patch_rows(
    table: str,
    *,
    params: dict[str, str],
    values: dict[str, Any],
) -> None:
    if _legacy.phase1 is None:
        raise _legacy.JaccPhase1Error("PHASE1_NOT_CONFIGURED")

    url = f"{_legacy.phase1._base_url}/rest/v1/{table}"
    headers = {**_legacy.phase1._headers, "Prefer": "return=minimal"}
    async with _legacy.httpx.AsyncClient(
        timeout=max(30.0, _legacy.phase1._timeout)
    ) as client:
        response = await client.patch(
            url,
            headers=headers,
            params=params,
            json=values,
        )

    if response.is_error:
        raise _legacy.JaccPhase1Error(
            f"Update failed for {table} "
            f"({response.status_code}): {response.text[:500]}"
        )


async def _profile_id_for_telegram(telegram_user_id: int) -> str | None:
    try:
        rows = await _get_rows(
            "jacc_profiles",
            select="id",
            params={"telegram_user_id": f"eq.{telegram_user_id}"},
            limit=1,
        )
    except Exception:
        return None
    return str(rows[0]["id"]) if rows else None


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
        params={"status": "in.(queued,processing,failed,retrying,dead_letter)"},
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
        and str(row.get("account_status") or "active") in {"active", "probation"}
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
    working_statuses = (
        "assigned", "consulting", "searching", "car_found",
        "waiting_customer", "waiting_payment", "payment_verifying",
        "payment_confirmed", "price_approval", "auction_pending",
        "negotiating", "inspection_pending", "reserved", "purchased",
        "paused", "reassigned", "disputed",
    )

    lines = [
        f"{icons[snapshot['state']]} JACC PHASE 1 HEALTH — {snapshot['state']}",
        "",
        "📋 Active Requests",
        f"• Waiting: {requests.get('waiting_broker', 0)}",
        f"• Offered: {requests.get('offered', 0)}",
        f"• Assigned/Working: {sum(requests.get(name, 0) for name in working_statuses)}",
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
            f"• Backup: {backup.get('status')} "
            f"({_age_label(backup.get('completed_at') or backup.get('started_at'))})"
            if backup else "• Backup: မရှိသေး"
        ),
        (
            f"• Restore test: {restore.get('status')} "
            f"({_age_label(restore.get('completed_at') or restore.get('started_at'))})"
            if restore else "• Restore test: မရှိသေး"
        ),
    ]

    if snapshot["problems"]:
        lines.extend(["", "🚨 Problems"])
        lines.extend(f"• {item}" for item in snapshot["problems"])
    if snapshot["warnings"]:
        lines.extend(["", "⚠️ Warnings"])
        lines.extend(f"• {item}" for item in snapshot["warnings"])

    await message.reply_text("\n".join(lines))


def _backup_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(22))


async def _build_backup_payload(admin_user_id: int) -> tuple[dict[str, Any], dict[str, int]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for table in _BACKUP_TABLES:
        rows = await _get_all_rows(table)
        tables[table] = rows
        counts[table] = len(rows)

    payload = {
        "format": _BACKUP_FORMAT,
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by_telegram_user_id": admin_user_id,
        "source": "Supabase REST service-role logical export",
        "table_counts": counts,
        "tables": tables,
    }
    return payload, counts


async def backupdb_cmd(update, context):
    message = update.effective_message
    user_id = int(update.effective_user.id)
    if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    await message.reply_text(
        "⏳ Phase 1 Supabase data ကို Export လုပ်နေပါတယ်...\n"
        "ပြီးသွားရင် AES-256 ZIP file နဲ့ Password သီးခြားပို့ပါမယ်။"
    )

    started_at = datetime.now(timezone.utc)
    try:
        payload, counts = await _build_backup_payload(user_id)
        json_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        timestamp = started_at.strftime("%Y%m%d_%H%M%S")
        json_name = f"jacc_phase1_{timestamp}.json"
        zip_name = f"JACC_Phase1_Backup_{timestamp}.zip"
        password = _backup_password()

        archive = BytesIO()
        with pyzipper.AESZipFile(
            archive,
            mode="w",
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES,
        ) as zipped:
            zipped.setpassword(password.encode("utf-8"))
            zipped.setencryption(pyzipper.WZ_AES, nbits=256)
            zipped.writestr(json_name, json_bytes)

        archive_bytes = archive.getvalue()
        checksum = hashlib.sha256(archive_bytes).hexdigest()
        total_rows = sum(counts.values())

        upload = BytesIO(archive_bytes)
        upload.name = zip_name
        sent = await context.bot.send_document(
            chat_id=user_id,
            document=upload,
            filename=zip_name,
            caption=(
                "✅ JACC Phase 1 Logical Backup\n"
                f"📊 Tables: {len(counts)} | Rows: {total_rows}\n"
                f"📦 Size: {len(archive_bytes):,} bytes\n"
                f"🔎 SHA-256: {checksum[:16]}…"
            ),
        )

        admin_profile_id = await _profile_id_for_telegram(user_id)
        completed_at = datetime.now(timezone.utc)
        backup_row = await _post_row(
            "jacc_backup_runs",
            {
                "backup_type": "database_export",
                "status": "succeeded",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "storage_location": (
                    f"telegram://chat/{user_id}/message/{sent.message_id}"
                ),
                "checksum_sha256": checksum,
                "size_bytes": len(archive_bytes),
                "retention_until": (completed_at + timedelta(days=30)).isoformat(),
                "metadata": {
                    "format": _BACKUP_FORMAT,
                    "archive": "AES-256 ZIP",
                    "table_counts": counts,
                    "supabase_managed_backup": False,
                    "temporary_free_plan_strategy": True,
                },
                "created_by": admin_profile_id,
            },
        )

        await message.reply_text(
            "🔐 Backup Password ကို နောက် message မှာ သီးခြားပို့ထားပါတယ်။\n\n"
            "ဒီ Password မရှိရင် ZIP ကိုဖွင့်မရပါ။ Backup file နဲ့ Password ကို "
            "တစ်နေရာတည်းမသိမ်းပါနဲ့။"
        )
        await context.bot.send_message(chat_id=user_id, text=password)
        await message.reply_text(
            "✅ Backup evidence မှတ်တမ်းတင်ပြီးပါပြီ။\n\n"
            f"Evidence ID: {backup_row.get('id') if backup_row else '-'}\n"
            "Restore စစ်ရန် Backup file ကို Reply လုပ်ပြီး—\n"
            "`/restoreverify PASSWORD`\n"
            "ပို့ပါ။",
            parse_mode="Markdown",
        )
    except Exception as exc:
        _legacy.logger.exception("Phase 1 logical backup failed")
        await message.reply_text(
            "❌ Phase 1 Backup မအောင်မြင်ပါ\n\n"
            f"Error: {str(exc)[:700]}"
        )


def _validate_backup_payload(payload: Any) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    if not isinstance(payload, dict):
        return ["Backup root က JSON object မဟုတ်ပါ"], counts
    if payload.get("format") != _BACKUP_FORMAT:
        errors.append("Backup format/version မမှန်ပါ")

    tables = payload.get("tables")
    declared = payload.get("table_counts")
    if not isinstance(tables, dict):
        return errors + ["tables object မရှိပါ"], counts
    if not isinstance(declared, dict):
        errors.append("table_counts object မရှိပါ")
        declared = {}

    for table in _BACKUP_TABLES:
        rows = tables.get(table)
        if not isinstance(rows, list):
            errors.append(f"{table}: row list မရှိပါ")
            continue
        counts[table] = len(rows)
        if declared.get(table) != len(rows):
            errors.append(f"{table}: declared count မကိုက်ပါ")

    profiles = {
        str(row.get("id"))
        for row in tables.get("jacc_profiles", [])
        if row.get("id") is not None
    }
    brokers = {
        str(row.get("user_id"))
        for row in tables.get("jacc_broker_profiles", [])
        if row.get("user_id") is not None
    }
    requests = {
        str(row.get("id"))
        for row in tables.get("jacc_service_requests", [])
        if row.get("id") is not None
    }

    request_codes = [
        str(row.get("request_code"))
        for row in tables.get("jacc_service_requests", [])
        if row.get("request_code") is not None
    ]
    if len(request_codes) != len(set(request_codes)):
        errors.append("jacc_service_requests: duplicate request_code ရှိ")

    for row in tables.get("jacc_memberships", []):
        if str(row.get("user_id")) not in profiles:
            errors.append("jacc_memberships: profile reference ပျက်")
            break
    for row in tables.get("jacc_broker_profiles", []):
        if str(row.get("user_id")) not in profiles:
            errors.append("jacc_broker_profiles: profile reference ပျက်")
            break
    for row in tables.get("jacc_service_requests", []):
        if str(row.get("customer_id")) not in profiles:
            errors.append("jacc_service_requests: customer reference ပျက်")
            break
        assigned = row.get("assigned_broker_id")
        if assigned is not None and str(assigned) not in brokers:
            errors.append("jacc_service_requests: assigned broker reference ပျက်")
            break
    for table in ("jacc_request_offers", "jacc_request_assignments"):
        for row in tables.get(table, []):
            if str(row.get("request_id")) not in requests:
                errors.append(f"{table}: request reference ပျက်")
                break
            if str(row.get("broker_id")) not in brokers:
                errors.append(f"{table}: broker reference ပျက်")
                break
    for row in tables.get("jacc_request_updates", []):
        if str(row.get("request_id")) not in requests:
            errors.append("jacc_request_updates: request reference ပျက်")
            break
        if str(row.get("actor_id")) not in profiles:
            errors.append("jacc_request_updates: actor reference ပျက်")
            break
    for row in tables.get("jacc_request_status_history", []):
        if str(row.get("request_id")) not in requests:
            errors.append("jacc_request_status_history: request reference ပျက်")
            break
        changed_by = row.get("changed_by")
        if changed_by is not None and str(changed_by) not in profiles:
            errors.append("jacc_request_status_history: actor reference ပျက်")
            break

    return errors, counts


async def restoreverify_cmd(update, context):
    message = update.effective_message
    user_id = int(update.effective_user.id)
    if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS:
        await message.reply_text("❌ Admin သာ သုံးနိုင်ပါတယ်")
        return

    reply = message.reply_to_message
    document = getattr(reply, "document", None) if reply else None
    if document is None:
        await message.reply_text(
            "❌ Backup ZIP file ကို Reply လုပ်ပြီး—\n"
            "`/restoreverify PASSWORD`\n"
            "ပို့ပါ။",
            parse_mode="Markdown",
        )
        return
    if not context.args:
        await message.reply_text("❌ Password ထည့်ရန်လိုပါတယ်")
        return

    password = " ".join(context.args).strip()
    started_at = datetime.now(timezone.utc)
    await message.reply_text("⏳ Backup file ကို decrypt/verify လုပ်နေပါတယ်...")

    try:
        telegram_file = await context.bot.get_file(document.file_id)
        file_bytes = bytes(await telegram_file.download_as_bytearray())
        checksum = hashlib.sha256(file_bytes).hexdigest()

        archive = BytesIO(file_bytes)
        with pyzipper.AESZipFile(archive, mode="r") as zipped:
            zipped.setpassword(password.encode("utf-8"))
            names = [name for name in zipped.namelist() if name.endswith(".json")]
            if not names:
                raise ValueError("Backup JSON file မပါပါ")
            payload = json.loads(zipped.read(names[0]).decode("utf-8"))

        errors, counts = _validate_backup_payload(payload)
        backup_rows = await _get_rows(
            "jacc_backup_runs",
            select="id,status,checksum_sha256",
            params={"checksum_sha256": f"eq.{checksum}"},
            limit=1,
        )
        backup_run_id = str(backup_rows[0]["id"]) if backup_rows else None
        completed_at = datetime.now(timezone.utc)
        admin_profile_id = await _profile_id_for_telegram(user_id)

        status = "failed" if errors else "verified"
        notes = (
            "; ".join(errors[:20])
            if errors
            else (
                "AES archive decrypted; JSON parsed; declared row counts, "
                "request-code uniqueness and core foreign-key references verified. "
                "Logical file validation only; not a full restore into a separate database."
            )
        )
        restore_row = await _post_row(
            "jacc_restore_tests",
            {
                "backup_run_id": backup_run_id,
                "status": status,
                "environment": "logical-file-validation",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "requests_checked": counts.get("jacc_service_requests", 0),
                "messages_checked": counts.get("jacc_message_outbox", 0),
                "photos_checked": 0,
                "audit_rows_checked": counts.get("jacc_audit_logs", 0),
                "notes": notes,
                "performed_by": admin_profile_id,
            },
        )

        if not errors and backup_run_id:
            await _patch_rows(
                "jacc_backup_runs",
                params={"id": f"eq.{backup_run_id}"},
                values={"status": "verified"},
            )

        if errors:
            await message.reply_text(
                "🔴 Restore Verification မအောင်မြင်ပါ\n\n"
                + "\n".join(f"• {item}" for item in errors[:15])
            )
            return

        await message.reply_text(
            "✅ Logical Restore Verification အောင်မြင်ပါပြီ\n\n"
            f"📋 Requests checked: {counts.get('jacc_service_requests', 0)}\n"
            f"📨 Messages checked: {counts.get('jacc_message_outbox', 0)}\n"
            f"🧾 Audit rows checked: {counts.get('jacc_audit_logs', 0)}\n"
            f"🔎 SHA-256: {checksum[:16]}…\n"
            f"🧪 Evidence ID: {restore_row.get('id') if restore_row else '-'}\n\n"
            "⚠️ ဒီစစ်ဆေးမှုက encrypted backup file ကို ဖွင့်နိုင်ခြင်း၊ row counts နဲ့ "
            "references မှန်ခြင်းကိုစစ်တာပါ။ သီးခြား Database ထဲ Full Restore စမ်းတာမဟုတ်သေးပါ။"
        )
    except RuntimeError:
        await message.reply_text("❌ Password မှားနေပါတယ် သို့မဟုတ် ZIP file ပျက်နေပါတယ်")
    except Exception as exc:
        _legacy.logger.exception("Phase 1 restore verification failed")
        await message.reply_text(
            "❌ Restore Verification မအောင်မြင်ပါ\n\n"
            f"Error: {str(exc)[:700]}"
        )


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


async def backup_router(update, context):
    command = (
        (update.effective_message.text or "")
        .split(maxsplit=1)[0]
        .split("@", 1)[0]
        .lower()
    )
    if command == "/backupdb":
        await backupdb_cmd(update, context)
        return
    if command == "/restoreverify":
        await restoreverify_cmd(update, context)
        return
    await _original_backup_cmd(update, context)


def _command_handler_with_phase1_tools(command, callback, *args, **kwargs):
    if command == "brokers":
        return _existing_command_handler(
            ["brokers", "brokerfree", "brokerbusy", "queue", "phase1check"],
            brokers_health_router,
            *args,
            **kwargs,
        )
    if command == "backup":
        return _existing_command_handler(
            ["backup", "backupdb", "restoreverify"],
            backup_router,
            *args,
            **kwargs,
        )
    return _existing_command_handler(command, callback, *args, **kwargs)


async def admin_cmd(update, context):
    await _original_admin_cmd(update, context)
    await update.effective_message.reply_text(
        "🩺 /phase1check — Phase 1 Health စစ်ရန်\n"
        "🗄 /backupdb — Encrypted Supabase logical backup\n"
        "🧪 /restoreverify — Backup file verification"
    )


async def _set_my_commands_with_phase1_tools(self, commands, *args, **kwargs):
    scope = kwargs.get("scope")
    chat_id = getattr(scope, "chat_id", None)
    try:
        is_admin_scope = int(chat_id) in _legacy.ADMIN_IDS
    except (TypeError, ValueError):
        is_admin_scope = False

    patched = list(commands)
    existing = {getattr(item, "command", "") for item in patched}
    additions = (
        ("phase1check", "🩺 Phase 1 Health စစ်ရန်"),
        ("backupdb", "🗄 Supabase Backup ထုတ်ရန်"),
        ("restoreverify", "🧪 Backup စစ်ရန်"),
    )
    if is_admin_scope:
        for command, description in additions:
            if command not in existing:
                patched.append(_legacy.BotCommand(command, description))

    return await _existing_set_my_commands(self, patched, *args, **kwargs)


_legacy.CommandHandler = _command_handler_with_phase1_tools
_queue.admin_cmd = admin_cmd
ExtBot.set_my_commands = _set_my_commands_with_phase1_tools
