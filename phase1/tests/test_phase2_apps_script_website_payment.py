from __future__ import annotations

from pathlib import Path

import pytest

from phase2.apply_apps_script_payment_gs import (
    PaymentScriptPatchError,
    apply_patch_text,
)


ADAPTER = Path("phase2/apps_script_website_payment_patch.gs")

CURRENT_PAYMENT_CONTRACT = """function checkPayment(data) {
  const r = [];
  return {
    ok: true,
    paymentId: r[0],
    registrationCode: r[1],
    telegramId: r[2],
    package: r[3],
    amount: r[4],
    method: r[5],
    slipUrl: r[6],
    status: r[7],
    submittedAt: r[8],
    approvedAt: r[9],
    adminNote: r[10]
  };
}

function approvePayment(data) {
  return jaccReviewPayment_(data.paymentId, true, data.adminNote || '');
}

function jaccReviewPayment_(paymentId, approved, adminNote) {
  const currentStatus = 'PENDING';
  if (currentStatus !== 'PENDING') {
    return { ok: false, error: 'PAYMENT_ALREADY_REVIEWED' };
  }
  if (approved) {
    activateMemberFromPayment({paymentId: paymentId});
  }
  return {ok:true};
}
"""


def _adapter() -> str:
    return ADAPTER.read_text(encoding="utf-8")


def test_adapter_uses_stable_payment_idempotency_key() -> None:
    source = _adapter()
    assert "Utilities.DigestAlgorithm.SHA_256" in source
    assert "return 'JACC-PAY-' + hex.slice(0, 32)" in source
    assert "idempotencyKey: jaccWebsitePaymentApprovalKey_(paymentId)" in source


def test_membership_activation_precedes_final_approval_and_dm() -> None:
    source = _adapter()
    activation = source.index("var activation = jaccApproveMembershipPayment_({")
    final_status = source.index("paySh.getRange(payRow, 8).setValue('APPROVED')")
    approval_dm = source.index("JACC Membership Approved")
    assert activation < final_status < approval_dm


def test_failed_activation_remains_retryable() -> None:
    source = _adapter()
    failure = source.split("if (!activation || activation.status !== 'ok')", 1)[1]
    failure = failure.split("paySh.getRange(payRow, 8).setValue('APPROVED')", 1)[0]
    assert "ACTIVATION_FAILED:" in failure
    assert "status:'PENDING'" in failure
    assert "setValue('APPROVED')" not in failure
    assert "JACC Membership Approved" not in failure


def test_web_renewal_does_not_rotate_existing_password() -> None:
    source = _adapter()
    assert "currentMember.package !== 'WEB'" in source
    assert "!currentMember.password" in source
    assert "password = generateJaccWebPassword_()" in source


def test_public_activation_response_excludes_password() -> None:
    source = _adapter()
    public = source.split("function jaccWebsitePaymentPublicActivation_", 1)[1]
    public = public.split("function jaccReviewWebsitePayment_", 1)[0]
    assert "password" not in public
    assert "expireDate" in public
    assert "package" in public


def test_transformer_delegates_and_redacts_public_status() -> None:
    patched = apply_patch_text(CURRENT_PAYMENT_CONTRACT)
    assert "return jaccReviewWebsitePayment_(paymentId, approved, adminNote);" in patched
    check = patched.split("function checkPayment", 1)[1].split(
        "function approvePayment", 1
    )[0]
    assert "telegramId: r[2]" not in check
    assert "slipUrl: r[6]" not in check
    assert "adminNote: r[10]" not in check
    assert "package: r[3]" in check
    assert apply_patch_text(patched) == patched


def test_transformer_refuses_unknown_payment_drift() -> None:
    with pytest.raises(PaymentScriptPatchError, match="checkPayment contract drift"):
        apply_patch_text(CURRENT_PAYMENT_CONTRACT.replace("slipUrl: r[6],", ""))
