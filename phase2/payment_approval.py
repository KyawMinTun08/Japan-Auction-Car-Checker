"""Retry-safe Phase 2 membership payment approval contract.

This module is staged only. The legacy Telegram callback must call
``approve_pending_payment`` instead of popping ``pending_payment`` before the
backend write. The backend action is intentionally atomic and idempotent:
``approveMembershipPayment``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, MutableMapping

from phase2_membership_guard import normalise_member_package


class PaymentApprovalError(RuntimeError):
    """Raised when an approval must remain pending for a safe retry."""


@dataclass(frozen=True)
class PaymentApprovalResult:
    idempotency_key: str
    expire_date: str
    package: str
    password: str
    duplicate: bool = False


def _text(value: object) -> str:
    return str(value or "").strip()


def _slip_info(payment: dict[str, Any]) -> dict[str, Any]:
    value = payment.get("slip_info") or {}
    return value if isinstance(value, dict) else {}


def transaction_number(payment: dict[str, Any]) -> str:
    slip = _slip_info(payment)
    return _text(
        slip.get("TRANSACTION_NO")
        or slip.get("REFERENCE")
        or payment.get("transactionNo")
    ).upper().replace(" ", "")


def build_idempotency_key(member_id: int | str, payment: dict[str, Any]) -> str:
    """Return a stable non-secret key for one payment approval.

    A bank transaction/reference number is preferred. When OCR did not find
    one, a deterministic fingerprint of the immutable payment fields is used.
    The key never contains a password or server credential.
    """
    member = _text(member_id).replace(".0", "")
    tx = transaction_number(payment)
    if tx:
        material = f"jacc-payment-v1|member={member}|tx={tx}"
    else:
        slip = _slip_info(payment)
        fields = (
            member,
            normalise_member_package(payment.get("package")),
            _text(payment.get("months")),
            _text(slip.get("AMOUNT") or payment.get("amount")),
            _text(payment.get("method")).upper(),
            _text(slip.get("DATE")),
            _text(slip.get("TIME")),
            _text(slip.get("SENDER")),
            _text(slip.get("TRANSFER_TO") or slip.get("RECEIVER")),
        )
        material = "jacc-payment-v1|" + "|".join(fields)
    return "JACC-PAY-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def pending_payment_snapshot(
    pending_payment: MutableMapping[int, dict[str, Any]],
    member_id: int,
) -> dict[str, Any]:
    """Read a copy without deleting the retry state."""
    value = pending_payment.get(int(member_id))
    if not isinstance(value, dict) or not value:
        raise PaymentApprovalError("payment_session_missing")
    return dict(value)


def clear_pending_payment_after_success(
    pending_payment: MutableMapping[int, dict[str, Any]],
    member_id: int,
    approved_key: str,
) -> bool:
    """Delete only the same payment that the backend completed.

    A customer may start a newer payment while an older backend request is in
    flight. In that case the newer session must not be removed.
    """
    current = pending_payment.get(int(member_id))
    if not isinstance(current, dict) or not current:
        return False
    if build_idempotency_key(member_id, current) != approved_key:
        return False
    pending_payment.pop(int(member_id), None)
    return True


def build_payment_record(
    member_id: int,
    payment: dict[str, Any],
    *,
    package_label: str,
) -> dict[str, Any]:
    slip = _slip_info(payment)
    method = _text(payment.get("method")).upper()
    return {
        "date": _text(slip.get("DATE")),
        "time": _text(slip.get("TIME")),
        "userId": str(int(member_id)),
        "username": _text(payment.get("username")),
        "package": package_label,
        "months": int(payment.get("months") or 1),
        "amount": slip.get("AMOUNT") or payment.get("amount") or "",
        "payType": _text(slip.get("TYPE")),
        "method": method,
        "transactionNo": transaction_number(payment),
        "receiver": _text(slip.get("TRANSFER_TO") or slip.get("RECEIVER")),
        "sender": _text(slip.get("SENDER")),
        "status": "APPROVED",
    }


async def approve_pending_payment(
    *,
    member_id: int,
    pending_payment: MutableMapping[int, dict[str, Any]],
    post_privileged_sheet: Callable[..., Awaitable[dict[str, Any]]],
    resolve_password: Callable[[str, str], Awaitable[str]],
    package_names: dict[str, str] | None = None,
) -> PaymentApprovalResult:
    """Approve once, preserve retry state on failure, and trust backend expiry."""
    snapshot = pending_payment_snapshot(pending_payment, member_id)
    package = normalise_member_package(snapshot.get("package"))
    if package not in {"CH", "WEB"}:
        raise PaymentApprovalError("invalid_package")

    try:
        months = int(snapshot.get("months") or 1)
    except (TypeError, ValueError) as exc:
        raise PaymentApprovalError("invalid_months") from exc
    if months < 1 or months > 12:
        raise PaymentApprovalError("invalid_months")

    key = build_idempotency_key(member_id, snapshot)
    username = _text(snapshot.get("username") or member_id).replace("@", "")
    password = await resolve_password(str(member_id), package)
    labels = package_names or {}
    payment_record = build_payment_record(
        member_id,
        snapshot,
        package_label=labels.get(package, package),
    )

    try:
        response = await post_privileged_sheet(
            "approveMembershipPayment",
            idempotencyKey=key,
            userId=str(member_id),
            username=username,
            days=months * 30,
            months=months,
            password=password,
            package=package,
            membershipAction=_text(snapshot.get("action") or "renew").lower(),
            payment=payment_record,
        )
    except Exception as exc:
        raise PaymentApprovalError("backend_unavailable") from exc

    if _text(response.get("status")).lower() != "ok":
        message = _text(response.get("message") or response.get("msg") or "backend_rejected")
        raise PaymentApprovalError(message)

    expire_date = _text(
        response.get("expireDate")
        or response.get("expiredDate")
        or response.get("expiry")
    )
    if not expire_date:
        # Do not clear pending state or show a guessed date. Admin can retry.
        raise PaymentApprovalError("authoritative_expiry_missing")

    actual_package = normalise_member_package(response.get("package") or package)
    actual_password = _text(
        response.get("password") if response.get("password") is not None else password
    )
    result = PaymentApprovalResult(
        idempotency_key=key,
        expire_date=expire_date,
        package=actual_package,
        password=actual_password,
        duplicate=bool(response.get("duplicate")),
    )

    clear_pending_payment_after_success(pending_payment, member_id, key)
    return result
