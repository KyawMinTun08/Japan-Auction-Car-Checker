"""Daily Web Premium activation reminder for JACC members.

Eligibility:
- Members sheet Status == ACTIVE
- Package == WEB
- DeviceID is blank

The reminder runs daily at 19:00 Myanmar time (UTC+06:30) and stops
implicitly as soon as the website binds a DeviceID for the member.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import completion_launcher as _completion
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup


_legacy = _completion._legacy
_WEB_URL = "https://kyawmintun08.github.io/Japan-Auction-Car-Checker/"
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

    # Defensive fallback if Apps Script ever returns row arrays directly.
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


async def _load_members() -> list[dict[str, str]]:
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


def _eligible_members(members: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        member
        for member in members
        if member.get("status") == "ACTIVE"
        and member.get("package") == "WEB"
        and not member.get("deviceId")
        and str(member.get("userId") or "").isdigit()
    ]


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
    """Validate the live Members response after deploy without messaging members."""
    await asyncio.sleep(75)
    try:
        members = await _load_members()
        eligible = _eligible_members(members)
        active_web = [m for m in members if m.get("status") == "ACTIVE" and m.get("package") == "WEB"]
        device_field_seen = any(bool(m.get("deviceId")) for m in active_web)

        async with Bot(token=_legacy.TOKEN) as bot:
            if active_web and not device_field_seen and len(eligible) == len(active_web):
                note = (
                    "⚠️ Web Reminder diagnostic: getMembers response မှာ DeviceID data မပါလာနိုင်ပါ။ "
                    "ACTIVE WEB member အားလုံးကို unbound လို့မြင်နေပါတယ်။ Member reminder မပို့ခင် backend response ကို စစ်ပါ။"
                )
                await _notify_admins(bot, note)
                return

            preview = ", ".join(
                f"@{m.get('username') or m.get('userId')}" for m in eligible[:8]
            ) or "မရှိ"
            await _notify_admins(
                bot,
                "✅ Web Premium Reminder ready\n"
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
    members = await _load_members()
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
            f"Pending: {len(eligible)}\n"
            f"Sent: {sent}\n"
            f"Failed: {failed}",
        )

    return len(eligible), sent, failed


async def daily_reminder_loop() -> None:
    global _last_run_date

    # Live diagnostic shortly after every deploy; it never messages members.
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


# queue_launcher imports this module before it calls completion_launcher.main().
# Wrapping completion main lets the reminder run even though Railway's active
# start command is queue_launcher.py.
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
