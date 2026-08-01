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


def test_duplicate_completed_approval_does_not_write_member_again() -> None:
    source = _source()
    completed = source.split(
        'if (existing && existing.status === "COMPLETED")', 1
    )[1].split("if (", 1)[0]
    assert "jaccPaymentApplyMemberWrite_" not in completed
    assert "duplicate" in source


def test_payment_write_does_not_depend_on_legacy_save_member_semantics() -> None:
    source = _source()
    assert "saveMember(" not in source
    assert "does not depend on the legacy saveMember()" in source
    assert "jaccPaymentApplyMemberWrite_" in source
    assert "targetExpireDate" in source
    assert "sheet.getRange(currentMember.row, 1, 1, 10).setValues(values)" in source
    assert "sheet.appendRow(values[0])" in source


def test_canonical_member_write_preserves_security_state() -> None:
    source = _source()
    assert "cancelCount = currentMember ? currentMember.cancelCount : 0" in source
    assert 'token = currentMember ? currentMember.token : ""' in source
    assert 'deviceId = currentMember ? currentMember.deviceId : ""' in source
    assert 'packageName === "WEB"' in source
    assert 'message: "web_password_required"' in source
    assert '"ACTIVE"' in source
    assert 'message: "authoritative_expiry_mismatch"' in source
    assert 'message: "authoritative_package_mismatch"' in source


def test_partial_completion_recovery_checks_target_expiry_and_package() -> None:
    source = _source()
    assert 'existing.status === "PROCESSING"' in source
    assert "jaccPaymentDateAtLeast_" in source
    assert "currentMember.package === existing.package" in source
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
    assert "jaccPaymentDateAtLeast_(authoritative.expireDate, targetExpireDate)" in source


def test_patch_reuses_existing_do_post_lock_without_deadlock() -> None:
    source = _source()
    assert "LockService.getScriptLock()" in source
    assert "if (!lock.hasLock())" in source
    assert "lock.waitLock(30000)" in source
    assert "releaseHere = true" in source
    assert "if (releaseHere) lock.releaseLock()" in source
    assert 'message: "payment_lock_busy"' in source


def test_patch_requires_secure_atomic_do_post_route() -> None:
    source = _source()
    assert 'case "approveMembershipPayment"' in source
    assert "jaccApproveMembershipPayment_(data)" in source
    assert "after jaccMembershipPreflight_(data)" in source


def test_patch_contains_no_server_secret_or_password_literal() -> None:
    source = _source()
    assert "SHEET_SERVER_KEY" not in source
    assert "JACC_SERVER_KEY=" not in source
    assert "sk-" not in source
    assert "AIza" not in source
