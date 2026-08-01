from __future__ import annotations

from pathlib import Path

import pytest

from phase2.apply_apps_script_phase3_payments_gs import (
    Phase3PaymentPatchError,
    apply_patch_text,
)


PATCH = Path("phase2/apps_script_phase3_payment_patch.gs")
SECURITY = Path("phase2/apps_script_membership_security_patch.gs")
AUTH_PROXY = Path("phase2/legacy_sheet_auth.py")

CURRENT_PHASE3_CONTRACT = r'''function handlePhase3PaymentAction_(body) {
  const action = String(body.action || '').trim();
  if (action === 'submitWebPayment') return submitWebPayment_(body);
  if (action === 'getWebPaymentStatus') return getWebPaymentStatus_(body.paymentId, body.userId);
  if (action === 'approveWebPayment') return approveWebPayment_(body.paymentId, body.adminId);
  if (action === 'rejectWebPayment') return rejectWebPayment_(body.paymentId, body.adminId, body.reason);
  return null;
}

function submitWebPayment_(body) {
  const paymentId = 'WP-OLD';
  const slipUrl = savePaymentSlip_(paymentId, body.slipBase64, body.mimeType);
  return {ok:true, paymentId:paymentId, slipUrl:slipUrl};
}

function getWebPaymentStatus_(paymentId, userId) {
  return {ok:true, paymentId:paymentId};
}

function approveWebPayment_(paymentId, adminId) {
  const password = generateWebPassword_();
  saveMember('1', 'user', 30, password, 'WEB');
  return {ok:true, password:password};
}

function rejectWebPayment_(paymentId, adminId, reason) {
  return {ok:true, status:'REJECTED'};
}

function getPaymentSheet_() { return {}; }
function savePaymentSlip_(paymentId, dataUrl, mimeType) { return ''; }
function notifyPaymentAdmin_(payment) { return true; }
function sendPaymentTelegramMessage_(chatId, text) { return true; }
'''


def _patch() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_transformer_delegates_all_four_phase3_routes() -> None:
    patched = apply_patch_text(CURRENT_PHASE3_CONTRACT)

    assert "return jaccSubmitPhase3WebPayment_(body);" in patched
    assert "return jaccGetPhase3WebPaymentStatus_(paymentId, userId);" in patched
    assert 'return jaccReviewPhase3WebPayment_(paymentId, true, adminId, "");' in patched
    assert "return jaccReviewPhase3WebPayment_(paymentId, false, adminId, reason);" in patched
    assert "saveMember(" not in patched
    assert "password:password" not in patched
    assert apply_patch_text(patched) == patched


def test_transformer_refuses_unknown_source_drift() -> None:
    with pytest.raises(Phase3PaymentPatchError, match="contract drift"):
        apply_patch_text(
            CURRENT_PHASE3_CONTRACT.replace(
                "function approveWebPayment_(paymentId, adminId) {",
                "function approveWebPayment_(paymentId) {",
            )
        )


def test_submit_validation_is_bounded_and_public_response_redacted() -> None:
    source = _patch()

    assert 'return {ok:false, error:"INVALID_USER_ID"}' in source
    assert 'return {ok:false, error:"INVALID_PACKAGE"}' in source
    assert 'return {ok:false, error:"INVALID_MONTHS"}' in source
    assert 'return {ok:false, error:"INVALID_AMOUNT"}' in source
    assert 'return {ok:false, error:"INVALID_METHOD"}' in source
    assert 'return {ok:false, error:"INVALID_SLIP_TYPE"}' in source
    assert "5 * 1024 * 1024" in source
    assert "jaccPhase3PendingForUser_" in source
    assert 'warning = "ADMIN_NOTIFICATION_FAILED"' in source

    submit_response = source.split("function jaccSubmitPhase3WebPayment_", 1)[1].split(
        "function jaccGetPhase3WebPaymentStatus_", 1
    )[0]
    success_return = submit_response.rsplit("return {", 1)[1]
    assert "slipUrl" not in success_return


def test_status_requires_owner_and_hides_non_owner_existence() -> None:
    source = _patch()
    status = source.split("function jaccGetPhase3WebPaymentStatus_", 1)[1].split(
        "function jaccPhase3Password_", 1
    )[0]

    assert "INVALID_STATUS_REQUEST" in status
    assert 'error:"PAYMENT_NOT_FOUND"' in status
    assert "row.values[2]" in status
    assert "slipUrl" not in status
    assert "username" not in status
    assert "AdminID" not in status


def test_membership_activation_precedes_final_approval_and_customer_dm() -> None:
    source = _patch()
    review = source.split("function jaccReviewPhase3WebPaymentLocked_", 1)[1]

    activation = review.index("var activation = jaccApproveMembershipPayment_({")
    final_approval = review.index('"APPROVED",', activation)
    customer_dm = review.index("sendPaymentTelegramMessage_(userId, customerMessage)")
    assert activation < final_approval < customer_dm


def test_activation_failure_remains_pending_and_retry_safe() -> None:
    source = _patch()
    failure = source.split('if (!activation || activation.status !== "ok")', 1)[1]
    failure = failure.split('row.sheet.getRange(row.row, 10, 1, 4)', 1)[0]

    assert 'error:"MEMBERSHIP_ACTIVATION_FAILED"' in failure
    assert 'status:"PENDING"' in failure
    assert '"ACTIVATION_FAILED:"' in failure
    assert '"APPROVED"' not in failure
    assert "sendPaymentTelegramMessage_" not in failure


def test_reject_cannot_overwrite_completed_approval() -> None:
    source = _patch()
    review = source.split("function jaccReviewPhase3WebPaymentLocked_", 1)[1]

    assert 'if (approved && currentStatus === "APPROVED")' in review
    assert 'if (!approved && currentStatus === "REJECTED")' in review
    assert 'if (currentStatus !== "PENDING")' in review
    assert 'error:"PAYMENT_ALREADY_REVIEWED"' in review


def test_web_renewal_preserves_existing_password_and_api_hides_it() -> None:
    source = _patch()
    password_helper = source.split("function jaccPhase3Password_", 1)[1].split(
        "function jaccPhase3PublicActivation_", 1
    )[0]
    public_activation = source.split("function jaccPhase3PublicActivation_", 1)[1].split(
        "function jaccReviewPhase3WebPayment_", 1
    )[0]

    assert 'currentMember.package === "WEB"' in password_helper
    assert "currentMember.password" in password_helper
    assert "password" not in public_activation


def test_phase3_admin_review_actions_require_server_key_everywhere() -> None:
    security = SECURITY.read_text(encoding="utf-8")
    proxy = AUTH_PROXY.read_text(encoding="utf-8")

    for action in ("approveWebPayment", "rejectWebPayment"):
        assert f"{action}: true" in security
        assert f'"{action}"' in proxy

    assert "submitWebPayment: true" not in security
    assert "getWebPaymentStatus: true" not in security
