"""JACC Phase 2 membership and Telegram channel safety guard.

This module is intentionally not imported by the production launcher yet.
It provides tested replacements for legacy membership checks, approval
persistence, and authenticated server-to-server Apps Script calls. Call
``install()`` only after the coordinated Apps Script/Railway rollout is ready.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx


_BANGKOK = ZoneInfo("Asia/Bangkok")
_ALLOWED_PACKAGES = {"CH", "WEB", "PROMO10D"}
_legacy: Any | None = None


def _runtime() -> Any:
    """Load the production bot lazily so pure tests need no bot dependencies."""
    global _legacy
    if _legacy is None:
        import legacy_bot

        _legacy = legacy_bot
    return _legacy


def normalise_member_id(value: object) -> str:
    """Return a stable Telegram user ID string from Sheet/API values."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()

    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalise_member_status(value: object) -> str:
    return str(value or "").strip().upper()


def normalise_member_package(value: object) -> str:
    package = str(value or "CH").strip().upper().replace(" ", "_")
    aliases = {
        "STANDARD": "CH",
        "TELEGRAM": "CH",
        "CH-PROMO": "CH",
        "CH_PROMO": "CH",
        "PREMIUM": "WEB",
        "WEB-PROMO": "WEB",
        "WEB_PROMO": "WEB",
        "WEB_PREMIUM": "WEB",
        "PROMO-10D": "PROMO10D",
        "PROMO_10D": "PROMO10D",
    }
    return aliases.get(package, package)


def parse_expire_date(value: object) -> date | None:
    """Parse the date formats currently seen in the Members sheet/API."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value or "").strip()
    if not text:
        return None

    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(text.rstrip("Z"), fmt).date()
        except ValueError:
            continue
    return None


def member_row_is_active(member: dict, *, today: date | None = None) -> bool:
    """Require ACTIVE status and a valid, non-expired membership date."""
    if normalise_member_status(member.get("status")) != "ACTIVE":
        return False
    expiry = parse_expire_date(
        member.get("expireDate")
        or member.get("expire_date")
        or member.get("expiry")
    )
    if expiry is None:
        return False
    current_day = today or datetime.now(_BANGKOK).date()
    return expiry >= current_day


def member_row_user_id(member: dict) -> str:
    return normalise_member_id(
        member.get("userId")
        or member.get("userID")
        or member.get("UserID")
        or member.get("telegramId")
    )


def _sheet_server_key() -> str:
    """Read the Railway-only Apps Script credential without exposing it."""
    runtime = _runtime()
    return str(
        getattr(runtime, "SHEET_SERVER_KEY", "")
        or os.environ.get("SHEET_SERVER_KEY", "")
    ).strip()


def build_privileged_sheet_payload(action: str, **fields: object) -> dict:
    """Build a fail-closed server-to-server Apps Script request payload."""
    action_name = str(action or "").strip()
    if not action_name:
        raise RuntimeError("privileged Sheet action is missing")

    server_key = _sheet_server_key()
    if not server_key:
        raise RuntimeError("SHEET_SERVER_KEY is not configured")

    payload = {"action": action_name, "serverKey": server_key}
    payload.update(fields)
    return payload


async def _post_privileged_sheet(action: str, **fields: object) -> dict:
    """POST one authenticated Apps Script action and require JSON output."""
    runtime = _runtime()
    if not runtime.SHEET_WEBHOOK:
        raise RuntimeError("SHEET_WEBHOOK is not configured")

    payload = build_privileged_sheet_payload(action, **fields)
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        response = await client.post(runtime.SHEET_WEBHOOK, json=payload)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError(f"{action} returned a non-object response")
    return result


async def _fetch_members() -> list[dict]:
    payload = await _post_privileged_sheet("getMembers")
    if payload.get("status") not in (None, "ok"):
        raise RuntimeError(f"getMembers failed: {payload}")
    members = payload.get("members", [])
    if not isinstance(members, list):
        raise RuntimeError("getMembers returned a non-list members value")
    return members


async def _fetch_existing_password(user_id: str) -> str:
    """Read the current credential for WEB renewal/upgrade preservation."""
    payload = await _post_privileged_sheet("getPassword", userId=str(user_id))
    status = str(payload.get("status") or "").lower()
    if status and status != "ok" and not payload.get("ok"):
        return ""
    return str(payload.get("password") or "").strip()


async def save_member_to_sheet_secure(
    user_id: str,
    username: str,
    days: int,
    password: str = "",
    package: str = "CH",
) -> bool:
    """Persist a member through the authenticated Apps Script contract."""
    payload = await _post_privileged_sheet(
        "saveMember",
        userId=str(user_id),
        username=str(username or "").replace("@", "").strip(),
        days=int(days),
        password=str(password or "").strip(),
        package=normalise_member_package(package),
    )
    return str(payload.get("status") or "").lower() == "ok"


async def resolve_membership_password(user_id: str, package: str) -> str:
    """Preserve a WEB member's password; generate only when none exists."""
    runtime = _runtime()
    if normalise_member_package(package) != "WEB":
        return ""

    try:
        existing = await _fetch_existing_password(str(user_id))
    except Exception as exc:
        runtime.logger.warning(
            "existing password lookup failed for %s: %s", user_id, exc
        )
        existing = ""
    return existing or runtime.generate_password()


async def is_active_member(user_id: int) -> bool:
    """Customer access check: fail closed when membership cannot be proven."""
    runtime = _runtime()
    if user_id in runtime.ADMIN_IDS:
        return True
    try:
        members = await _fetch_members()
    except Exception as exc:
        runtime.logger.error("membership active check failed: %s", exc)
        return False

    wanted = str(user_id)
    return any(
        member_row_user_id(member) == wanted and member_row_is_active(member)
        for member in members
    )


async def get_member_package(user_id: int) -> str | None:
    runtime = _runtime()
    if user_id in runtime.ADMIN_IDS:
        return "WEB"
    try:
        members = await _fetch_members()
    except Exception as exc:
        runtime.logger.error("membership package check failed: %s", exc)
        return None

    wanted = str(user_id)
    for member in members:
        if member_row_user_id(member) != wanted:
            continue
        if not member_row_is_active(member):
            return None
        package = normalise_member_package(member.get("package"))
        return package if package in _ALLOWED_PACKAGES else None
    return None


async def is_valid_member(user_id: int) -> bool:
    """Destructive channel-removal check: fail safe on temporary Sheet errors."""
    runtime = _runtime()
    if user_id in runtime.ADMIN_IDS:
        return True
    try:
        members = await _fetch_members()
    except Exception as exc:
        runtime.logger.error("channel membership validation failed: %s", exc)
        return True

    wanted = str(user_id)
    for member in members:
        if member_row_user_id(member) != wanted:
            continue
        package = normalise_member_package(member.get("package"))
        return member_row_is_active(member) and package in _ALLOWED_PACKAGES
    return False


async def activate_promo10d(context, user_id: int, username: str) -> bool:
    """Use the same authenticated saveMember contract as paid memberships."""
    del context
    runtime = _runtime()
    return await save_member_to_sheet_secure(
        str(user_id),
        str(username or user_id).replace("@", "").strip(),
        10,
        runtime.generate_password(),
        "PROMO10D",
    )


async def approve_member(update, context) -> None:
    """Admin approval that never reports success before Sheet persistence."""
    runtime = _runtime()
    admin_id = update.effective_user.id
    if runtime.ADMIN_IDS and admin_id not in runtime.ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format: `/approve 123456789 1 WEB`",
            parse_mode="Markdown",
        )
        return

    target = str(context.args[0]).replace("@", "").strip()
    try:
        months = int(context.args[1])
    except (TypeError, ValueError):
        await update.message.reply_text("❌ လ ဂဏန်းထည့်ပါ")
        return
    if months < 1 or months > 12:
        await update.message.reply_text("❌ Membership လကို 1 မှ 12 အတွင်း ထည့်ပါ")
        return

    package = normalise_member_package(
        context.args[2] if len(context.args) > 2 else "CH"
    )
    if package not in {"CH", "WEB"}:
        await update.message.reply_text("❌ Package ကို CH သို့မဟုတ် WEB သာ ထည့်ပါ")
        return

    member_id: int | None
    member_username = target
    try:
        member_id = int(target)
    except ValueError:
        member_id = None

    if member_id is not None:
        try:
            chat = await context.bot.get_chat(member_id)
            member_username = (
                getattr(chat, "username", None)
                or getattr(chat, "first_name", None)
                or str(member_id)
            )
        except Exception as exc:
            runtime.logger.info("approve get_chat %s: %s", member_id, exc)

    member_key = str(member_id) if member_id is not None else target
    password = await resolve_membership_password(member_key, package)
    try:
        saved = await save_member_to_sheet_secure(
            member_key,
            member_username,
            months * 30,
            password,
            package,
        )
    except Exception as exc:
        runtime.logger.error("secure membership save failed for %s: %s", member_key, exc)
        saved = False

    if not saved:
        await update.message.reply_text(
            "❌ Membership ကို Sheet ထဲ မသိမ်းနိုင်ပါ။\n\n"
            "Customer ကို approve မလုပ်ရသေးပါ။ Sheet/Webhook စစ်ပြီး ပြန်လုပ်ပါ။"
        )
        return

    invite_url = await runtime.create_invite_link(context, months * 30)
    if member_id is not None:
        await runtime.send_approval_dm(
            context,
            member_id,
            months,
            password,
            invite_url,
            package=package,
        )

    expiry = datetime.now(_BANGKOK).date() + timedelta(days=months * 30)
    password_line = (
        "🔑 Password ကို customer DM ထဲပို့ထားပါသည်။\n" if password else ""
    )
    text = (
        "✅ <b>Membership Approved!</b>\n\n"
        f"👤 @{member_username}\n"
        f"🆔 <code>{member_id if member_id is not None else 'N/A'}</code>\n"
        f"📦 Package: {runtime.PLAN_NAMES.get(package, package)}\n"
        f"📅 <b>{months} လ</b>\n"
        f"⏰ ကုန်ဆုံး: <code>{expiry.strftime('%d/%m/%Y')}</code>\n"
        f"{password_line}"
    )
    if invite_url:
        text += "📢 Channel invite ပို့ပြီးပါပြီ။"
    await update.message.reply_text(text, parse_mode="HTML")


def install() -> SimpleNamespace:
    """Install tested replacements before legacy_bot.main() registers handlers."""
    runtime = _runtime()
    replacements = SimpleNamespace(
        save_member_to_sheet=save_member_to_sheet_secure,
        is_active_member=is_active_member,
        get_member_package=get_member_package,
        is_valid_member=is_valid_member,
        activate_promo10d=activate_promo10d,
        approve_member=approve_member,
    )
    for name, value in vars(replacements).items():
        setattr(runtime, name, value)
    return replacements
