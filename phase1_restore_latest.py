"""Phone-friendly restore verification for the JACC Phase 1 backup flow.

The original restore command requires replying to the ZIP message. This patch
stores the Telegram file_id of each new encrypted backup in backup evidence and
lets admins run `/restoreverify PASSWORD` without replying to the document.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import phase1_healthcheck as _health
from telegram.ext import ExtBot


_original_backupdb_cmd = _health.backupdb_cmd
_original_restoreverify_cmd = _health.restoreverify_cmd
_original_send_document = ExtBot.send_document
_captured_backup_file_ids: dict[int, str] = {}


async def _send_document_with_backup_capture(self, *args, **kwargs):
    sent = await _original_send_document(self, *args, **kwargs)
    filename = str(kwargs.get("filename") or "")
    document_arg = kwargs.get("document")
    if not filename:
        filename = str(getattr(document_arg, "name", "") or "")

    sent_document = getattr(sent, "document", None)
    chat_id = kwargs.get("chat_id")
    if (
        filename.startswith("JACC_Phase1_Backup_")
        and sent_document is not None
        and chat_id is not None
    ):
        try:
            _captured_backup_file_ids[int(chat_id)] = str(sent_document.file_id)
        except (TypeError, ValueError):
            pass
    return sent


async def _persist_latest_file_id(user_id: int, file_id: str) -> bool:
    rows = await _health._get_rows(
        "jacc_backup_runs",
        select="id,metadata,status,started_at",
        params={
            "status": "in.(succeeded,verified)",
            "order": "started_at.desc",
        },
        limit=1,
    )
    if not rows:
        return False

    row = rows[0]
    metadata = dict(row.get("metadata") or {})
    metadata.update(
        {
            "telegram_file_id": file_id,
            "restore_without_reply": True,
            "backup_owner_telegram_user_id": user_id,
        }
    )
    await _health._patch_rows(
        "jacc_backup_runs",
        params={"id": f"eq.{row['id']}"},
        values={"metadata": metadata},
    )
    return True


async def backupdb_cmd(update, context):
    user_id = int(update.effective_user.id)
    _captured_backup_file_ids.pop(user_id, None)
    await _original_backupdb_cmd(update, context)

    file_id = _captured_backup_file_ids.pop(user_id, "")
    if not file_id:
        return

    try:
        saved = await _persist_latest_file_id(user_id, file_id)
        if saved:
            await update.effective_message.reply_text(
                "✅ Backup file reference သိမ်းပြီးပါပြီ။\n\n"
                "အခုကစပြီး ZIP ကို Reply မလုပ်ဘဲ—\n"
                "/restoreverify PASSWORD\n"
                "ပို့နိုင်ပါတယ်။"
            )
    except Exception:
        _health._legacy.logger.exception(
            "Could not persist latest Phase 1 backup Telegram file_id"
        )


async def _latest_backup_file_id(user_id: int) -> str:
    rows = await _health._get_rows(
        "jacc_backup_runs",
        select="id,metadata,status,started_at",
        params={
            "status": "in.(succeeded,verified)",
            "order": "started_at.desc",
        },
        limit=1,
    )
    if not rows:
        return ""

    metadata: dict[str, Any] = dict(rows[0].get("metadata") or {})
    owner = metadata.get("backup_owner_telegram_user_id")
    try:
        if owner is not None and int(owner) != user_id:
            return ""
    except (TypeError, ValueError):
        return ""
    return str(metadata.get("telegram_file_id") or "").strip()


class _MessageProxy:
    def __init__(self, real_message, file_id: str):
        self._real_message = real_message
        self.reply_to_message = SimpleNamespace(
            document=SimpleNamespace(file_id=file_id)
        )

    async def reply_text(self, *args, **kwargs):
        return await self._real_message.reply_text(*args, **kwargs)


async def restoreverify_cmd(update, context):
    message = update.effective_message
    reply = message.reply_to_message
    if getattr(reply, "document", None) is not None:
        await _original_restoreverify_cmd(update, context)
        return

    if not context.args:
        await message.reply_text("❌ Password ထည့်ရန်လိုပါတယ်")
        return

    user_id = int(update.effective_user.id)
    try:
        file_id = await _latest_backup_file_id(user_id)
    except Exception:
        _health._legacy.logger.exception("Latest backup lookup failed")
        await message.reply_text("❌ နောက်ဆုံး Backup ကိုရှာမရပါ")
        return

    if not file_id:
        await message.reply_text(
            "⚠️ လက်ရှိ Backup ဟောင်းမှာ auto file reference မပါသေးပါ။\n\n"
            "/backupdb ကို တစ်ကြိမ်ပြန်လုပ်ပြီး Password အသစ်နဲ့—\n"
            "/restoreverify PASSWORD\n"
            "ပို့ပါ။ ZIP ကို Reply လုပ်စရာမလိုတော့ပါ။"
        )
        return

    proxy_update = SimpleNamespace(
        effective_message=_MessageProxy(message, file_id),
        effective_user=update.effective_user,
    )
    await _original_restoreverify_cmd(proxy_update, context)


ExtBot.send_document = _send_document_with_backup_capture
_health.backupdb_cmd = backupdb_cmd
_health.restoreverify_cmd = restoreverify_cmd

# Load after health/backup command patches so the self-test extends the final chain.
import phase1_selftest as _phase1_selftest  # noqa: F401,E402

# Keep legacy broker commands synchronized with the Phase 1 broker registry.
import phase1_broker_sync as _phase1_broker_sync  # noqa: F401,E402
