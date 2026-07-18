"""JACC Phase 3 website-payment Telegram callback handler.

This module handles the Approve / Reject inline buttons sent by the
Google Apps Script payment workflow.  It deliberately keeps payment
state and member activation in Apps Script; the Telegram bot only
forwards the admin decision to SHEET_WEBHOOK.
"""

import logging
from typing import Any

import httpx
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_phase3_payment_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    sheet_webhook: str,
    admin_ids: list[int],
) -> bool:
    """Handle webpay_approve_/webpay_reject_ callbacks.

    Returns True when the callback belongs to Phase 3, including error
    cases, so the caller can stop processing it in the normal callback
    router. Returns False for unrelated callback data.
    """

    query = update.callback_query
    if query is None:
        return False

    data = str(query.data or "")
    approve_prefix = "webpay_approve_"
    reject_prefix = "webpay_reject_"

    if not (data.startswith(approve_prefix) or data.startswith(reject_prefix)):
        return False

    admin_id = int(query.from_user.id)
    if admin_id not in admin_ids:
        await query.answer("❌ Admin သာ အသုံးပြုနိုင်ပါတယ်", show_alert=True)
        return True

    if not sheet_webhook:
        await query.answer("❌ SHEET_WEBHOOK မသတ်မှတ်ရသေးပါ", show_alert=True)
        return True

    is_approve = data.startswith(approve_prefix)
    payment_id = data[len(approve_prefix if is_approve else reject_prefix):].strip()

    if not payment_id:
        await query.answer("❌ Payment ID မတွေ့ပါ", show_alert=True)
        return True

    await query.answer("စစ်ဆေးနေပါတယ်…")

    payload: dict[str, Any] = {
        "action": "approveWebPayment" if is_approve else "rejectWebPayment",
        "paymentId": payment_id,
        "adminId": str(admin_id),
    }
    if not is_approve:
        payload["reason"] = "Payment slip could not be verified by admin"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            response = await client.post(sheet_webhook, json=payload)
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        logger.exception("Phase 3 payment callback failed: %s", exc)
        await query.edit_message_text(
            "❌ Payment server ကို ဆက်သွယ်မရပါ။\n\n"
            f"Payment ID: `{payment_id}`\n"
            "ခဏနောက် ပြန်နှိပ်ပါ။",
            parse_mode="Markdown",
        )
        return True

    if not result.get("ok"):
        error = str(result.get("error") or result.get("message") or "UNKNOWN_ERROR")
        await query.edit_message_text(
            "❌ Payment action မအောင်မြင်ပါ။\n\n"
            f"Payment ID: `{payment_id}`\n"
            f"Error: `{error}`",
            parse_mode="Markdown",
        )
        return True

    if is_approve:
        package_name = str(result.get("package") or "-")
        months = result.get("months") or "-"
        already = "\nℹ️ အရင်က Approve လုပ်ပြီးသားပါ။" if result.get("alreadyApproved") else ""
        await query.edit_message_text(
            "✅ *Website Payment Approved*\n\n"
            f"🆔 `{payment_id}`\n"
            f"📦 Package: *{package_name}*\n"
            f"📅 Duration: *{months} month(s)*"
            f"{already}",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            "❌ *Website Payment Rejected*\n\n"
            f"🆔 `{payment_id}`\n"
            "Customer ကို Telegram မှ အကြောင်းကြားပြီးပါပြီ။",
            parse_mode="Markdown",
        )

    return True
