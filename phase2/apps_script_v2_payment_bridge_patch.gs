/**
 * JACC Phase 2 bridge for the existing JACC v2 Payment.gs flow.
 *
 * STAGED ONLY. Add this file with the other Phase 2 Apps Script modules and
 * patch Payment.gs with apply_apps_script_payment_gs.py before deployment.
 *
 * The bridge converts each existing PAY-* payment ID into one stable
 * JACC-PAY-<32 hex> idempotency key and delegates the member write to the
 * Phase 2 Membership_Approval_Ledger implementation.
 */

function jaccV2PaymentIdempotencyKey_(paymentId) {
  var clean = String(paymentId || "").trim();
  if (!clean) return "";

  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    "JACC-V2-PAYMENT:" + clean,
    Utilities.Charset.UTF_8
  );
  var hex = bytes.map(function(value) {
    var unsigned = value < 0 ? value + 256 : value;
    return ("0" + unsigned.toString(16)).slice(-2);
  }).join("");

  return "JACC-PAY-" + hex.slice(0, 32);
}

function jaccV2RegistrationUsername_(registrationCode, fallback) {
  var code = String(registrationCode || "").trim();
  var safeFallback = String(fallback || "").trim();
  if (!code) return safeFallback;

  try {
    var sheetName = typeof JACC_REG_SHEET !== "undefined"
      ? JACC_REG_SHEET
      : "Registrations";
    var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName(sheetName);
    if (!sheet || sheet.getLastRow() < 2) return safeFallback;

    var rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 6)
      .getDisplayValues();
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i][0] || "").trim() !== code) continue;
      return String(rows[i][2] || safeFallback).trim() || safeFallback;
    }
  } catch (lookupError) {
    Logger.log("Phase 2 registration username lookup failed: " + lookupError);
  }

  return safeFallback;
}

function jaccActivateV2PaymentPhase2_(payment) {
  payment = payment || {};

  var paymentId = String(payment.paymentId || "").trim();
  var userId = String(payment.telegramId || "").trim().replace(/\.0$/, "");
  var registrationCode = String(payment.registrationCode || "").trim();
  var packageName = jaccPaymentPackage_(payment.package || "CH");
  var key = jaccV2PaymentIdempotencyKey_(paymentId);

  if (!/^PAY-[A-Z0-9]+$/i.test(paymentId)) {
    return {status: "error", message: "invalid_v2_payment_id"};
  }
  if (!/^\d+$/.test(userId)) {
    return {status: "error", message: "invalid_user_id"};
  }
  if (!/^JACC-PAY-[a-f0-9]{32}$/i.test(key)) {
    return {status: "error", message: "invalid_idempotency_key"};
  }

  var days = parseInt(payment.days, 10);
  if (!days || days < 1 || days > 3660) {
    var months = parseInt(payment.months, 10);
    days = months && months > 0 ? months * 30 : 30;
  }

  var currentMember = jaccPaymentMemberSnapshot_(userId);
  var username = jaccV2RegistrationUsername_(
    registrationCode,
    currentMember ? currentMember.username : userId
  );
  var password = "";

  if (packageName === "WEB") {
    if (currentMember && currentMember.package === "WEB" && currentMember.password) {
      password = currentMember.password;
    } else if (typeof generateJaccWebPassword_ === "function") {
      password = generateJaccWebPassword_();
    } else {
      return {status: "error", message: "web_password_generator_missing"};
    }
  }

  return jaccApproveMembershipPayment_({
    idempotencyKey: key,
    userId: userId,
    username: username,
    days: days,
    package: packageName,
    password: password,
    membershipAction: currentMember ? "renew" : "new",
    payment: {
      date: Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy"),
      time: Utilities.formatDate(new Date(), "Asia/Bangkok", "HH:mm:ss"),
      userId: userId,
      username: username,
      package: packageName,
      months: Math.max(1, Math.round(days / 30)),
      amount: payment.amount || "",
      payType: payment.method || "",
      transactionNo: paymentId,
      status: "APPROVED"
    }
  });
}
