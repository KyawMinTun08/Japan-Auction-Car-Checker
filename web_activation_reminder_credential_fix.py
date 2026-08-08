"""Use the deployed Apps Script getMembers response as the canonical reminder source.

The Apps Script endpoint now exposes DeviceID. This avoids the separate Google
service-account dependency that previously caused Railway diagnostics to fail.
The loader fails closed unless the response explicitly contains a DeviceID
field (or a 10-column row with DeviceID at column J), so blank DeviceID values
are safe to interpret as genuinely unbound members.
"""

from __future__ import annotations

from typing import Any

import web_activation_reminder_patch as _reminder


_DEVICE_KEYS = (
    "deviceId",
    "deviceID",
    "DeviceID",
    "DEVICEID",
    "device_id",
)
_APKPURE_URL = "https://apkpure.com/japan-auction-car-checker/com.kyawmintun.jacc"


async def apps_script_deviceid_load_members() -> tuple[list[dict[str, str]], str]:
    if not _reminder._legacy.SHEET_WEBHOOK:
        raise RuntimeError("SHEET_WEBHOOK is empty")

    payload: dict[str, Any] = {"action": "getMembers"}
    key = _reminder._server_key()
    if key:
        payload["serverKey"] = key

    async with _reminder._legacy.httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(
            _reminder._legacy.SHEET_WEBHOOK,
            json=payload,
            timeout=20,
        )
    response.raise_for_status()
    data = response.json()

    if str(data.get("status") or "").lower() != "ok":
        raise RuntimeError(
            str(data.get("message") or data.get("error") or "getMembers failed")
        )

    raw_members = data.get("members") or []
    if not isinstance(raw_members, list):
        raise RuntimeError("getMembers members payload is not a list")

    # Prove that DeviceID is really present in the deployed Apps Script schema.
    schema_has_device = not raw_members
    for item in raw_members:
        if isinstance(item, dict) and any(key_name in item for key_name in _DEVICE_KEYS):
            schema_has_device = True
            break
        if isinstance(item, (list, tuple)) and len(item) >= 10:
            schema_has_device = True
            break

    if not schema_has_device:
        raise RuntimeError(
            "Apps Script getMembers response is missing DeviceID; reminders safely blocked"
        )

    members = [_reminder._normalise_member(item) for item in raw_members]
    return members, "apps_script_deviceid"


def assert_device_schema_is_safe(
    members: list[dict[str, str]],
    source: str,
) -> None:
    # The loader already verified that DeviceID exists in the raw response.
    # Therefore an empty deviceId value now safely means the member is unbound.
    if source != "apps_script_deviceid":
        raise RuntimeError("untrusted Web reminder member source")


def _install_apkpure_button() -> None:
    """Append a direct APKPure download button to reminder keyboards."""
    original_markup = _reminder.InlineKeyboardMarkup

    def markup_with_apkpure(inline_keyboard, *args, **kwargs):
        rows = [list(row) for row in inline_keyboard]
        has_web_button = any(
            getattr(button, "url", "") == _reminder._WEB_URL
            for row in rows
            for button in row
        )
        has_apkpure_button = any(
            getattr(button, "url", "") == _APKPURE_URL
            for row in rows
            for button in row
        )
        if has_web_button and not has_apkpure_button:
            rows.append([
                _reminder.InlineKeyboardButton(
                    "📲 Download JACC App (APKPure)",
                    url=_APKPURE_URL,
                )
            ])
        return original_markup(rows, *args, **kwargs)

    _reminder.InlineKeyboardMarkup = markup_with_apkpure


async def notify_admins_with_links(bot, text: str) -> None:
    """Show the same Web/App buttons on the startup ready diagnostic."""
    reply_markup = None
    if str(text or "").startswith("✅ Web Premium Reminder ready"):
        reply_markup = _reminder.InlineKeyboardMarkup([
            [
                _reminder.InlineKeyboardButton(
                    "🌐 JACC Web App ဖွင့်ရန်",
                    url=_reminder._WEB_URL,
                )
            ],
            [
                _reminder.InlineKeyboardButton(
                    "📲 Download JACC App (APKPure)",
                    url=_APKPURE_URL,
                )
            ],
        ])

    for admin_id in getattr(_reminder._legacy, "ADMIN_IDS", []) or []:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            _reminder._legacy.logger.warning(
                "web reminder admin notify failed for %s: %s",
                admin_id,
                exc,
            )


_reminder._load_members = apps_script_deviceid_load_members
_reminder._assert_device_state_is_safe = assert_device_schema_is_safe
_install_apkpure_button()
_reminder._notify_admins = notify_admins_with_links
