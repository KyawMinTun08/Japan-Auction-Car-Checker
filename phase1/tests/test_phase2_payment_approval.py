from __future__ import annotations

import asyncio

import pytest

from phase2.payment_approval import (
    PaymentApprovalError,
    approve_pending_payment,
    build_idempotency_key,
    pending_payment_snapshot,
)


def _payment(**overrides):
    value = {
        "package": "WEB",
        "action": "renew",
        "months": 1,
        "amount": 30000,
        "method": "kpay",
        "username": "@member",
        "slip_info": {
            "TRANSACTION_NO": "TX 12345",
            "DATE": "01/08/2026",
            "TIME": "18:00",
            "AMOUNT": "30000",
            "SENDER": "Customer",
            "TRANSFER_TO": "JACC",
        },
    }
    value.update(overrides)
    return value


def test_idempotency_key_is_stable_and_transaction_scoped() -> None:
    first = build_idempotency_key(123, _payment())
    second = build_idempotency_key("123", _payment())
    different = build_idempotency_key(
        123,
        _payment(slip_info={"TRANSACTION_NO": "TX-999"}),
    )

    assert first == second
    assert first.startswith("JACC-PAY-")
    assert different != first
    assert "TX" not in first


def test_pending_snapshot_does_not_remove_retry_state() -> None:
    pending = {123: _payment()}
    snapshot = pending_payment_snapshot(pending, 123)
    snapshot["months"] = 9

    assert 123 in pending
    assert pending[123]["months"] == 1


def test_backend_failure_keeps_pending_payment() -> None:
    pending = {123: _payment()}

    async def post(*args, **kwargs):
        raise RuntimeError("sheet unavailable")

    async def password(*args, **kwargs):
        return "EXISTING"

    with pytest.raises(PaymentApprovalError, match="backend_unavailable"):
        asyncio.run(
            approve_pending_payment(
                member_id=123,
                pending_payment=pending,
                post_privileged_sheet=post,
                resolve_password=password,
            )
        )

    assert 123 in pending


def test_backend_rejection_keeps_pending_payment() -> None:
    pending = {123: _payment()}

    async def post(*args, **kwargs):
        return {"status": "error", "message": "member_schema_mismatch"}

    async def password(*args, **kwargs):
        return "EXISTING"

    with pytest.raises(PaymentApprovalError, match="member_schema_mismatch"):
        asyncio.run(
            approve_pending_payment(
                member_id=123,
                pending_payment=pending,
                post_privileged_sheet=post,
                resolve_password=password,
            )
        )

    assert 123 in pending


def test_missing_authoritative_expiry_keeps_pending_payment() -> None:
    pending = {123: _payment()}

    async def post(*args, **kwargs):
        return {"status": "ok", "package": "WEB"}

    async def password(*args, **kwargs):
        return "EXISTING"

    with pytest.raises(PaymentApprovalError, match="authoritative_expiry_missing"):
        asyncio.run(
            approve_pending_payment(
                member_id=123,
                pending_payment=pending,
                post_privileged_sheet=post,
                resolve_password=password,
            )
        )

    assert 123 in pending


def test_success_uses_backend_expiry_and_clears_same_payment() -> None:
    pending = {123: _payment()}
    captured = {}

    async def post(action: str, **fields):
        captured.update(action=action, fields=fields)
        return {
            "status": "ok",
            "expireDate": "15/10/2026",
            "package": "WEB",
            "password": "EXISTING",
        }

    async def password(user_id: str, package: str):
        assert (user_id, package) == ("123", "WEB")
        return "EXISTING"

    result = asyncio.run(
        approve_pending_payment(
            member_id=123,
            pending_payment=pending,
            post_privileged_sheet=post,
            resolve_password=password,
            package_names={"WEB": "Web Premium"},
        )
    )

    assert result.expire_date == "15/10/2026"
    assert result.package == "WEB"
    assert result.password == "EXISTING"
    assert result.duplicate is False
    assert 123 not in pending
    assert captured["action"] == "approveMembershipPayment"
    assert captured["fields"]["days"] == 30
    assert captured["fields"]["membershipAction"] == "renew"
    assert captured["fields"]["payment"]["transactionNo"] == "TX12345"
    assert captured["fields"]["idempotencyKey"].startswith("JACC-PAY-")


def test_duplicate_backend_success_is_treated_as_success() -> None:
    pending = {123: _payment()}

    async def post(*args, **kwargs):
        return {
            "status": "ok",
            "expireDate": "15/10/2026",
            "package": "WEB",
            "password": "EXISTING",
            "duplicate": True,
        }

    async def password(*args, **kwargs):
        return "EXISTING"

    result = asyncio.run(
        approve_pending_payment(
            member_id=123,
            pending_payment=pending,
            post_privileged_sheet=post,
            resolve_password=password,
        )
    )

    assert result.duplicate is True
    assert 123 not in pending


def test_newer_payment_is_not_removed_by_older_inflight_approval() -> None:
    original = _payment()
    newer = _payment(slip_info={"TRANSACTION_NO": "TX-NEW"})
    pending = {123: original}

    async def post(*args, **kwargs):
        pending[123] = newer
        return {
            "status": "ok",
            "expireDate": "15/10/2026",
            "package": "WEB",
            "password": "EXISTING",
        }

    async def password(*args, **kwargs):
        return "EXISTING"

    asyncio.run(
        approve_pending_payment(
            member_id=123,
            pending_payment=pending,
            post_privileged_sheet=post,
            resolve_password=password,
        )
    )

    assert pending[123] == newer
