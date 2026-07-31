"""JACC bot compatibility wrapper with an active-request duplicate guard.

The previous production launcher is preserved in ``bot_core.py``.  This wrapper
re-exports its complete module surface, then prevents the legacy fallback from
creating a second random Request ID while Supabase already has an open request
for the same Telegram member.
"""

from __future__ import annotations

from typing import Any

import bot_core as _core


# Preserve every public and private attribute expected by admin_launcher,
# completion_launcher, and queue_launcher.
for _name, _value in vars(_core).items():
    if _name not in {
        "__name__",
        "__file__",
        "__package__",
        "__spec__",
        "__loader__",
        "__cached__",
        "__builtins__",
    }:
        globals()[_name] = _value


_original_submit_request = _core.submit_request


async def _active_phase1_request(telegram_user_id: int) -> dict[str, Any] | None:
    """Return the member's newest open central request, when one exists."""
    if _core._legacy.phase1 is None:
        return None

    profile = await _core._legacy.phase1.get_profile_by_telegram_user_id(
        telegram_user_id
    )
    url = (
        f"{_core._legacy.phase1._base_url}/rest/v1/"
        "jacc_service_requests"
    )
    params = {
        "customer_id": f"eq.{profile['id']}",
        "status": "not.in.(completed,cancelled,closed_inactive)",
        "select": (
            "id,request_code,status,service_type,form_data,created_at"
        ),
        "order": "created_at.desc",
        "limit": "1",
    }
    async with _core._legacy.httpx.AsyncClient(
        timeout=_core._legacy.phase1._timeout
    ) as client:
        response = await client.get(
            url,
            headers=_core._legacy.phase1._headers,
            params=params,
        )

    if response.is_error:
        raise _core._legacy.JaccPhase1Error(
            "Active request lookup failed "
            f"({response.status_code}): {response.text[:500]}"
        )

    rows = response.json()
    return rows[0] if rows else None


async def submit_request(context, user_id: int, username: str):
    """Block duplicate legacy requests when the central request is still open."""
    try:
        active = await _active_phase1_request(int(user_id))
    except Exception:
        # A temporary lookup failure must not break the existing production flow.
        _core._legacy.logger.exception(
            "Active request duplicate guard lookup failed"
        )
        active = None

    if active:
        request_code = str(active.get("request_code") or "-")
        status = str(active.get("status") or "-")
        form_data = dict(active.get("form_data") or {})
        car_name = str(form_data.get("car_name") or "-")

        # Clear the just-completed form so it cannot be submitted again later.
        _core._legacy.pending_request.pop(int(user_id), None)

        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                "⚠️ *Active Request ရှိပြီးသားပါ*\n\n"
                f"🆔 Request ID: `{request_code}`\n"
                f"🚗 {car_name}\n"
                f"📊 Status: `{status}`\n\n"
                "လက်ရှိ Request ပြီးဆုံး/Cancel ဖြစ်ပြီးမှ Request အသစ်တင်နိုင်ပါမယ်။\n"
                "အခြေအနေကြည့်ရန် /mystatus"
            ),
            parse_mode="Markdown",
        )
        _core._legacy.logger.info(
            "Duplicate request blocked: user=%s active_request=%s",
            user_id,
            request_code,
        )
        return

    await _original_submit_request(context, user_id, username)


# Legacy callbacks resolve this module attribute at runtime.
_core.submit_request = submit_request
_core._legacy.submit_request = submit_request
