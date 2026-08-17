import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from payment_audit import validate_member_record, validate_payment_slip


def _payment(**overrides):
    data = {
        "amount": 30000,
        "method": "kpay",
        "package": "WEB",
        "months": 1,
    }
    data.update(overrides)
    return data


def _slip(**overrides):
    data = {
        "TYPE": "KPay",
        "AMOUNT": "30000",
        "TRANSACTION_NO": "01004243091299950069",
        "DATE": "14/08/2026",
        "TIME": "15:17",
        "TRANSFER_TO": "U KYAW MIN TUN",
    }
    data.update(overrides)
    return data


def test_valid_payment_slip_requires_exact_amount_and_canonical_fields():
    result = validate_payment_slip(_payment(), _slip(), expected_receiver="Kyaw Min Tun")
    assert result["ok"] is True
    assert result["amount"] == 30000
    assert result["method"] == "KPAY"
    assert result["transaction_no"] == "01004243091299950069"


def test_amount_overpayment_is_not_silently_accepted():
    result = validate_payment_slip(_payment(), _slip(AMOUNT="30001"), expected_receiver="Kyaw Min Tun")
    assert result["ok"] is False
    assert result["reason"] == "amount_mismatch"


def test_amount_underpayment_is_not_accepted():
    result = validate_payment_slip(_payment(), _slip(AMOUNT="29999"), expected_receiver="Kyaw Min Tun")
    assert result["ok"] is False
    assert result["reason"] == "amount_mismatch"


def test_missing_transaction_and_invalid_date_fail_closed():
    missing_tx = validate_payment_slip(_payment(), _slip(TRANSACTION_NO="UNKNOWN"), expected_receiver="Kyaw Min Tun")
    assert missing_tx["reason"] == "transaction_missing"
    invalid_date = validate_payment_slip(_payment(), _slip(DATE="UNKNOWN"), expected_receiver="Kyaw Min Tun")
    assert invalid_date["reason"] == "date_missing"


def test_method_and_receiver_mismatch_fail_closed():
    method = validate_payment_slip(_payment(method="wave"), _slip(), expected_receiver="Kyaw Min Tun")
    assert method["reason"] == "payment_method_mismatch"
    receiver = validate_payment_slip(_payment(), _slip(TRANSFER_TO="Someone Else"), expected_receiver="Kyaw Min Tun")
    assert receiver["reason"] == "receiver_mismatch"


def test_wave_does_not_require_kpay_receiver_name():
    result = validate_payment_slip(
        _payment(method="wave"),
        _slip(TYPE="Wave", TRANSFER_TO="UNKNOWN"),
        expected_receiver="Kyaw Min Tun",
    )
    assert result["ok"] is True


def test_canonical_web_member_record_requires_verified_dates_and_password():
    saved = {
        "status": "ok",
        "canonicalMemberChecked": True,
        "startDate": "14/08/2026",
        "expireDate": "13/09/2026",
        "package": "WEB",
        "password": "stable-pass",
        "entryType": "NEW",
    }
    result = validate_member_record(saved, "WEB")
    assert result["ok"] is True
    assert result["expireDate"] == "13/09/2026"


def test_canonical_member_date_and_package_mismatches_fail_closed():
    bad_date = validate_member_record(
        {
            "status": "ok",
            "canonicalMemberChecked": True,
            "startDate": "14/08/2026",
            "expireDate": "13/08/2026",
            "package": "WEB",
            "password": "stable-pass",
            "entryType": "NEW",
        },
        "WEB",
    )
    assert bad_date["reason"] == "expire_before_start"

    bad_package = validate_member_record(
        {
            "status": "ok",
            "canonicalMemberChecked": True,
            "startDate": "14/08/2026",
            "expireDate": "13/09/2026",
            "package": "CH",
            "password": "",
            "entryType": "NEW",
        },
        "WEB",
    )
    assert bad_package["reason"] == "package_mismatch"


def test_unverified_member_record_is_not_accepted():
    result = validate_member_record({"status": "ok"}, "CH")
    assert result["reason"] == "member_not_verified"
