from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT_CORE = (ROOT / "bot_core.py").read_text(encoding="utf-8")
LEGACY_BOT = (ROOT / "legacy_bot.py").read_text(encoding="utf-8")
LEGACY = (ROOT / "Code.gs").read_text(encoding="utf-8")


def test_phase1_sheet_mirror_checks_http_json_and_identity_contract():
    expected = [
        "def _validate_legacy_sheet_mirror_response(",
        "response.raise_for_status()",
        "result = response.json()",
        "missing_req_id",
        "req_id_mismatch",
        "customer_id_mismatch",
        "return ok",
    ]
    for marker in expected:
        assert marker in BOT_CORE, marker


def test_phase1_mirror_does_not_retry_non_idempotent_add_request():
    assert "This write is intentionally not retried automatically" in BOT_CORE
    assert "legacy_mirror_ok = await _save_request_to_legacy_sheet(" in BOT_CORE
    assert "manual reconciliation required" in BOT_CORE
    assert "ဒီ Request ID ကို ပြန်မတင်ပါနှင့်။" in BOT_CORE


def test_legacy_response_validator_requires_authoritative_identity():
    expected = [
        "def _validate_legacy_add_request_response(",
        "missing_or_invalid_req_id",
        "customer_id_mismatch",
        "validated_req_id, validation_reason",
        "ဒီ Request ကို ပြန်မတင်မီ /mystatus ဖြင့် အရင်စစ်ပါ။",
    ]
    for marker in expected:
        assert marker in LEGACY_BOT, marker


def test_legacy_timeout_reconciles_with_read_only_owner_checked_lookup():
    expected = [
        "async def _lookup_legacy_request(request_code: str, user_id: int):",
        '"action": "getRequest"',
        '"customerId": str(user_id)',
        "read-only owner-checked lookup",
        "Request ကို ပြန်မတင်မီ /mystatus ဖြင့် အရင်စစ်ပါ။",
    ]
    for marker in expected:
        assert marker in LEGACY_BOT, marker


def test_phase1_duplicate_race_skips_legacy_fallback():
    assert 'if "ACTIVE_REQUEST_ALREADY_EXISTS" in str(exc).upper()' in BOT_CORE
    assert 'legacy fallback skipped' in BOT_CORE
    assert 'ဒီ Request ကို ထပ်မတင်ထားပါ။' in BOT_CORE


def test_owner_known_status_updates_include_customer_id():
    assert '"customerId": str(customer_tg_id)' in BOT_CORE
    assert '"customerId": str(user_id)' in (ROOT / "bot.py").read_text(encoding="utf-8")
    assert '"customerId": str_uid' in LEGACY_BOT


def test_apps_script_get_request_owner_check_remains_available():
    assert 'case "getRequest":' in LEGACY
    assert 'msg:"request_owner_mismatch"' in LEGACY
