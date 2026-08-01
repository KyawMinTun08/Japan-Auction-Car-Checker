"""Telegram callback integration for retry-safe Phase 2 payment approval.

Install this module before ``legacy_bot.main()`` registers handlers. Only the
``slip_ok_`` callback is intercepted; every other callback is delegated to the
unchanged legacy handler.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import phase2_membership_guard
from phase2 import payment_approval


_legacy: Any | None = None
_original_button_callback: Callable[..., Awaitable[Any]] | None = None


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


async def _remove_approval_buttons(query) -> None:
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        # The approval itself is already idempotent; failing to remove the
        # keyboard must not turn a successful approval into an error.
        return


async def button_callback(update, context):
    """Intercept admin payment approval and delegate all unrelated callbacks."""
    runtime = _runtime()
    query = update.callback_query
    data = str(getattr(query, "data", "") or "")

    if not data.startswith("slip_ok_"):
        if _original_button_callback is None:
            raise RuntimeError("payment callback integration is not installed")
        return await _original_button_callback(update, context)

    await query.answer()
    if query.from_user.id not in runtime.ADMIN_IDS:
        await query.answer("❌ Admin သာ လုပ်နိုင်တယ်", show_alert=True)
        return None

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
