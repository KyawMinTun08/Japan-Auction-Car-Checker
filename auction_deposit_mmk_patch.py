"""JACC auction deposit policy: fixed MMK 1,000,000 deposit.

Production behavior:
- All user-facing auction deposit prompts show MMK 1,000,000 (not THB 20,000).
- Deposit slip OCR validates at least MMK 1,000,000.
- Deposits are stored with mmkAmount=1,000,000 and an internal THB equivalent
  based on MMK_RATE so existing auction balance math remains compatible.
- Auction-lost refunds return the exact MMK deposit amount.

The patch is loaded before legacy_bot.main() registers handlers, so it keeps the
large legacy bot unchanged and is easy to roll back.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

import completion_launcher as _completion
from telegram.ext import ExtBot


_legacy = _completion._legacy
_DEPOSIT_MMK = int(os.environ.get("AUCTION_DEPOSIT_MMK", "1000000"))

_original_button_callback = _legacy.button_callback
_original_handle_photo = _legacy.handle_photo
_original_auctionwon_cmd = _legacy.auctionwon_cmd
_original_auctionlost_cmd = _legacy.auctionlost_cmd
_original_inline_button = _legacy.InlineKeyboardButton
_original_send_message = ExtBot.send_message
_original_edit_message_text = ExtBot.edit_message_text


def _amount_int(value: Any, default: int = 0) -> int:
    try:
        cleaned = re.sub(r"[^0-9.-]", "", str(value or ""))
        return int(float(cleaned)) if cleaned else default
    except Exception:
        return default


def _policy_text(text: Any) -> Any:
    """Rewrite only the old fixed deposit copy; unrelated prices are untouched."""
    if not isinstance(text, str):
        return text
    return text.replace("฿20,000", f"{_DEPOSIT_MMK:,} ကျပ်")


def _deposit_button(text, *args, **kwargs):
    return _original_inline_button(_policy_text(text), *args, **kwargs)


if not getattr(ExtBot, "_jacc_mmk_deposit_text_wrapped", False):
    async def _send_message_with_mmk_deposit(self, chat_id, text, *args, **kwargs):
        return await _original_send_message(
            self,
            chat_id=chat_id,
            text=_policy_text(text),
            *args,
            **kwargs,
        )

    async def _edit_message_with_mmk_deposit(self, text, *args, **kwargs):
        return await _original_edit_message_text(
            self,
            text=_policy_text(text),
            *args,
            **kwargs,
        )

    ExtBot.send_message = _send_message_with_mmk_deposit
    ExtBot.edit_message_text = _edit_message_with_mmk_deposit
    ExtBot._jacc_mmk_deposit_text_wrapped = True

# Buttons in legacy functions resolve this global at call time.
_legacy.InlineKeyboardButton = _deposit_button


async def handle_photo(update, context):
    """Intercept only deposit slips; delegate every other photo flow unchanged."""
    user = update.effective_user
    user_id = user.id

    # Preserve legacy priority for admin QR and broadcast-photo modes.
    if user_id in getattr(_legacy, "ADMIN_IDS", []):
        if user_id in getattr(_legacy, "pending_setqr", {}):
            return await _original_handle_photo(update, context)
    if (
        user_id in getattr(_legacy, "pending_broadcast", {})
        and _legacy.pending_broadcast[user_id].get("waiting_photo")
    ):
        return await _original_handle_photo(update, context)

    dep_data = getattr(_legacy, "pending_deposit", {}).get(str(user_id))
    if not dep_data or dep_data.get("step") != "waiting_slip":
        return await _original_handle_photo(update, context)

    if not _legacy.check_rate_limit(user_id, max_req=5, window=60):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း ပုံများသွားတယ် — ခဏစောင့်ပါ")
        return

    photo = update.message.photo[-1]
    await update.message.reply_text("🔍 Deposit Slip ဖတ်နေတယ်... ⏳")
    try:
        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())
        slip_info = await _legacy.gemini_read_slip(file_bytes)
    except Exception as exc:
        _legacy.logger.error("MMK deposit slip read: %s", exc)
        slip_info = {}

    amount = slip_info.get("AMOUNT", "UNKNOWN")
    pay_type = slip_info.get("TYPE", "UNKNOWN")
    txn_no = slip_info.get("TRANSACTION_NO", "UNKNOWN")
    date_str = slip_info.get("DATE", "UNKNOWN")
    amt_num = _amount_int(amount, -1)

    if amt_num < 0:
        amount_ok = "⚠️ စစ်မရ"
        amount_display = str(amount)
    elif amt_num >= _DEPOSIT_MMK:
        amount_ok = "✅"
        amount_display = f"{amt_num:,}"
    else:
        amount_ok = f"⚠️ မပြည့်မီ ({_DEPOSIT_MMK:,} ကျပ် လိုသည်)"
        amount_display = f"{amt_num:,}"

    _legacy.pending_deposit[str(user_id)]["slip_info"] = slip_info
    req_id = dep_data.get("reqId", "")
    name = update.effective_user.first_name or str(user_id)

    admin_text = (
        "💰 *Deposit Slip အသစ်*\n\n"
        f"👤 {name} (`{user_id}`)\n"
        f"🆔 Request: `{req_id}`\n\n"
        f"🏦 Type: {pay_type}\n"
        f"🔢 Txn No: `{txn_no}`\n"
        f"💵 Amount: {amount_display} ကျပ် {amount_ok}\n"
        f"📅 Date: {date_str}\n\n"
        "⚠️ စစ်ဆေးပြီးမှ Confirm လုပ်ပါ"
    )
    admin_kb = _legacy.InlineKeyboardMarkup([
        [_original_inline_button(f"💬 {name} ကို Message", url=f"tg://user?id={user_id}")],
        [
            _original_inline_button("✅ Confirm", callback_data=f"dep_ok_{user_id}"),
            _original_inline_button("❌ Reject", callback_data=f"dep_no_{user_id}"),
        ],
    ])
    await _legacy.notify_admins(context, admin_text, reply_markup=admin_kb)
    await update.message.reply_text(
        "✅ *Deposit Slip လက်ခံပြီ!*\n\nAdmin စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏",
        parse_mode="Markdown",
    )


async def button_callback(update, context):
    """Use legacy callbacks except admin confirmation of the fixed MMK deposit."""
    query = update.callback_query
    data = str(query.data or "")
    if not data.startswith("dep_ok_"):
        return await _original_button_callback(update, context)

    await query.answer()
    if query.from_user.id not in _legacy.ADMIN_IDS:
        await query.answer("❌ Admin only", show_alert=True)
        return

    customer_id = data.replace("dep_ok_", "")
    dep_data = _legacy.pending_deposit.get(customer_id, {})
    req_id = dep_data.get("reqId", "")
    broker_tg_id = dep_data.get("brokerTgId", "")
    slip_info = dep_data.get("slip_info", {})
    if not req_id:
        await query.message.reply_text("❌ Deposit data မတွေ့ပါ — Customer ကို slip ပြန်ပို့ခိုင်းပါ")
        return

    # Re-check the OCR amount before committing, even though an admin confirms it.
    slip_amount = _amount_int(slip_info.get("AMOUNT"), -1)
    if 0 <= slip_amount < _DEPOSIT_MMK:
        await query.message.reply_text(
            f"⚠️ Slip amount {slip_amount:,} ကျပ်ပဲရှိပါတယ်။ "
            f"လိုအပ်သော Deposit = {_DEPOSIT_MMK:,} ကျပ်။"
        )
        return

    mmk_rate = _amount_int(os.environ.get("MMK_RATE", "3800"), 3800)
    thb_equivalent = round(_DEPOSIT_MMK / mmk_rate) if mmk_rate > 0 else 0
    now_str = datetime.now().strftime("%d/%m/%Y")

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                _legacy.SHEET_WEBHOOK,
                json={
                    "action": "saveDeposit",
                    "reqId": req_id,
                    "customerId": customer_id,
                    "brokerTgId": broker_tg_id,
                    # Kept for backward-compatible auction balance math only.
                    "thbAmount": thb_equivalent,
                    "mmkAmount": _DEPOSIT_MMK,
                    "mmkRate": mmk_rate,
                    "date": now_str,
                    "txnNo": slip_info.get("TRANSACTION_NO", ""),
                    "payType": slip_info.get("TYPE", ""),
                    "status": "HOLD",
                },
                timeout=15,
            )
        response.raise_for_status()
        result = response.json()
        if str(result.get("status") or "").lower() != "ok":
            raise RuntimeError(str(result.get("message") or result.get("msg") or "saveDeposit failed"))
    except Exception as exc:
        _legacy.logger.exception("MMK saveDeposit failed: %s", exc)
        await query.message.reply_text("❌ Deposit Sheet save မအောင်မြင်ပါ။ Data ကို မဖျက်ထားပါ — ပြန် Confirm လုပ်နိုင်ပါတယ်။")
        return

    _legacy.pending_deposit.pop(customer_id, None)

    try:
        await _original_send_message(
            context.bot,
            chat_id=int(customer_id),
            text=(
                "✅ *Deposit လက်ခံပြီ!*\n\n"
                f"🆔 `{req_id}`\n"
                f"💰 {_DEPOSIT_MMK:,} ကျပ်\n"
                f"📅 {now_str}\n\n"
                "Broker က လေလံအတွက် ဆက်လုပ်ပေးနေပါပြီ ⏳"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        _legacy.logger.error("MMK dep_ok customer: %s", exc)

    if broker_tg_id:
        try:
            await _original_send_message(
                context.bot,
                chat_id=int(broker_tg_id),
                text=(
                    "✅ *Customer Deposit ရပြီ — လေလံဆက်လုပ်နိုင်ပြီ*\n\n"
                    f"🆔 `{req_id}`\n"
                    f"💰 {_DEPOSIT_MMK:,} ကျပ် — HOLD ✅\n\n"
                    "Admin မှ Deposit အတည်ပြုပြီ"
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:
            _legacy.logger.error("MMK dep_ok broker: %s", exc)

    await query.message.reply_text(
        "✅ *Deposit Confirmed!*\n\n"
        f"🆔 `{req_id}`\n"
        f"👤 Customer: `{customer_id}`\n"
        f"💰 {_DEPOSIT_MMK:,} ကျပ်\n"
        f"📅 Internal rate: {mmk_rate:,} ks/฿",
        parse_mode="Markdown",
    )

    if req_id in _legacy.proxy_sessions:
        _legacy.proxy_sessions[req_id]["deposit_paid"] = True
    _legacy.nodep_pending.pop(req_id, None)


async def auctionwon_cmd(update, context):
    user_id = update.effective_user.id
    if user_id not in _legacy.ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: `/auctionwon R123456 [ကားဖိုး]`\nဥပမာ: `/auctionwon R001234 150000`",
            parse_mode="Markdown",
        )
        return

    req_id = context.args[0].strip().upper()
    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                _legacy.SHEET_WEBHOOK,
                json={"action": "getDeposit", "reqId": req_id},
                timeout=10,
            )
        dep = resp.json()
    except Exception as exc:
        _legacy.logger.error("MMK auctionwon getDeposit: %s", exc)
        await update.message.reply_text("❌ Sheet error")
        return

    if dep.get("status") != "ok":
        await update.message.reply_text(f"❌ `{req_id}` Deposit မတွေ့ပါ", parse_mode="Markdown")
        return

    customer_id = dep.get("customerId")
    broker_tg_id = dep.get("brokerTgId")
    mmk_amount = _amount_int(dep.get("mmkAmount"), 0)
    thb_credit = _amount_int(dep.get("thbAmount"), 0)
    car_price = _amount_int(context.args[1], 0) if len(context.args) > 1 else 0
    remaining = max(0, car_price - thb_credit) if car_price else 0
    is_new_mmk = mmk_amount == _DEPOSIT_MMK

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(
                _legacy.SHEET_WEBHOOK,
                json={
                    "action": "updateDeposit",
                    "reqId": req_id,
                    "auctionResult": "WON",
                    "carPrice": car_price,
                },
                timeout=10,
            )
    except Exception as exc:
        _legacy.logger.error("MMK auctionwon updateDeposit: %s", exc)

    if is_new_mmk:
        deposit_label = f"{mmk_amount:,} ကျပ်"
        deposit_note = "ကားဖိုးထဲ Deposit ပေးသည့်နေ့ ငွေလဲနှုန်းအတိုင်း ထည့်တွက်ပြီ"
    else:
        deposit_label = f"฿{thb_credit:,}"
        deposit_note = "ကားဖိုးထဲ ထည့်တွက်ပြီ"

    if customer_id:
        try:
            msg = (
                "🏆 *ကားရပြီ!*\n\n"
                f"🆔 Request: `{req_id}`\n\n"
                f"💰 Deposit: {deposit_label} ({deposit_note})\n"
            )
            if car_price:
                msg += (
                    f"🚗 ကားဖိုး: ฿{car_price:,}\n"
                    f"💵 ကျန်ပေးရမည်: ฿{remaining:,} + Commission\n\n"
                )
            msg += "Admin မှ ကျန်ငွေ + Commission တောင်းပါမည် 📞"
            await _original_send_message(
                context.bot,
                chat_id=int(customer_id),
                text=msg,
                parse_mode="Markdown",
            )
        except Exception as exc:
            _legacy.logger.error("MMK auctionwon customer: %s", exc)

    if broker_tg_id:
        try:
            await _original_send_message(
                context.bot,
                chat_id=int(broker_tg_id),
                text=(
                    "🏆 *Auction Won!*\n\n"
                    f"🆔 `{req_id}`\n"
                    "Customer ကို ကျန်ငွေ တောင်းဆိုပြီ ✅"
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:
            _legacy.logger.error("MMK auctionwon broker: %s", exc)

    await update.message.reply_text(
        "✅ *Auction Won မှတ်တမ်းတင်ပြီ*\n\n"
        f"🆔 `{req_id}`\n"
        f"💰 Deposit {deposit_label} — {deposit_note}\n"
        + (f"💵 ကျန်ငွေ: ฿{remaining:,} + Commission" if car_price else ""),
        parse_mode="Markdown",
    )


async def auctionlost_cmd(update, context):
    user_id = update.effective_user.id
    if user_id not in _legacy.ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: `/auctionlost R123456`", parse_mode="Markdown")
        return

    req_id = context.args[0].strip().upper()
    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                _legacy.SHEET_WEBHOOK,
                json={"action": "getDeposit", "reqId": req_id},
                timeout=10,
            )
        dep = resp.json()
    except Exception as exc:
        _legacy.logger.error("MMK auctionlost getDeposit: %s", exc)
        await update.message.reply_text("❌ Sheet error")
        return

    if dep.get("status") != "ok":
        await update.message.reply_text(f"❌ `{req_id}` Deposit မတွေ့ပါ", parse_mode="Markdown")
        return

    customer_id = dep.get("customerId")
    broker_tg_id = dep.get("brokerTgId")
    mmk_amount = _amount_int(dep.get("mmkAmount"), 0)
    thb_amount = _amount_int(dep.get("thbAmount"), 0)
    is_new_mmk = mmk_amount == _DEPOSIT_MMK

    try:
        async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
            await client.post(
                _legacy.SHEET_WEBHOOK,
                json={"action": "updateDeposit", "reqId": req_id, "auctionResult": "LOST"},
                timeout=10,
            )
    except Exception as exc:
        _legacy.logger.error("MMK auctionlost updateDeposit: %s", exc)

    if customer_id:
        try:
            if is_new_mmk:
                text = (
                    "😔 *ကားမရဘူး*\n\n"
                    f"🆔 Request: `{req_id}`\n\n"
                    f"💰 Deposit: {mmk_amount:,} ကျပ်\n"
                    f"💵 ပြန်ပေးမည်: *{mmk_amount:,} ကျပ်*\n\n"
                    "Deposit အပြည့်ကို Admin မှ ၂-၃ ရက်အတွင်း ပြန်လွှဲပေးပါမည် 🙏"
                )
            else:
                text = (
                    "😔 *ကားမရဘူး*\n\n"
                    f"🆔 Request: `{req_id}`\n\n"
                    f"💰 Deposit: ฿{thb_amount:,}\n"
                    f"💵 ပြန်ပေးမည်: *{mmk_amount:,} ks*\n\n"
                    "(ပေးသည့်နေ့ rate အတိုင်း MMK ပြန်ပေးမည်)\n\n"
                    "Admin မှ ၂-၃ ရက်အတွင်း ပြန်လွှဲပေးပါမည် 🙏"
                )
            await _original_send_message(
                context.bot,
                chat_id=int(customer_id),
                text=text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            _legacy.logger.error("MMK auctionlost customer: %s", exc)

    await _legacy.notify_admins(
        context,
        "💸 *Refund လုပ်ပေးရမည်!*\n\n"
        f"🆔 `{req_id}`\n"
        f"👤 Customer ID: `{customer_id}`\n"
        f"💵 ပြန်ပေးရမည်: *{mmk_amount:,} ကျပ်*\n\n"
        f"ပြန်လွှဲပြီးရင် `/refunddone {req_id}` နှိပ်ပါ",
    )

    if broker_tg_id:
        try:
            await _original_send_message(
                context.bot,
                chat_id=int(broker_tg_id),
                text=(
                    "😔 *Auction Lost*\n\n"
                    f"🆔 `{req_id}`\n"
                    "Customer ကို Deposit ပြန်ပေးမည် — Admin handle လုပ်မည်"
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:
            _legacy.logger.error("MMK auctionlost broker: %s", exc)

    await update.message.reply_text(
        "✅ *Auction Lost မှတ်တမ်းတင်ပြီ*\n\n"
        f"🆔 `{req_id}`\n"
        f"💵 Refund: *{mmk_amount:,} ကျပ်*\n\n"
        "⚠️ Customer ကို ပြန်လွှဲပေးဖို့ မမေ့ပါနဲ့!",
        parse_mode="Markdown",
    )


# Replace handlers before legacy_bot.main() registers them.
_legacy.handle_photo = handle_photo
_legacy.button_callback = button_callback
_legacy.auctionwon_cmd = auctionwon_cmd
_legacy.auctionlost_cmd = auctionlost_cmd
