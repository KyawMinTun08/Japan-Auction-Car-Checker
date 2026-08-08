"""Use the deployed Apps Script getMembers response as the canonical reminder source.

The Apps Script endpoint now exposes DeviceID.  This avoids the separate Google
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


_reminder._load_members = apps_script_deviceid_load_members
_reminder._assert_device_state_is_safe = assert_device_schema_is_safe
