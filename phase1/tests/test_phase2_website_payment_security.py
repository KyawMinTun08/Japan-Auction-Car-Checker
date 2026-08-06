from __future__ import annotations

from pathlib import Path


SECURITY = Path("phase2/apps_script_membership_security_patch.gs")
PROXY = Path("phase2/legacy_sheet_auth.py")


def test_apps_script_requires_server_key_for_payment_review() -> None:
    source = SECURITY.read_text(encoding="utf-8")
    privileged = source.split(
        "var JACC_PRIVILEGED_MEMBER_ACTIONS = {", 1
    )[1].split("};", 1)[0]
    assert "approvePayment: true" in privileged
    assert "rejectPayment: true" in privileged
    assert "submitPayment: true" not in privileged
    assert "checkPayment: true" not in privileged


def test_railway_proxy_authenticates_payment_review_only() -> None:
    source = PROXY.read_text(encoding="utf-8")
    protected = source.split("_PROTECTED_ACTIONS = frozenset(", 1)[1].split(
        ")\n\n_legacy", 1
    )[0]
    assert '"approvePayment"' in protected
    assert '"rejectPayment"' in protected
    assert '"submitPayment"' not in protected
    assert '"checkPayment"' not in protected
