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


def test_qa_quick_approve_handler_is_removed() -> None:
    """The qa_ callback bypassed Finance entirely (raw save_member_to_sheet,
    no admin check, no duplicate protection) and had no live button pointing
    at it anywhere in the codebase. It must stay removed."""
    bot = LEGACY.read_text(encoding="utf-8")
    assert 'elif data.startswith("qa_")' not in bot


def test_redeem_checks_finance_log_result() -> None:
    """A promo redemption grants membership first, then logs a Finance row.
    log_finance_entry() can still fail after its own retries; redeem_cmd
    must notice and alert an admin instead of silently losing the audit
    trail while telling the user everything succeeded."""
    bot = LEGACY.read_text(encoding="utf-8")
    redeem_cmd = bot[bot.index("async def redeem_cmd"):bot.index("# ── Auto Timer")]
    assert "finance_logged = await log_finance_entry(" in redeem_cmd
    assert "if not finance_logged:" in redeem_cmd
    assert "no Finance" in redeem_cmd


def test_paymethod_selection_persists_draft_before_slip_is_sent() -> None:
    """pending_payment (package/period/method) lived only in process memory
    until the first slip was processed. A bot restart (deploy) in between
    dropped it silently, and the member's already-sent slip then got
    rejected by the admin-only OCR gate. The method-selection step must now
    save a draft immediately so a restart can restore it."""
    bot = LEGACY.read_text(encoding="utf-8")
    paymethod_cb = bot[bot.index('elif data.startswith("paymethod_")'):bot.index('elif data.startswith("setqr_")')]
    assert 'pending_payment[user_id]["waiting_slip"] = True' in paymethod_cb
    assert 'pending_payment[user_id]["userId"]' in paymethod_cb
    assert "await save_payment_draft(pending_payment[user_id])" in paymethod_cb


def test_payment_slip_approval_is_strict_and_fail_closed() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    assert "validate_payment_batch(" in bot
    assert "expected_receiver=ADMIN_REAL_NAME" in bot
    assert "strict=True" in bot
    assert "transaction_already_used" in bot
    assert "Approve ကို ထပ်မနှိပ်ပါနှင့်" in bot
    assert '"source": "PAYMENT_SLIP"' in bot
    assert "for attempt in range(1, 4)" in bot


def test_upgrade_blocks_existing_web_premium_accounts() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    flow_guard = bot[bot.index("async def validate_payment_flow"):bot.index("async def resolve_payment_action")]
    upgrade_cmd = bot[bot.index("async def upgrade_cmd"):bot.index("# ── NEW: Broker Session Selector")]
    package_button = bot[bot.index('elif data.startswith("pkg_")'):bot.index('elif data.startswith("period_")')]

    assert 'normalized_action == "upgrade"' in flow_guard
    assert 'normalized_package in ("WEB", "WEBPROMO")' in flow_guard
    assert '"reason": "already_premium"' in flow_guard
    assert "Web Premium ဖြစ်ပြီးသားပါ" in upgrade_cmd
    assert "သက်တမ်းတိုးလိုပါက `/renew`" in upgrade_cmd
    assert 'flow.get("reason") == "already_premium"' in package_button
    assert 'Package Upgrade — ရှိပြီးသား Member သီးသန့်' in upgrade_cmd


def test_manual_approve_uses_atomic_idempotent_endpoint() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    approve_cmd = bot[bot.index("async def approve_member"):bot.index("async def members_list")]

    assert '"action": "approveManualMember"' in bot
    assert "approve_manual_member_transaction" in approve_cmd
    assert "operation_bucket" in approve_cmd
    assert "Finance row အသစ် မဖန်တီးထားပါ" in approve_cmd
    assert "save_member_to_sheet(" not in approve_cmd
    assert "log_finance_entry(" not in approve_cmd


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


def test_payment_approval_uses_atomic_idempotent_flow() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    assert "async def approve_payment_transaction" in bot
    assert "atomic_result = await approve_payment_transaction(atomic_payment)" in bot
    assert "await clear_payment_draft(member_id, transaction_no)" in bot
    assert "transaction_result = await approve_payment_transaction(transaction_payload)" not in bot
    assert "pending_payment.pop(member_id, None)" in bot


def test_payment_callback_acknowledges_before_durable_restore() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    callback = patch[patch.index("async def button_callback"):patch.index("# The legacy main function")]
    legacy = LEGACY.read_text(encoding="utf-8")
    legacy_callback = legacy[legacy.index("async def button_callback"):legacy.index("# ── 🚗 Buying Car 10 Day Promo ──")]

    assert callback.index("await query.answer()") < callback.index("asyncio.wait_for(")
    assert "_jacc_callback_answered" in callback
    assert "_jacc_callback_answered" in legacy_callback


def test_yes_approve_restores_durable_payment_draft() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    approval = bot[bot.index('elif data.startswith("slip_ok_")'):bot.index('elif data.startswith("slip_no_")')]
    assert "pay_data = await ensure_payment_session(member_id)" in approval
    assert 'pay_data = pending_payment.get(member_id, {})' not in approval
    assert "Payment draft မတွေ့ပါ" in approval


def test_payment_rejection_retries_the_original_flow() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    helper = bot[bot.index("def payment_retry_command"):bot.index("# ── 10 Day Promo Helpers")]
    reject = bot[bot.index('elif data.startswith("slip_no_")'):bot.index('elif data.startswith("uid_ok_")')]

    assert '"join": "/newmember"' in helper
    assert '"renew": "/renew"' in helper
    assert '"upgrade": "/upgrade"' in helper
    assert "pay_data = await ensure_payment_session(member_id)" in reject
    assert "retry_action, _ = await resolve_payment_action(member_id, pay_data)" in reject
    assert "retry_command = payment_retry_command(retry_action)" in reject
    assert "ပြန်လည် ကြိုးစားရန် /renew" not in reject
    assert "ဒီ payment ၏ flow ကို မသတ်မှတ်နိုင်သေးပါ" in reject


def test_missing_payment_draft_fails_closed_without_resend_request() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    approval = bot[bot.index('elif data.startswith("slip_ok_")'):bot.index('elif data.startswith("slip_no_")')]

    assert "Payment_Drafts/Finance record" in approval
    assert "Member ကို slip ထပ်မပို့ခိုင်းသေးပါနှင့်" in approval
    assert "Member ကို slip ပြန်ပို့ခိုင်းပါ" not in approval


def test_approval_callback_does_not_block_on_sheet_password_lookup() -> None:
    patch = PATCH.read_text(encoding="utf-8")
    save_block = patch[patch.index("async def save_member_to_sheet"):patch.index("async def send_approval_dm")]
    dm_block = patch[patch.index("async def send_approval_dm"):patch.index("async def button_callback")]
    callback_block = patch[patch.index("async def button_callback"):patch.index("# The legacy main function")]

    # Telegram callback queries expire while the handler is waiting. Apps
    # Script saveMember already preserves an existing Web password and returns
    # the effective password, so no pre/post approval lookup belongs here.
    assert "await _fetch_sheet_member" not in save_block
    assert "await _fetch_sheet_member" not in dm_block
    assert "await _fetch_sheet_member" not in callback_block
    assert "await _original_button_callback(update, context)" in callback_block
    assert "_PAYMENT_DRAFT_RESTORE_TIMEOUT_SECONDS = 3.0" in patch
    assert "asyncio.wait_for(" in callback_block
    assert "continuing without network wait" in callback_block


def test_photo_car_ocr_is_admin_only_but_payment_slip_flow_remains_available() -> None:
    bot = LEGACY.read_text(encoding="utf-8")
    payment_mode = bot.index("# ── Payment Slip Mode ──")
    slip_ocr = bot.index("slip_info  = await gemini_read_slip(file_bytes)", payment_mode)
    gate = bot.index("# ── Admin-only Car/List OCR Mode ──")
    list_mode = bot.index("# ── Auction List Mode ──")
    car_ocr = bot.index("result     = await gemini_ocr_chassis(file_bytes)")
    gate_block = bot[gate:list_mode]

    assert payment_mode < slip_ocr < gate
    assert "if user_id not in ADMIN_IDS:" in gate_block
    assert "AI Car OCR / Chassis" in gate_block
    assert "Payment slip ဖြစ်ပါက" in gate_block
    assert gate < list_mode < car_ocr
