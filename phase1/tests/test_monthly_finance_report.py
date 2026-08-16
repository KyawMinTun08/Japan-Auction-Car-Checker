from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "Code.gs"
BOT = ROOT / "legacy_bot.py"


def test_members_columns_remain_unchanged() -> None:
    code = CODE.read_text(encoding="utf-8")
    expected = {
        "var C_USERID   = 0;",
        "var C_USERNAME = 1;",
        "var C_START    = 2;",
        "var C_EXPIRE   = 3;",
        "var C_STATUS   = 4;",
        "var C_CANCELCOUNT = 5;",
        "var C_PASSWORD = 6;",
        "var C_PACKAGE  = 7;",
        "var C_TOKEN    = 8;",
    }
    assert expected.issubset(set(code.splitlines()))


def test_apps_script_finance_report_is_protected_and_month_scoped() -> None:
    code = CODE.read_text(encoding="utf-8")
    assert 'case "getFinanceReport":' in code
    assert '_authorizeFinanceReport_(data.serverKey)' in code
    assert 'getProperty("JACC_SERVER_KEY")' in code
    assert 'message:"server_key_not_configured"' in code
    assert 'message:"unauthorized"' in code
    assert 'if (!/^\\d{4}-(0[1-9]|1[0-2])$/.test(monthText))' in code
    assert 'dateKey.slice(0, 7) !== monthText' in code


def test_finance_ledger_keeps_legacy_columns_and_adds_audit_fields() -> None:
    code = CODE.read_text(encoding="utf-8")
    assert '"Date","Time","UserID","Username","Package","Months"' in code
    assert '"Amount(Ks)","PayType","TransactionNo","TransferTo","Sender","Status"' in code
    assert '"EntryType","Source","PaymentID","ApprovedBy","ExpireDate","Note"' in code
    assert 'bySource: {PAYMENT_SLIP:0, MANUAL:0, PROMO:0, OTHER:0}' in code
    assert 'fp.entryType || ""' in code
    assert 'fp.source || "PAYMENT_SLIP"' in code
    assert 'fp.approvedBy || ""' in code
    assert 'fp.expireDate || ""' in code


def test_duplicate_transaction_is_not_appended_twice() -> None:
    code = CODE.read_text(encoding="utf-8")
    assert 'var paymentId = String(fp.paymentId || fp.transactionNo || "").trim();' in code
    assert 'result:"duplicate", duplicate:true' in code
    assert 'existingTransaction === paymentId || existingPaymentId === paymentId' in code


def test_bot_finance_command_is_admin_only_and_uses_server_key() -> None:
    bot = BOT.read_text(encoding="utf-8")
    assert 'SHEET_SERVER_KEY      = os.environ.get' in bot
    assert 'async def get_finance_report(month: str) -> dict:' in bot
    assert 'async def finance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):' in bot
    assert 'if not ADMIN_IDS or user_id not in ADMIN_IDS:' in bot
    assert '"action": "getFinanceReport"' in bot
    assert '"serverKey": SHEET_SERVER_KEY' in bot
    assert 'CommandHandler("finance",     finance_cmd)' in bot
    assert 'BotCommand("finance",       "📊 Monthly Finance Report (Admin)")' in bot


def test_bot_records_activity_type_for_payment_manual_and_promo_paths() -> None:
    bot = BOT.read_text(encoding="utf-8")
    assert '"entryType": entry_type' in bot
    assert '"source": "PAYMENT_SLIP"' in bot
    assert '"status": "NO_PAYMENT"' in bot
    assert '"source": "MANUAL"' in bot
    assert '"status": "PROMO"' in bot
    assert '"source": "PROMO"' in bot
