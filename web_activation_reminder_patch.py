"""Daily Web Premium activation reminder for JACC members.

Eligibility:
- Members sheet Status == ACTIVE
- Package == WEB
- DeviceID is blank

The reminder runs daily at 19:00 Myanmar time (UTC+06:30) and stops
implicitly as soon as the website binds a DeviceID for the member.

Device state is read directly from Google Sheets with the existing
GOOGLE_CREDS_JSON Railway service-account credential. Apps Script getMembers
is retained only as a fail-safe fallback because its legacy response does not
currently include DeviceID.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import completion_launcher as _completion
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


_legacy = _completion._legacy
_WEB_URL = "https://kyawmintun08.github.io/Japan-Auction-Car-Checker/"
_SHEET_ID = "1ZRw9xUS2pqZe5rJdmBtsX6yS7hAc65BHDO6K3zG1mpY"
_MEMBERS_TAB = "Members"
_MMT = timezone(timedelta(hours=6, minutes=30))
_REMINDER_HOUR = 19
_REMINDER_MINUTE = 0
_last_run_date: str | None = None


def _server_key() -> str:
    return str(
        getattr(_legacy, "SHEET_SERVER_KEY", "")
        or getattr(_legacy, "JACC_SERVER_KEY", "")
        or os.environ.get("SHEET_SERVER_KEY", "")
        or os.environ.get("JACC_SERVER_KEY", "")
    ).strip()


def _first(member: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in member and member.get(name) is not None:
            return member.get(name)
    return default


def _normalise_member(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        user_id = _first(
            raw,
            "userId", "userID", "userid", "UserID", "USERID",
            "telegramId", "telegram_id", "id",
        )
        username = _first(raw, "username", "Username", "USERNAME")
        status = _first(raw, "status", "Status", "STATUS")
        package = _first(raw, "package", "Package", "PACKAGE")
        device_id = _first(
            raw,
            "deviceId", "deviceID", "DeviceID", "DEVICEID",
            "device_id", "device",
        )
        return {
            "userId": str(user_id or "").strip().replace(".0", ""),
            "username": str(username or "").strip(),
            "status": str(status or "").strip().upper(),
            "package": str(package or "").strip().upper(),
            "deviceId": str(device_id or "").strip(),
        }

    if isinstance(raw, (list, tuple)):
        row = list(raw) + [""] * 10
        return {
            "userId": str(row[0] or "").strip().replace(".0", ""),
            "username": str(row[1] or "").strip(),
            "status": str(row[4] or "").strip().upper(),
            "package": str(row[7] or "").strip().upper(),
            "deviceId": str(row[9] or "").strip(),
        }

    return {"userId": "", "username": "", "status": "", "package": "", "deviceId": ""}


def _decode_google_credentials() -> dict[str, Any]:
    raw = str(os.environ.get("GOOGLE_CREDS_JSON", "") or "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_CREDS_JSON is empty")

    candidates = [raw]
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        candidates.append(decoded)
    except Exception:
        pass

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            info = json.loads(candidate)
            if not isinstance(info, dict):
                raise ValueError("credential JSON is not an object")
            if info.get("private_key"):
                info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
            return info
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"GOOGLE_CREDS_JSON is invalid: {last_error}")


def _load_members_from_sheet_sync() -> list[dict[str, str]]:
    import gspread

    creds = _decode_google_credentials()
    client = gspread.service_account_from_dict(creds)
    worksheet = client.open_by_key(_SHEET_ID).worksheet(_MEMBERS_TAB)
    values = list(worksheet.get("A:J"))
    if not values:
        return []

    headers = [str(value or "").strip().lower() for value in values[0]]
    index = {name: pos for pos, name in enumerate(headers) if name}

    def cell(row: list[Any], *names: str) -> str:
        for name in names:
            pos = index.get(name.lower())
            if pos is not None and pos < len(row):
                return str(row[pos] or "").strip()
        return ""

    members: list[dict[str, str]] = []
    for raw_row in values[1:]:
        row = list(raw_row)
        user_id = cell(row, "UserID", "user_id", "telegramId").replace(".0", "")
        if not user_id:
            continue
        members.append({
            "userId": user_id,
            "username": cell(row, "USERNAME", "Username"),
            "status": cell(row, "STATUS", "Status").upper(),
            "package": cell(row, "PACKAGE", "Package").upper(),
            "deviceId": cell(row, "DeviceID", "deviceId", "device_id"),
        })
    return members


async def _load_members_via_apps_script() -> list[dict[str, str]]:
    if not _legacy.SHEET_WEBHOOK:
        raise RuntimeError("SHEET_WEBHOOK is empty")

    payload: dict[str, Any] = {"action": "getMembers"}
    key = _server_key()
    if key:
        payload["serverKey"] = key

    async with _legacy.httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(
            _legacy.SHEET_WEBHOOK,
            json=payload,
            timeout=20,
        )
    response.raise_for_status()
    data = response.json()
    if str(data.get("status") or "").lower() != "ok":
        raise RuntimeError(str(data.get("message") or data.get("error") or "getMembers failed"))
    return [_normalise_member(item) for item in (data.get("members") or [])]


async def _load_members() -> tuple[list[dict[str, str]], str]:
    try:
        members = await asyncio.to_thread(_load_members_from_sheet_sync)
        return members, "google_sheet"
    except Exception as exc:
        _legacy.logger.warning("direct Members sheet read failed; using Apps Script fallback: %s", exc)
        members = await _load_members_via_apps_script()
        return members, "apps_script_fallback"


def _eligible_members(members: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        member
        for member in members
        if member.get("status") == "ACTIVE"
        and member.get("package") == "WEB"
        and not member.get("deviceId")
        and str(member.get("userId") or "").isdigit()
    ]


def _active_web_members(members: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        member for member in members
        if member.get("status") == "ACTIVE" and member.get("package") == "WEB"
    ]


def _assert_device_state_is_safe(members: list[dict[str, str]], source: str) -> None:
    if source == "google_sheet":
        return
    active_web = _active_web_members(members)
    if active_web and all(not member.get("deviceId") for member in active_web):
        raise RuntimeError(
            "DeviceID unavailable from Apps Script fallback; reminders blocked to prevent false sends"
        )


def _next_run_delay() -> float:
    now = datetime.now(_MMT)
    target = now.replace(
        hour=_REMINDER_HOUR,
        minute=_REMINDER_MINUTE,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in getattr(_legacy, "ADMIN_IDS", []) or []:
        try:
            await bot.send_message(chat_id=int(admin_id), text=text)
        except Exception as exc:
            _legacy.logger.warning("web reminder admin notify failed for %s: %s", admin_id, exc)


async def _diagnostic_scan() -> None:
    """Validate live Sheet access after deploy without messaging members."""
    await asyncio.sleep(75)
    try:
        members, source = await _load_members()
        _assert_device_state_is_safe(members, source)
        eligible = _eligible_members(members)
        active_web = _active_web_members(members)

        preview = ", ".join(
            f"@{m.get('username') or m.get('userId')}" for m in eligible[:8]
        ) or "မရှိ"

        async with Bot(token=_legacy.TOKEN) as bot:
            await _notify_admins(
                bot,
                "✅ Web Premium Reminder ready\n"
                f"Source: {source}\n"
                f"ACTIVE WEB: {len(active_web)}\n"
                f"Device မချိတ်ရသေး: {len(eligible)}\n"
                f"Pending: {preview}\n"
                "နေ့စဉ် 7:00 PM Myanmar Time မှာ reminder ပို့ပါမယ်။",
            )
    except Exception as exc:
        _legacy.logger.exception("web reminder diagnostic failed")
        try:
            async with Bot(token=_legacy.TOKEN) as bot:
                await _notify_admins(bot, f"❌ Web Reminder diagnostic failed: {exc}")
        except Exception:
            pass


async def _send_daily_reminders() -> tuple[int, int, int]:
    members, source = await _load_members()
    _assert_device_state_is_safe(members, source)
    eligible = _eligible_members(members)

    sent = 0
    failed = 0
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 JACC Web App ဖွင့်ရန်", url=_WEB_URL)]
    ])
    text = (
        "💎 *Web Premium အသုံးပြုရန် သတိပေးချက်*\n\n"
        "သင့် Membership က *Web Premium* ဖြစ်ပေမယ့် Website / App ကို "
        "ဒီ account နဲ့ မချိတ်ရသေးပါ။\n\n"
        "Premium Package ထဲမှာ Website/App အသုံးပြုခွင့် ပါပြီးသားပါ။ "
        "အောက်က button ကိုနှိပ်ပြီး Access Password နဲ့ Sign In လုပ်ပါ။\n\n"
        "🔑 Password မေ့ရင် /mypassword ကိုနှိပ်ပါ။\n\n"
        "✅ Device ချိတ်ပြီးတာနဲ့ ဒီနေ့စဉ် Reminder အလိုအလျောက် ရပ်သွားပါမယ်။"
    )

    async with Bot(token=_legacy.TOKEN) as bot:
        for member in eligible:
            try:
                await bot.send_message(
                    chat_id=int(member["userId"]),
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
                sent += 1
                await asyncio.sleep(0.08)
            except Exception as exc:
                failed += 1
                _legacy.logger.warning(
                    "web activation reminder failed for %s: %s",
                    member.get("userId"),
                    exc,
                )

        await _notify_admins(
            bot,
            "💎 Web Activation Reminder Summary\n"
            f"Source: {source}\n"
            f"Pending: {len(eligible)}\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}",
        )

    return len(eligible), sent, failed


async def daily_reminder_loop() -> None:
    global _last_run_date

    asyncio.create_task(_diagnostic_scan())

    while True:
        try:
            delay = _next_run_delay()
            _legacy.logger.info(
                "Web activation reminder scheduled in %.0f seconds (19:00 Myanmar time)",
                delay,
            )
            await asyncio.sleep(delay)

            today = datetime.now(_MMT).strftime("%Y-%m-%d")
            if _last_run_date == today:
                await asyncio.sleep(60)
                continue

            await _send_daily_reminders()
            _last_run_date = today
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _legacy.logger.exception("daily web activation reminder failed: %s", exc)
            await asyncio.sleep(300)


def start_background_task() -> asyncio.Task:
    return asyncio.create_task(
        daily_reminder_loop(),
        name="jacc-web-premium-activation-reminder",
    )


if not getattr(_completion, "_web_activation_reminder_wrapped", False):
    _original_completion_main = _completion.main

    async def _completion_main_with_web_reminder() -> None:
        task = start_background_task()
        try:
            await _original_completion_main()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _completion.main = _completion_main_with_web_reminder
    _completion._web_activation_reminder_wrapped = True
