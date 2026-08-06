"""Telegram callback integration for retry-safe Phase 2 payment approval.

Install this module before ``legacy_bot.main()`` registers handlers. It handles
legacy ``slip_ok_`` approvals plus the Apps Script Phase 3
``webpay_approve_``/``webpay_reject_`` buttons. Every unrelated callback is
delegated to the unchanged legacy handler.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import phase2_membership_guard
from phase2 import payment_approval


_legacy: Any | None = None
_original_button_callback: Callable[..., Awaitable[Any]] | None = None
_PHASE3_APPROVE_PREFIX = "webpay_approve_"
_PHASE3_REJECT_PREFIX = "webpay_reject_"
_PHASE3_PAYMENT_ID = re.compile(r"^WP-[A-Z0-9-]{4,64}$", re.IGNORECASE)


def _runtime() -> Any:
    global _legacy
    if _legacy is None:
        import legacy_bot

        _legacy = legacy_bot
    return _legacy


def _approval_error_message(code: str) -> str:
    messages = {
        "payment_session_missing": (
            "❌ Payment data မတွေ့တော့ပါ။ Customer ကို approve မလုပ်ရသေးပါ။"
        ),
        "backend_unavailable": (
            "❌ Membership backend ကို ယခုဆက်သွယ်မရပါ။\n\n"
            "Payment data မဖျက်ထားပါ။ ဒီ Approve button ကို နောက်တစ်ကြိမ် ပြန်နှိပ်နိုင်ပါတယ်။"
        ),
        "authoritative_expiry_missing": (
            "❌ Backend က အတည်ပြုထားသော expiry date မပြန်ပေးပါ။\n\n"
            "Payment data မဖျက်ထားပါ။ Apps Script စစ်ပြီး ပြန် Approve လုပ်ပါ။"
        ),
        "invalid_package": "❌ Payment package မမှန်ပါ။ Data မဖျက်ထားပါ။",
        "invalid_months": "❌ Membership လအရေအတွက် မမှန်ပါ။ Data မဖျက်ထားပါ။",
    }
    return messages.get(
        code,
        "❌ Membership approval မအောင်မြင်ပါ။\n\n"
        f"Reason: {code or 'unknown'}\n"
        "Payment data မဖျက်ထားပါ။ စစ်ဆေးပြီး ပြန် Approve လုပ်ပါ။",
    )


def _phase3_error_message(code: str) -> str:
    messages = {
        "MEMBERSHIP_ACTIVATION_FAILED": (
            "❌ Membership activation မအောင်မြင်သေးပါ။\n\n"
            "Payment ကို PENDING အတိုင်းထားထားပြီး ဒီ button ကို safe retry လုပ်နိုင်ပါတယ်။"
        ),
        "PHASE2_PAYMENT_APPROVAL_NOT_AVAILABLE": (
            "❌ Phase 2 payment module မတက်သေးပါ။ Payment ကို မပြောင်းထားပါ။"
        ),
        "PAYMENT_NOT_FOUND": "❌ Payment record မတွေ့ပါ။",
        "PAYMENT_ALREADY_REVIEWED": "❌ Payment ကို အခြား status နဲ့ review လုပ်ပြီးသားပါ။",
        "INVALID_STORED_PAYMENT": "❌ Payment row data မမှန်ပါ။ Admin က Sheet ကိုစစ်ပါ။",
        "PAYMENT_LOCK_BUSY": "⏳ Payment system အလုပ်များနေပါတယ်။ ခဏနေရင် ပြန်နှိပ်ပါ။",
    }
    return messages.get(
        code,
        "❌ Website payment review မအောင်မြင်ပါ။\n\n"
        f"Reason: {code or 'unknown'}\n"
        "Button ကို မဖယ်ထားပါ။ စစ်ဆေးပြီး ပြန်လုပ်နိုင်ပါတယ်။",
    )


async def _remove_approval_buttons(query) -> None:
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        # The approval itself is already idempotent; failing to remove the
        # keyboard must not turn a successful approval into an error.
        return


def _phase3_callback(data: str) -> tuple[str, str] | None:
    for action, prefix in (
        ("approveWebPayment", _PHASE3_APPROVE_PREFIX),
        ("rejectWebPayment", _PHASE3_REJECT_PREFIX),
    ):
        if not data.startswith(prefix):
            continue
        payment_id = data[len(prefix) :].strip()
        return action, payment_id
    return None


async def _handle_phase3_payment_callback(query, action: str, payment_id: str):
    runtime = _runtime()
    if not _PHASE3_PAYMENT_ID.fullmatch(payment_id):
        await query.message.reply_text("❌ Website Payment ID မမှန်ပါ")
        return None

    fields: dict[str, object] = {
        "paymentId": payment_id,
        "adminId": str(query.from_user.id),
    }
    if action == "rejectWebPayment":
        fields["reason"] = "Rejected by administrator"

    try:
        response = await phase2_membership_guard._post_privileged_sheet(
            action,
            **fields,
        )
    except Exception as exc:
        runtime.logger.error(
            "Phase 3 payment callback backend failure for %s: %s",
            payment_id,
            exc,
        )
        await query.message.reply_text(_phase3_error_message("backend_unavailable"))
        return None

    if not isinstance(response, dict) or response.get("ok") is not True:
        code = str(
            (response or {}).get("error")
            or (response or {}).get("message")
            or "backend_rejected"
        )
        runtime.logger.warning(
            "Phase 3 payment callback kept retryable for %s: %s",
            payment_id,
            code,
        )
        await query.message.reply_text(_phase3_error_message(code))
        return None

    await _remove_approval_buttons(query)

    status = str(response.get("status") or "").upper()
    if action == "rejectWebPayment":
        headline = (
            "♻️ Website payment ကို Reject လုပ်ပြီးသားပါ။"
            if response.get("alreadyRejected")
            else "❌ Website payment ကို Reject လုပ်ပြီးပါပြီ။"
        )
        await query.message.reply_text(f"{headline}\n\n🆔 {payment_id}")
        return response

    activation = response.get("activation") if isinstance(response.get("activation"), dict) else {}
    duplicate = bool(response.get("alreadyApproved") or activation.get("duplicate"))
    headline = (
        "♻️ Website payment ကို အရင်ကတည်းက approve လုပ်ပြီးသားပါ။ "
        "Membership သက်တမ်း ထပ်မတိုးပါ။"
        if duplicate
        else "✅ Website Payment + Membership Approved!"
    )
    expiry = str(activation.get("expireDate") or "")
    package = str(activation.get("package") or "")
    details = ""
    if package:
        details += f"\n📦 Package: {package}"
    if expiry:
        details += f"\n⏰ ကုန်ဆုံး: {expiry}"
    delivery = (
        "\n⚠️ Membership Active ဖြစ်ပေမယ့် customer DM မပို့နိုင်ပါ။"
        if response.get("deliveryFailed")
        else "\n📨 Customer notification ပြီးပါပြီ။"
    )

    await query.message.reply_text(
        f"{headline}\n\n🆔 {payment_id}{details}{delivery}"
    )
    return response


async def button_callback(update, context):
    """Intercept payment callbacks and delegate all unrelated callbacks."""
    runtime = _runtime()
    query = update.callback_query
    data = str(getattr(query, "data", "") or "")
    phase3 = _phase3_callback(data)
    is_legacy_approval = data.startswith("slip_ok_")

    if not is_legacy_approval and phase3 is None:
        if _original_button_callback is None:
            raise RuntimeError("payment callback integration is not installed")
        return await _original_button_callback(update, context)

    if query.from_user.id not in runtime.ADMIN_IDS:
        await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
        return None
    await query.answer()

    if phase3 is not None:
        action, payment_id = phase3
        return await _handle_phase3_payment_callback(query, action, payment_id)

    try:
        member_id = int(data.replace("slip_ok_", "", 1))
    except (TypeError, ValueError):
        await query.message.reply_text("❌ Member ID မမှန်ပါ")
        return None

    try:
        snapshot = payment_approval.pending_payment_snapshot(
            runtime.pending_payment,
            member_id,
        )
    except payment_approval.PaymentApprovalError as exc:
        await query.message.reply_text(_approval_error_message(str(exc)))
        return None

    try:
        months = int(snapshot.get("months") or 1)
    except (TypeError, ValueError):
        months = 1
    name = str(snapshot.get("name") or "Unknown")
    username = str(snapshot.get("username") or member_id)

    try:
        result = await payment_approval.approve_pending_payment(
            member_id=member_id,
            pending_payment=runtime.pending_payment,
            post_privileged_sheet=phase2_membership_guard._post_privileged_sheet,
            resolve_password=phase2_membership_guard.resolve_membership_password,
            package_names=runtime.PLAN_NAMES,
        )
    except payment_approval.PaymentApprovalError as exc:
        runtime.logger.warning(
            "payment approval kept pending for %s: %s",
            member_id,
            exc,
        )
        await query.message.reply_text(_approval_error_message(str(exc)))
        return None

    invite_url = ""
    try:
        invite_url = await runtime.create_invite_link(context, months * 30)
    except Exception as exc:
        runtime.logger.error(
            "approved member invite creation failed for %s: %s",
            member_id,
            exc,
        )

    delivery_error: Exception | None = None
    try:
        await runtime.send_approval_dm(
            context,
            member_id,
            months,
            result.password,
            invite_url,
            package=result.package,
        )
    except Exception as exc:
        delivery_error = exc
        runtime.logger.error(
            "membership approved but customer DM failed for %s: %s",
            member_id,
            exc,
        )

    await _remove_approval_buttons(query)

    headline = (
        "♻️ Payment approval ကို အရင်ကတည်းက မှတ်တမ်းတင်ပြီးသားပါ။ "
        "သက်တမ်းကို ထပ်မတိုးပါ။"
        if result.duplicate
        else "✅ Payment Confirmed + Membership Approved!"
    )
    password_line = (
        "🔑 Web password ကို customer DM ထဲပို့ထားပါသည်။\n"
        if result.package == "WEB" and not delivery_error
        else ""
    )
    delivery_line = (
        "⚠️ Membership က Active ဖြစ်ပြီးပါပြီ၊ ဒါပေမယ့် customer DM မပို့နိုင်ပါ။ "
        "Admin က /channel နဲ့ /mypassword flow ကိုစစ်ပါ။"
        if delivery_error
        else "📨 Member ကို DM ပို့ပြီးပါပြီ။"
    )

    await query.message.reply_text(
        f"{headline}\n\n"
        f"👤 {name} ({username})\n"
        f"📦 {runtime.PLAN_NAMES.get(result.package, result.package)} — {months} လ\n"
        f"⏰ ကုန်ဆုံး: {result.expire_date}\n"
        f"{password_line}"
        f"{delivery_line}"
    )
    return result


def install() -> SimpleNamespace:
    """Patch the callback before Telegram's CallbackQueryHandler is registered."""
    global _original_button_callback

    runtime = _runtime()
    if _original_button_callback is None:
        _original_button_callback = runtime.button_callback
    runtime.button_callback = button_callback
    return SimpleNamespace(button_callback=button_callback)
