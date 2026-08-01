from __future__ import annotations

from pathlib import Path


PATCH = Path("phase2/apps_script_payment_approval_patch.gs")


def _source() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_payment_approval_uses_persistent_idempotency_ledger() -> None:
    source = _source()
    assert 'JACC_PAYMENT_APPROVAL_LEDGER = "Membership_Approval_Ledger"' in source
    assert '"IdempotencyKey"' in source
    assert '"TargetExpireDate"' in source
    assert '"ActualExpireDate"' in source
    assert "jaccPaymentFindLedger_" in source
    assert "jaccPaymentWriteLedger_" in source


def test_duplicate_completed_approval_does_not_save_member_again() -> None:
    source = _source()
    completed = source.split(
        'if (existing && existing.status === "COMPLETED")', 1
    )[1].split("var targetExpireDate", 1)[0]
    assert "saveMember(" not in completed
    assert "duplicate" in source


def test_partial_completion_recovery_checks_target_expiry() -> None:
    source = _source()
    assert 'existing.status === "PROCESSING"' in source
    assert "jaccPaymentDateAtLeast_" in source
    assert 'lastMessage: "recovered_after_partial_completion"' in source
    assert 'recovered: Boolean(recovered)' in source


def test_finance_log_is_idempotent() -> None:
    source = _source()
    assert 'sheet.getRange(1, 13).setValue("IdempotencyKey")' in source
    assert "jaccPaymentAppendFinanceOnce_" in source
    assert "if (jaccPaymentText_(existingKeys[i][0]) === idempotencyKey) return false" in source


def test_authoritative_member_expiry_is_returned() -> None:
    source = _source()
    assert "jaccPaymentMemberSnapshot_" in source
    assert "expireDate: ledger.actualExpireDate || member.expireDate" in source
    assert 'message: "authoritative_expiry_missing"' in source


def test_patch_requires_secure_atomic_do_post_route() -> None:
    source = _source()
    assert 'case "approveMembershipPayment"' in source
    assert "jaccApproveMembershipPayment_(data)" in source
    assert "doPost ScriptLock" in source
    assert "jaccMembershipPreflight_(data)" in source


def test_patch_contains_no_server_secret_or_password_literal() -> None:
    source = _source()
    assert "SHEET_SERVER_KEY" not in source
    assert "JACC_SERVER_KEY=" not in source
    assert "sk-" not in source
    assert "AIza" not in source
