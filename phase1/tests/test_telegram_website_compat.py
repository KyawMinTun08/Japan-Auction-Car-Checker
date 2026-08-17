from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy_bot.py"
QUEUE = ROOT / "queue_launcher.py"
PATCH = ROOT / "membership_approval_patch.py"
CODE = ROOT / "Code.gs"
INDEX = ROOT / "index.html"


def test_website_and_apps_script_contract_stays_unchanged() -> None:
    web = INDEX.read_text(encoding="utf-8")
    apps_script = CODE.read_text(encoding="utf-8")
    assert 'JACCDeviceBinding.withDevice(\'verifyLogin\'' in web
    assert 'verifyStoredSession' in web
    assert 'withDevice(\'verifyLogin\'' in web
    assert 'case "saveMember":' in apps_script
    assert 'data.userId, data.username, data.days' in apps_script
    assert 'case "getPassword":' in apps_script
    assert 'case "verifyToken":' in apps_script
    assert 'package:    _normalizePackage(rows[i][C_PACKAGE])' in apps_script
    assert 'expireDate: Utilities.formatDate(expireDate' in apps_script


def test_bot_uses_canonical_save_response_for_approval_and_renewal() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    assert ') -> dict:' in bot[bot.index('async def save_member_to_sheet'):bot.index('async def create_invite_link')]
    assert 'saved = await enrich_member_save_result' in bot
    assert 'canonical_password = str(saved.get("password") or password or "")' in bot
    assert 'canonical_expire = str(saved.get("expireDate") or "")' in bot
    assert 'package=canonical_package, expire_date=canonical_expire' in bot
    assert 'if saved.get("status") != "ok":' in bot


def test_promo_payload_matches_apps_script_days_contract() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    promo = bot[bot.index('async def activate_promo10d'):bot.index('def generate_password')]
    assert '"days":     10' in promo
    assert '"startDate"' not in promo
    assert '"expireDate"' not in promo


def test_railway_wrappers_preserve_structured_result_and_expiry() -> None:
    queue = QUEUE.read_text(encoding="utf-8")
    patch = PATCH.read_text(encoding="utf-8")
    assert ') -> dict:' in queue[queue.index('async def save_member_to_sheet'):queue.index('async def send_approval_dm')]
    assert 'expire_date: str = ""' in queue
    assert 'expire_date = expire_date or' in queue
    assert ') -> dict:' in patch[patch.index('async def save_member_to_sheet'):patch.index('async def send_approval_dm')]
    assert 'return canonical' in patch
    assert 'expire_date=expire_date' in patch
    assert 'return {"status": "error", "message": last_detail}' in patch


def test_standard_paths_do_not_advertise_a_web_password() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    quick = bot[bot.index('elif data.startswith("qa_")'):bot.index('elif data.startswith("req_budget_")')]
    assert '"CH")' in quick
    assert 'Password: `{password}`' not in quick


def test_payment_slip_approval_is_strict_and_fail_closed() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    assert "validate_payment_batch(" in bot
    assert "expected_receiver=ADMIN_REAL_NAME" in bot
    assert "strict=True" in bot
    assert "Duplicate renewal မဖြစ်စေရန် Approve ကို ထပ်မနှိပ်ပါနဲ့" in bot
    assert '"source": "PAYMENT_SLIP"' in bot
    assert "for attempt in range(1, 4)" in bot


def test_finance_slip_logging_requires_amount_and_transaction() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    helper = bot[bot.index("async def log_finance_entry"):bot.index("async def get_finance_report")]
    assert 'source == "PAYMENT_SLIP"' in helper
    assert "transaction number" in helper
    assert "numeric amount" in helper
    assert 'result.get("duplicate") is True' in helper


def test_member_integrity_verification_includes_start_and_expire_dates() -> None:
    audit = (ROOT / "payment_audit.py").read_text(encoding="utf-8")
    assert 'saved.get("startDate")' in audit
    assert 'saved.get("expireDate")' in audit
    assert 'reason": "expire_before_start"' in audit
    assert 'reason": "web_password_missing"' in audit
