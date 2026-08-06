"""Safe membership approval retry patch for the production Telegram bot.

This module is imported by ``phase1_production_launcher.py`` after the normal
launch stack has loaded. It keeps payment approval data available when the
Google Apps Script write fails and adds detailed, safe Railway logging for the
real webhook response.
"""

from __future__ import annotations

from typing import Any

import queue_launcher as _queue


_legacy = _queue._legacy
_original_button_callback = _legacy.button_callback
_last_membership_save: dict[str, dict[str, Any]] = {}


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


async def save_member_to_sheet(
    user_id: str,
    username: str,
    days: int,
    password: str = "",
    package: str = "CH",
) -> bool:
    """Write membership data with retries and useful failure diagnostics."""
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
        return False

    if not clean_user_id or clean_days <= 0:
        detail = f"invalid payload: user_id={clean_user_id!r}, days={clean_days!r}"
        _last_membership_save[clean_user_id] = {
            "ok": False,
            "detail": detail,
        }
        _legacy.logger.error("Membership save failed: %s", detail)
        return False

    payload = {
        "action": "saveMember",
        "userId": clean_user_id,
        "username": clean_username,
        "days": clean_days,
        "password": clean_password,
        "package": clean_package,
    }

    last_detail = "unknown webhook failure"
    for attempt in range(1, 4):
        try:
            async with _legacy.httpx.AsyncClient(
                follow_redirects=True,
                timeout=20.0,
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
                    _last_membership_save[clean_user_id] = {
                        "ok": True,
                        "detail": "ok",
                        "result": result,
                    }
                    _legacy.logger.info(
                        "Membership saved user=%s package=%s days=%s result=%s",
                        clean_user_id,
                        clean_package,
                        clean_days,
                        result.get("result", "ok"),
                    )
                    return True

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
    return False


async def button_callback(update, context):
    """Restore pending payment data when a membership Sheet write fails."""
    query = update.callback_query
    callback_data = str(getattr(query, "data", "") or "")

    if not callback_data.startswith("slip_ok_"):
        return await _original_button_callback(update, context)

    member_id_text = callback_data.replace("slip_ok_", "", 1).strip()
    try:
        member_id = int(member_id_text)
    except ValueError:
        return await _original_button_callback(update, context)

    # The legacy handler pops this data before writing to Google Sheets. Keep a
    # copy so a temporary webhook failure does not destroy the approval session.
    payment_snapshot = dict(_legacy.pending_payment.get(member_id, {}) or {})
    _last_membership_save.pop(str(member_id), None)

    try:
        await _original_button_callback(update, context)
    except Exception:
        if payment_snapshot:
            _legacy.pending_payment[member_id] = payment_snapshot
        _legacy.logger.exception(
            "Membership approval callback crashed; payment data restored user=%s",
            member_id,
        )
        try:
            await query.message.reply_text(
                "❌ Approve လုပ်နေစဉ် Error ဖြစ်သွားပါတယ်။ Data မပျောက်ပါ — ခဏနေရင် Yes — Approve ကို ထပ်နှိပ်ပါ။"
            )
        except Exception:
            pass
        return

    save_result = _last_membership_save.get(str(member_id), {})
    if save_result.get("ok"):
        return

    # A failed save must remain retryable. This specifically prevents the next
    # button tap from returning “Data ကုန်သွားပြီ”.
    if payment_snapshot:
        _legacy.pending_payment[member_id] = payment_snapshot

    detail = str(save_result.get("detail") or "unknown error")[:500]
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
_legacy.button_callback = button_callback
