"""Pure validation helpers for JACC payment approvals and member integrity."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_UNKNOWN = {"", "UNKNOWN", "N/A", "NONE", "NULL"}
_ALLOWED_ENTRY_TYPES = {"NEW", "RENEW", "UPGRADE", "MANUAL", "PROMO"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_amount(value: Any) -> int | None:
    """Return a positive integer amount, or None when unreadable."""
    text = _text(value).replace(",", "")
    if text.upper() in _UNKNOWN:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    try:
        amount = int(digits)
    except ValueError:
        return None
    return amount if amount > 0 else None


def normalize_method(value: Any) -> str:
    text = _text(value).upper()
    if "KPAY" in text or "KBZPAY" in text or "KBZ BANK" in text:
        return "KPAY"
    if "WAVE" in text:
        return "WAVE"
    if text == "CB" or "CB PAY" in text or "BANK" in text:
        return "CB"
    return text


def _normalise_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _reference(slip_info: dict[str, Any]) -> str:
    return _text(
        slip_info.get("TRANSACTION_NO")
        or slip_info.get("REFERENCE")
        or slip_info.get("TRANSACTION_ID")
    )


def validate_payment_slip(
    payment: dict[str, Any],
    slip_info: dict[str, Any],
    expected_receiver: str = "",
) -> dict[str, Any]:
    """Validate a receipt against the Bot-selected purchase before approval.

    This intentionally rejects incomplete or ambiguous slips rather than guessing.
    The check is deterministic and does not alter any member or Finance data.
    """
    expected = normalize_amount(payment.get("amount"))
    actual = normalize_amount(slip_info.get("AMOUNT"))
    if expected is None:
        return {"ok": False, "reason": "expected_amount_invalid"}
    if actual is None:
        return {"ok": False, "reason": "amount_unreadable"}
    if actual != expected:
        return {
            "ok": False,
            "reason": "amount_mismatch",
            "expected_amount": expected,
            "actual_amount": actual,
        }

    selected_method = normalize_method(payment.get("method"))
    slip_method = normalize_method(slip_info.get("TYPE"))
    if selected_method not in {"KPAY", "WAVE", "CB"}:
        return {"ok": False, "reason": "selected_method_invalid"}
    if slip_method != selected_method:
        return {
            "ok": False,
            "reason": "payment_method_mismatch",
            "selected_method": selected_method,
            "slip_method": slip_method,
        }

    transaction_no = _reference(slip_info)
    if transaction_no.upper() in _UNKNOWN or len(re.sub(r"\s+", "", transaction_no)) < 5:
        return {"ok": False, "reason": "transaction_missing"}

    date_text = _text(slip_info.get("DATE"))
    if date_text.upper() in _UNKNOWN:
        return {"ok": False, "reason": "date_missing"}
    try:
        datetime.strptime(date_text, "%d/%m/%Y")
    except ValueError:
        return {"ok": False, "reason": "date_invalid"}

    if selected_method == "KPAY" and expected_receiver:
        receiver = _normalise_name(slip_info.get("TRANSFER_TO"))
        configured = _normalise_name(expected_receiver)
        if not receiver or receiver in _UNKNOWN or configured not in receiver:
            return {"ok": False, "reason": "receiver_mismatch"}

    return {
        "ok": True,
        "amount": actual,
        "method": selected_method,
        "transaction_no": transaction_no,
        "date": date_text,
        "time": _text(slip_info.get("TIME")),
    }


def normalize_package(value: Any) -> str:
    text = _text(value).upper().replace("_", "-")
    if "WEB" in text or "PREMIUM" in text:
        return "WEB"
    if text in {"CH", "CHANNEL", "STANDARD", "CH-PROMO"} or "STANDARD" in text:
        return "CH"
    return text


def _parse_member_date(value: Any) -> datetime | None:
    """Parse Sheets display dates and Apps Script JavaScript Date strings."""
    text = _text(value)
    if text.upper() in _UNKNOWN:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            pass
    # Apps Script can serialize a Date cell through String(Date), for example:
    # Thu Jul 16 2026 00:00:00 GMT+0700 (Indochina Time).
    match = re.search(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})",
        text,
    )
    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)} {int(match.group(2)):02d} {match.group(3)}",
                "%b %d %Y",
            )
        except ValueError:
            return None
    return None


def validate_member_record(
    saved: dict[str, Any], requested_package: Any
) -> dict[str, Any]:
    """Validate the canonical member fields returned after saveMember."""
    if not isinstance(saved, dict) or saved.get("status") != "ok":
        return {"ok": False, "reason": "member_save_not_ok"}
    if not saved.get("canonicalMemberChecked"):
        return {"ok": False, "reason": str(saved.get("canonicalMemberError") or "member_not_verified")}

    expected_package = normalize_package(requested_package)
    actual_package = normalize_package(saved.get("package"))
    if expected_package != actual_package:
        return {
            "ok": False,
            "reason": "package_mismatch",
            "expected_package": expected_package,
            "actual_package": actual_package,
        }

    start_text = _text(saved.get("startDate"))
    expire_text = _text(saved.get("expireDate"))
    if start_text.upper() in _UNKNOWN or expire_text.upper() in _UNKNOWN:
        return {"ok": False, "reason": "member_date_missing"}
    start_date = _parse_member_date(start_text)
    expire_date = _parse_member_date(expire_text)
    if not start_date or not expire_date:
        return {"ok": False, "reason": "member_date_invalid"}
    if expire_date < start_date:
        return {"ok": False, "reason": "expire_before_start"}

    entry_type = _text(saved.get("entryType")).upper()
    if entry_type and entry_type not in _ALLOWED_ENTRY_TYPES:
        return {"ok": False, "reason": "entry_type_invalid"}
    if actual_package == "WEB" and not _text(saved.get("password")):
        return {"ok": False, "reason": "web_password_missing"}

    return {
        "ok": True,
        "startDate": start_date.strftime("%d/%m/%Y"),
        "expireDate": expire_date.strftime("%d/%m/%Y"),
        "package": actual_package,
        "entryType": entry_type,
    }


def validate_payment_batch(
    payment: dict[str, Any],
    slips: list[dict[str, Any]],
    expected_receiver: str = "",
) -> dict[str, Any]:
    """Validate one or more receipts that together pay for one package."""
    expected = normalize_amount(payment.get("amount"))
    if expected is None:
        return {"ok": False, "reason": "expected_amount_invalid"}
    if not slips:
        return {"ok": False, "reason": "payment_slips_missing"}

    selected_method = normalize_method(payment.get("method"))
    if selected_method not in {"KPAY", "WAVE", "CB"}:
        return {"ok": False, "reason": "selected_method_invalid"}

    total = 0
    transaction_numbers: list[str] = []
    for item in slips:
        info = item.get("slip_info", {}) if isinstance(item, dict) else {}
        actual = normalize_amount(info.get("AMOUNT"))
        if actual is None:
            return {"ok": False, "reason": "amount_unreadable"}
        slip_method = normalize_method(info.get("TYPE"))
        if slip_method != selected_method:
            return {
                "ok": False,
                "reason": "payment_method_mismatch",
                "selected_method": selected_method,
                "slip_method": slip_method,
            }
        transaction_no = _reference(info)
        if transaction_no.upper() in _UNKNOWN or len(re.sub(r"\s+", "", transaction_no)) < 5:
            return {"ok": False, "reason": "transaction_missing"}
        if transaction_no in transaction_numbers:
            return {"ok": False, "reason": "duplicate_transaction"}
        date_text = _text(info.get("DATE"))
        if date_text.upper() in _UNKNOWN:
            return {"ok": False, "reason": "date_missing"}
        try:
            datetime.strptime(date_text, "%d/%m/%Y")
        except ValueError:
            return {"ok": False, "reason": "date_invalid"}
        if selected_method == "KPAY" and expected_receiver:
            receiver = _normalise_name(info.get("TRANSFER_TO"))
            configured = _normalise_name(expected_receiver)
            if not receiver or receiver in _UNKNOWN or configured not in receiver:
                return {"ok": False, "reason": "receiver_mismatch"}
        transaction_numbers.append(transaction_no)
        total += actual

    if total != expected:
        return {
            "ok": False,
            "reason": "amount_mismatch",
            "expected_amount": expected,
            "actual_amount": total,
        }
    return {
        "ok": True,
        "amount": total,
        "method": selected_method,
        "transaction_numbers": transaction_numbers,
        "transaction_no": "|".join(transaction_numbers),
    }
