"""Safe membership approval retry patch for the production Telegram bot.

This module is imported by ``queue_launcher.py`` after the normal launch stack
has loaded. It keeps payment approval data available when the Google Apps Script
write fails, keeps an existing Web member password stable across renewals, and
ensures the password sent to the member is the password actually stored in the
Members sheet.
"""

from __future__ import annotations

import asyncio
from typing import Any

import queue_launcher as _queue


_legacy = _queue._legacy
_original_button_callback = _legacy.button_callback
_original_send_approval_dm = _legacy.send_approval_dm
_last_membership_save: dict[str, dict[str, Any]] = {}
# Per-member locks, not one global lock: approve_payment_transaction's own
# retries can take 45-135s. A single shared lock would serialize an admin
# approving member A behind an unrelated slow retry for member B.
_approval_locks: dict[str, asyncio.Lock] = {}
_PAYMENT_DRAFT_RESTORE_TIMEOUT_SECONDS = 3.0


def _lock_for_member(member_id: Any) -> asyncio.Lock:
    key = str(member_id)
    lock = _approval_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _approval_locks[key] = lock
    return lock


def _normalise_package(value: Any) -> str:
    package = str(value or "CH").strip().upper().replace("_", "-")
    aliases = {
        "STANDARD": "CH",
        "CHANNEL": "CH",
        "WEB-PREMIUM": "WEB",
        "PREMIUM": "WEB",
    }
    return aliases.get(package, package)


def _safe_response_text(response: Any) -> str:
    try:
        return str(response.text or "").replace("\n", " ")[:500]
    except Exception:
        return "<response text unavailable>"


def _normalise_expire_date(value: Any) -> str:
    """Return a valid Members-sheet date in canonical dd/MM/yyyy form."""
    text = str(value or "").strip()
    if not text:
        return ""
    import re
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        return f"{int(match.group(1)):02d}/{int(match.group(2)):02d}/{match.group(3)}"
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return f"{int(match.group(3)):02d}/{int(match.group(2)):02d}/{match.group(1)}"
    return text


async def _fetch_sheet_member(user_id: str, attempts: int = 3) -> dict[str, str]:
    """Read the canonical password/package from Apps Script for one member."""
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id or not _legacy.SHEET_WEBHOOK:
        return {}

    for attempt in range(1, max(1, attempts) + 1):
        try:
            async with _legacy.httpx.AsyncClient(
                follow_redirects=True,
                timeout=40.0,
            ) as client:
                response = await client.post(
                    _legacy.SHEET_WEBHOOK,
                    json={"action": "getPassword", "userId": clean_user_id, "serverKey": _legacy.SHEET_SERVER_KEY},
                )
            if not response.is_error:
                data = response.json()
                if isinstance(data, dict) and data.get("status") == "ok":
                    return {
                        "password": str(data.get("password") or "").strip(),
                        "package": _normalise_package(data.get("package") or ""),
                    }
        except Exception as exc:
            if attempt == max(1, attempts):
                _legacy.logger.warning(
                    "Member password lookup failed user=%s: %s",
                    clean_user_id,
                    exc,
                )
        if attempt < max(1, attempts):
            await _legacy.asyncio.sleep(0.35 * attempt)
    return {}


async def save_member_to_sheet(
    user_id: str,
    username: str,
    days: int,
    password: str = "",
    package: str = "CH",
) -> dict:
    """Write membership data safely and return canonical Sheet fields."""
    clean_user_id = str(user_id or "").strip()
    clean_username = str(username or "").strip()
    clean_password = str(password or "").strip()
    clean_package = _normalise_package(package)

    try:
        clean_days = int(days)
    except (TypeError, ValueError):
        clean_days = 0

    if not _legacy.SHEET_WEBHOOK:
        detail = "SHEET_WEBHOOK environment variable is empty"
        _last_membership_save[clean_user_id] = {
            "ok": False,
            "detail": detail,
        }
        _legacy.logger.error("Membership save failed for %s: %s", clean_user_id, detail)
        return {"status": "error", "message": detail}

    if not clean_user_id or clean_days <= 0:
        detail = f"invalid payload: user_id={clean_user_id!r}, days={clean_days!r}"
        _last_membership_save[clean_user_id] = {
            "ok": False,
            "detail": detail,
        }
        _legacy.logger.error("Membership save failed: %s", detail)
        return {"status": "error", "message": detail}

    # The Apps Script saveMember path is canonical for password preservation:
    # same-package Web renewals keep Members!G and return the effective password.
    # Do not perform a blocking pre-lookup here; the approval callback has already
    # answered Telegram and must not spend callback time on a second Sheet call.

    payload = {
        "action": "saveMember",
        "userId": clean_user_id,
        "username": clean_username,
        "days": clean_days,
        "password": clean_password,
        "package": clean_package,
        "serverKey": _legacy.SHEET_SERVER_KEY,
    }

    last_detail = "unknown webhook failure"
    for attempt in range(1, 4):
        try:
            async with _legacy.httpx.AsyncClient(
                follow_redirects=True,
                timeout=40.0,
            ) as client:
                response = await client.post(
                    _legacy.SHEET_WEBHOOK,
                    json=payload,
                )

            status_code = int(response.status_code)
            response_text = _safe_response_text(response)

            if response.is_error:
                last_detail = f"HTTP {status_code}: {response_text}"
                _legacy.logger.error(
                    "Membership webhook HTTP failure user=%s attempt=%s/3 %s",
                    clean_user_id,
                    attempt,
                    last_detail,
                )
            else:
                try:
                    result = response.json()
                except Exception as exc:
                    result = None
                    last_detail = (
                        f"invalid JSON response ({type(exc).__name__}): "
                        f"{response_text}"
                    )
                    _legacy.logger.error(
                        "Membership webhook JSON failure user=%s attempt=%s/3 %s",
                        clean_user_id,
                        attempt,
                        last_detail,
                    )

                if isinstance(result, dict) and result.get("status") == "ok":
                    canonical = dict(result)
                    canonical.setdefault("package", clean_package)
                    canonical.setdefault("password", clean_password)
                    raw_expire = canonical.get("expireDate") or canonical.get("expiredDate") or ""
                    canonical["expireDate"] = _normalise_expire_date(raw_expire)
                    canonical["status"] = "ok"
                    _last_membership_save[clean_user_id] = {
                        "ok": True,
                        "detail": "ok",
                        "result": canonical,
                        "password": str(canonical.get("password") or clean_password),
                    }
                    _legacy.logger.info(
                        "Membership saved user=%s package=%s days=%s result=%s",
                        clean_user_id,
                        clean_package,
                        clean_days,
                        canonical.get("result", "ok"),
                    )
                    return canonical

                if isinstance(result, dict):
                    message = (
                        result.get("message")
                        or result.get("msg")
                        or result.get("error")
                        or "Apps Script returned status != ok"
                    )
                    last_detail = f"Apps Script: {message}"
                elif result is not None:
                    last_detail = f"unexpected JSON response: {str(result)[:500]}"

                _legacy.logger.error(
                    "Membership webhook logical failure user=%s attempt=%s/3 %s",
                    clean_user_id,
                    attempt,
                    last_detail,
                )

        except Exception as exc:
            last_detail = f"{type(exc).__name__}: {str(exc)[:500]}"
            _legacy.logger.exception(
                "Membership webhook exception user=%s attempt=%s/3",
                clean_user_id,
                attempt,
            )

        if attempt < 3:
            await _legacy.asyncio.sleep(0.8 * attempt)

    _last_membership_save[clean_user_id] = {
        "ok": False,
        "detail": last_detail,
    }
    return {"status": "error", "message": last_detail}


async def send_approval_dm(
    context,
    member_id: int,
    months: int,
    password: str,
    invite_url: str,
    package: str = "CH",
    expire_date: str = "",
):
    """Send the canonical password returned by saveMember without another Sheet call."""
    clean_package = _normalise_package(package)
    verified_password = str(password or "").strip()

    # saveMember returns the effective password after applying the Apps Script
    # renewal rule. Avoid a second blocking lookup here; a failed lookup after a
    # successful save must not turn approval into a Telegram callback timeout.
    if clean_package.startswith("WEB") and not verified_password:
        _legacy.logger.error(
            "Web approval password missing from canonical save response user=%s",
            member_id,
        )

    await _original_send_approval_dm(
        context,
        member_id,
        months,
        verified_password,
        invite_url,
        package=clean_package,
        expire_date=expire_date,
    )

    if clean_package.startswith("WEB") and not verified_password:
        try:
            await context.bot.send_message(
                chat_id=int(member_id),
                text=(
                    "⚠️ Web Password sync မပြီးသေးပါ။ Wrong password မပို့ထားပါ။\n\n"
                    "ခဏနေရင် /mypassword ကိုနှိပ်ပါ။ မရသေးရင် Admin ကိုဆက်သွယ်ပါ။"
                ),
            )
        except Exception as exc:
            _legacy.logger.warning(
                "Password sync warning DM failed user=%s: %s",
                member_id,
                exc,
            )


async def button_callback(update, context):
    """Keep approvals retryable and preserve the current Web password on renew."""
    query = update.callback_query
    callback_data = str(getattr(query, "data", "") or "")

    if not callback_data.startswith(("slip_confirm_", "slip_ok_", "slip_no_")):
        return await _original_button_callback(update, context)

    callback_prefix = next(
        (prefix for prefix in ("slip_confirm_", "slip_ok_", "slip_no_") if callback_data.startswith(prefix)),
        "",
    )

    # Answer Telegram immediately. Durable draft restoration may take seconds;
    # it must never happen before answerCallbackQuery or the callback can expire.
    if not getattr(query, "_jacc_callback_answered", False):
        try:
            await query.answer()
        finally:
            try:
                setattr(query, "_jacc_callback_answered", True)
            except Exception:
                pass

    member_id_text = callback_data.replace(callback_prefix, "", 1).strip()
    try:
        member_id = int(member_id_text)
    except ValueError:
        return await _original_button_callback(update, context)

    # Restore the durable draft before the legacy handler reads pending_payment.
    # This covers Railway restarts/redeploys between the admin buttons.
    if not _legacy.pending_payment.get(member_id):
        try:
            restored = await asyncio.wait_for(
                _legacy.get_payment_draft(member_id),
                timeout=_PAYMENT_DRAFT_RESTORE_TIMEOUT_SECONDS,
            )
            if restored:
                _legacy.pending_payment[member_id] = restored
        except asyncio.TimeoutError:
            _legacy.logger.warning(
                "Payment draft restore timed out user=%s after %.1fs; continuing without network wait",
                member_id,
                _PAYMENT_DRAFT_RESTORE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            _legacy.logger.warning("Payment draft restore failed user=%s: %s", member_id, exc)

    # The legacy handler may clear data after a successful approval. Keep a copy
    # so a temporary webhook failure does not destroy the approval session.
    payment_snapshot = dict(_legacy.pending_payment.get(member_id, {}) or {})
    _last_membership_save.pop(str(member_id), None)

    # The legacy handler calls query.answer() at its first line. Never perform
    # Sheet/network I/O before delegating, or Telegram may reject the callback as
    # too old before the approval logic starts. Apps Script saveMember remains
    # the canonical password-preservation authority.
    member_lock = _lock_for_member(member_id)
    try:
        async with member_lock:
            await _original_button_callback(update, context)
    except Exception as exc:
        # The legacy handler removes pending_payment before the Sheet write. If
        # the write already succeeded and a later Telegram response failed,
        # restoring the payment data would make the next tap renew the member a
        # second time. Treat that case as approved and never replay the write.
        save_result = _last_membership_save.get(str(member_id), {})
        if save_result.get("ok"):
            _legacy.logger.exception(
                "Membership approval completed but post-save step failed "
                "user=%s error=%s",
                member_id,
                exc,
            )
            try:
                await query.message.reply_text(
                    "✅ Membership Sheet ထဲသိမ်းပြီးပါပြီ။ Duplicate မဖြစ်အောင် "
                    "Approve ကို ထပ်မနှိပ်ပါနဲ့။ Customer ကို /mypassword သုံးခိုင်းပါ။"
                )
            except Exception:
                pass
            return

        # The current legacy handler approves through approve_payment_transaction
        # (an atomic Apps Script endpoint) rather than save_member_to_sheet, so
        # this patch's own bookkeeping is never populated on that path. Missing
        # bookkeeping is therefore not evidence of failure — treat it exactly
        # like the post-completion branch below does, instead of restoring an
        # already-cleared payment draft and telling the admin to re-approve
        # money that was already committed and DM'd to the member.
        if not save_result:
            _legacy.logger.exception(
                "Membership approval callback raised after delegating, with no "
                "patch-local save bookkeeping (likely approved via "
                "approve_payment_transaction); not treating as a failed "
                "approval user=%s error=%s",
                member_id,
                exc,
            )
            return

        if payment_snapshot:
            _legacy.pending_payment[member_id] = payment_snapshot
        _legacy.logger.exception(
            "Membership approval callback crashed before completion; "
            "payment data restored user=%s error=%s",
            member_id,
            exc,
        )
        try:
            await query.message.reply_text(
                "❌ Approve လုပ်နေစဉ် Error ဖြစ်သွားပါတယ်။ Data မပျောက်ပါ — "
                "Webhook စစ်ပြီး Yes — Approve ကို တစ်ကြိမ်ပဲ ထပ်နှိပ်ပါ။"
            )
        except Exception:
            pass
        return

    save_result = _last_membership_save.get(str(member_id), {})
    if save_result.get("ok"):
        return

    # The legacy callback may complete the approval successfully through a
    # different save wrapper, leaving no patch-local result. Do not turn that
    # missing bookkeeping entry into a false `unknown error` after the member
    # already received the success message. An explicit failed result is the
    # only safe condition for restoring/retrying the payment session.
    if not save_result:
        _legacy.logger.warning(
            "Approval returned without patch save bookkeeping user=%s; "
            "do not emit a false Sheet error or replay payment",
            member_id,
        )
        return

    # A failed save must remain retryable. This specifically prevents the next
    # button tap from returning “Data ကုန်သွားပြီ”.
    if payment_snapshot:
        _legacy.pending_payment[member_id] = payment_snapshot

    detail = str(save_result.get("detail") or save_result.get("message") or "unknown error")[:500]
    _legacy.logger.error(
        "Membership approval retained for retry user=%s detail=%s",
        member_id,
        detail,
    )

    if _legacy.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=_legacy.ADMIN_IDS[0],
                text=(
                    "🛠 Sheet error detail\n\n"
                    f"Member: {member_id}\n"
                    f"Error: {detail}\n\n"
                    "✅ Payment data ကို မဖျက်ထားပါ။ Webhook ပြင်ပြီး Yes — Approve ကို ထပ်နှိပ်နိုင်ပါတယ်။"
                ),
            )
        except Exception as exc:
            _legacy.logger.warning(
                "Detailed membership failure notification failed: %s",
                exc,
            )


# The legacy main function resolves these names only when it registers handlers,
# so patching here is early enough for the production runtime.
_legacy.save_member_to_sheet = save_member_to_sheet
_legacy.send_approval_dm = send_approval_dm
_legacy.button_callback = button_callback
