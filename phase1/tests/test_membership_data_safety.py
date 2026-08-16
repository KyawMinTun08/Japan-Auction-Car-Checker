from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODE_GS = (ROOT / "Code.gs").read_text(encoding="utf-8")
LEGACY_BOT = (ROOT / "legacy_bot.py").read_text(encoding="utf-8")
APPROVAL_PATCH = (ROOT / "membership_approval_patch.py").read_text(encoding="utf-8")


def test_apps_script_save_member_has_operation_id_guard():
    assert 'data.operationId || ""' in CODE_GS
    assert "function _findMembershipOperation(operationId)" in CODE_GS
    assert 'result:"already_applied"' in CODE_GS
    assert 'operation_id_conflict' in CODE_GS


def test_apps_script_finance_logging_is_idempotent_and_exportable():
    assert "function logPayment(payment)" in CODE_GS
    assert "function getFinanceBackupCSV()" in CODE_GS
    assert "function getPaymentsBackupCSV()" in CODE_GS
    assert "function getRecoveryMembersCSV()" in CODE_GS
    assert 'case "getFinanceBackupCSV"' in CODE_GS
    assert 'case "getPaymentsBackupCSV"' in CODE_GS
    assert 'case "getRecoveryMembersCSV"' in CODE_GS
    assert 'case "getDuplicateMembers"' in CODE_GS
    assert 'if (!_serverKeyMatches(data))' in CODE_GS


def test_automatic_premium_password_rotation_is_disabled():
    start = CODE_GS.index("function monthlyPasswordReset()")
    end = CODE_GS.index("// ═══════════════════════════════════════════", start)
    monthly_reset = CODE_GS[start:end]
    assert "automatic Premium password rotation is disabled" in monthly_reset
    assert "setValue(pw)" not in monthly_reset
    assert "UrlFetchApp.fetch" not in monthly_reset


def test_bot_backup_covers_members_finance_and_duplicates():
    start = LEGACY_BOT.index("async def backup_cmd")
    end = LEGACY_BOT.index("async def upgrade_cmd", start)
    backup = LEGACY_BOT[start:end]
    assert 'getRecoveryMembersCSV' in backup
    assert 'getFinanceBackupCSV' in backup
    assert 'getPaymentsBackupCSV' in backup
    assert 'getDuplicateMembers' in backup
    assert 'SHEET_SERVER_KEY' in backup


def test_payment_admin_confirmation_uses_canonical_expiry_and_hides_password():
    start = LEGACY_BOT.index("member_snapshot = await get_member_snapshot", LEGACY_BOT.index('elif data.startswith("slip_ok_")'))
    end = LEGACY_BOT.index('elif data.startswith("slip_no_")', start)
    confirmation = LEGACY_BOT[start:end]
    assert "canonical_expire" in confirmation
    assert "get_member_snapshot" in confirmation
    assert 'Password: `{password}`' not in confirmation


def test_approval_retry_has_save_aware_duplicate_protection():
    assert "_approval_operation_id" in APPROVAL_PATCH
    assert 'payload["operationId"]' in APPROVAL_PATCH
    assert "Membership approval completed but post-save step failed" in APPROVAL_PATCH
    assert "never replay the write" in APPROVAL_PATCH
    assert "payment data restored user=%s error=%s" in APPROVAL_PATCH
