/**
 * JACC Phase 2 atomic membership-payment approval.
 *
 * STAGED ONLY — deploy together with apps_script_membership_security_patch.gs
 * and the Railway Phase 2 caller. The action must run under the existing
 * doPost ScriptLock and after jaccMembershipPreflight_(data).
 *
 * Required doPost route:
 *
 *   case "approveMembershipPayment":
 *     return _json(jaccApproveMembershipPayment_(data));
 */

var JACC_PAYMENT_APPROVAL_LEDGER = "Membership_Approval_Ledger";
var JACC_PAYMENT_APPROVAL_HEADERS = [
  "IdempotencyKey",
  "UserID",
  "Status",
  "TargetExpireDate",
  "ActualExpireDate",
  "Package",
  "MembershipAction",
  "CreatedAt",
  "UpdatedAt",
  "LastMessage"
];

function jaccPaymentText_(value) {
  return String(value == null ? "" : value).trim();
}

function jaccPaymentPackage_(value) {
  var packageName = jaccPaymentText_(value).toUpperCase();
  if (packageName.indexOf("WEB") >= 0 || packageName.indexOf("PREMIUM") >= 0) {
    return "WEB";
  }
  return "CH";
}

function jaccPaymentDate_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12, 0, 0);
  }
  var text = jaccPaymentText_(value);
  var match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  var parsed = new Date(
    parseInt(match[3], 10),
    parseInt(match[2], 10) - 1,
    parseInt(match[1], 10),
    12, 0, 0
  );
  return isNaN(parsed.getTime()) ? null : parsed;
}

function jaccPaymentFormatDate_(value) {
  var parsed = jaccPaymentDate_(value);
  if (!parsed) return "";
  return Utilities.formatDate(parsed, "Asia/Bangkok", "dd/MM/yyyy");
}

function jaccPaymentToday_() {
  var text = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy");
  return jaccPaymentDate_(text);
}

function jaccPaymentExpectedExpiry_(member, days) {
  var today = jaccPaymentToday_();
  var current = member ? jaccPaymentDate_(member.expireDate) : null;
  var active = member && jaccPaymentText_(member.status).toUpperCase() === "ACTIVE";
  var base = active && current && current.getTime() >= today.getTime() ? current : today;
  var target = new Date(base.getTime());
  target.setDate(target.getDate() + parseInt(days, 10));
  return jaccPaymentFormatDate_(target);
}

function jaccPaymentMemberSnapshot_(userId) {
  var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName(MEMBERS);
  if (!sheet || sheet.getLastRow() < 2) return null;
  var wanted = jaccPaymentText_(userId).replace(/\.0$/, "");
  var rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 10).getValues();
  for (var i = 0; i < rows.length; i++) {
    var rowId = jaccPaymentText_(rows[i][0]).replace(/\.0$/, "");
    if (rowId !== wanted) continue;
    return {
      row: i + 2,
      userId: rowId,
      username: jaccPaymentText_(rows[i][1]),
      expireDate: jaccPaymentFormatDate_(rows[i][3]),
      status: jaccPaymentText_(rows[i][4]).toUpperCase(),
      password: jaccPaymentText_(rows[i][6]),
      package: jaccPaymentPackage_(rows[i][7])
    };
  }
  return null;
}

function jaccPaymentEnsureLedger_() {
  var ss = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(JACC_PAYMENT_APPROVAL_LEDGER);
  if (!sheet) sheet = ss.insertSheet(JACC_PAYMENT_APPROVAL_LEDGER);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(JACC_PAYMENT_APPROVAL_HEADERS);
    sheet.getRange(1, 1, 1, JACC_PAYMENT_APPROVAL_HEADERS.length)
      .setFontWeight("bold");
  }
  return sheet;
}

function jaccPaymentFindLedger_(sheet, idempotencyKey) {
  if (sheet.getLastRow() < 2) return null;
  var keys = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getDisplayValues();
  for (var i = 0; i < keys.length; i++) {
    if (jaccPaymentText_(keys[i][0]) !== idempotencyKey) continue;
    var row = i + 2;
    var values = sheet.getRange(row, 1, 1, JACC_PAYMENT_APPROVAL_HEADERS.length)
      .getDisplayValues()[0];
    return {
      row: row,
      key: values[0],
      userId: values[1],
      status: values[2],
      targetExpireDate: values[3],
      actualExpireDate: values[4],
      package: values[5],
      membershipAction: values[6],
      lastMessage: values[9]
    };
  }
  return null;
}

function jaccPaymentWriteLedger_(sheet, existing, values) {
  var now = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm:ss");
  if (!existing) {
    sheet.appendRow([
      values.key,
      values.userId,
      values.status,
      values.targetExpireDate || "",
      values.actualExpireDate || "",
      values.package || "",
      values.membershipAction || "",
      now,
      now,
      values.lastMessage || ""
    ]);
    return jaccPaymentFindLedger_(sheet, values.key);
  }

  sheet.getRange(existing.row, 2, 1, 9).setValues([[
    values.userId || existing.userId,
    values.status || existing.status,
    values.targetExpireDate || existing.targetExpireDate,
    values.actualExpireDate || existing.actualExpireDate,
    values.package || existing.package,
    values.membershipAction || existing.membershipAction,
    sheet.getRange(existing.row, 8).getDisplayValue() || now,
    now,
    values.lastMessage || ""
  ]]);
  return jaccPaymentFindLedger_(sheet, values.key || existing.key);
}

function jaccPaymentDateAtLeast_(actual, expected) {
  var actualDate = jaccPaymentDate_(actual);
  var expectedDate = jaccPaymentDate_(expected);
  return Boolean(actualDate && expectedDate && actualDate.getTime() >= expectedDate.getTime());
}

function jaccPaymentAppendFinanceOnce_(idempotencyKey, payment) {
  var ss = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName("Finance");
  if (!sheet) sheet = ss.insertSheet("Finance");
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      "Date", "Time", "UserID", "Username", "Package", "Months",
      "Amount(Ks)", "PayType", "TransactionNo", "TransferTo", "Sender",
      "Status", "IdempotencyKey"
    ]);
  } else if (!jaccPaymentText_(sheet.getRange(1, 13).getDisplayValue())) {
    sheet.getRange(1, 13).setValue("IdempotencyKey");
  }

  if (sheet.getLastRow() >= 2) {
    var existingKeys = sheet.getRange(2, 13, sheet.getLastRow() - 1, 1)
      .getDisplayValues();
    for (var i = 0; i < existingKeys.length; i++) {
      if (jaccPaymentText_(existingKeys[i][0]) === idempotencyKey) return false;
    }
  }

  var fp = payment || {};
  sheet.appendRow([
    fp.date || "",
    fp.time || "",
    fp.userId || "",
    fp.username || "",
    fp.package || "",
    fp.months || "",
    fp.amount || "",
    fp.payType || "",
    fp.transactionNo || "",
    fp.receiver || "",
    fp.sender || "",
    fp.status || "APPROVED",
    idempotencyKey
  ]);
  return true;
}

function jaccPaymentSuccessResponse_(ledger, member, duplicate, recovered) {
  return {
    status: "ok",
    idempotencyKey: ledger.key,
    expireDate: ledger.actualExpireDate || member.expireDate,
    package: ledger.package || member.package,
    password: member.password || "",
    duplicate: Boolean(duplicate),
    recovered: Boolean(recovered)
  };
}

function jaccApproveMembershipPayment_(data) {
  var key = jaccPaymentText_(data.idempotencyKey);
  if (!/^JACC-PAY-[a-f0-9]{32}$/i.test(key)) {
    return {status: "error", message: "invalid_idempotency_key"};
  }

  var userId = jaccPaymentText_(data.userId).replace(/\.0$/, "");
  if (!/^\d+$/.test(userId)) {
    return {status: "error", message: "invalid_user_id"};
  }

  var days = parseInt(data.days, 10);
  if (!days || days < 1 || days > 3660) {
    return {status: "error", message: "invalid_days"};
  }

  var packageName = jaccPaymentPackage_(data.package);
  var membershipAction = jaccPaymentText_(data.membershipAction || "renew").toLowerCase();
  var ledgerSheet = jaccPaymentEnsureLedger_();
  var existing = jaccPaymentFindLedger_(ledgerSheet, key);
  var currentMember = jaccPaymentMemberSnapshot_(userId);

  if (existing && existing.userId !== userId) {
    return {status: "error", message: "idempotency_key_conflict"};
  }

  if (existing && existing.status === "COMPLETED") {
    if (!currentMember) return {status: "error", message: "completed_member_missing"};
    return jaccPaymentSuccessResponse_(existing, currentMember, true, false);
  }

  if (existing && existing.status === "PROCESSING" && currentMember &&
      jaccPaymentDateAtLeast_(currentMember.expireDate, existing.targetExpireDate)) {
    jaccPaymentAppendFinanceOnce_(key, data.payment || {});
    existing = jaccPaymentWriteLedger_(ledgerSheet, existing, {
      key: key,
      userId: userId,
      status: "COMPLETED",
      targetExpireDate: existing.targetExpireDate,
      actualExpireDate: currentMember.expireDate,
      package: currentMember.package,
      membershipAction: membershipAction,
      lastMessage: "recovered_after_partial_completion"
    });
    return jaccPaymentSuccessResponse_(existing, currentMember, true, true);
  }

  var targetExpireDate = existing && existing.targetExpireDate
    ? existing.targetExpireDate
    : jaccPaymentExpectedExpiry_(currentMember, days);

  existing = jaccPaymentWriteLedger_(ledgerSheet, existing, {
    key: key,
    userId: userId,
    status: "PROCESSING",
    targetExpireDate: targetExpireDate,
    actualExpireDate: "",
    package: packageName,
    membershipAction: membershipAction,
    lastMessage: "membership_write_started"
  });

  var saved;
  try {
    saved = saveMember(
      userId,
      jaccPaymentText_(data.username),
      days,
      jaccPaymentText_(data.password),
      packageName
    );
  } catch (err) {
    jaccPaymentWriteLedger_(ledgerSheet, existing, {
      key: key,
      userId: userId,
      status: "RETRYABLE",
      targetExpireDate: targetExpireDate,
      package: packageName,
      membershipAction: membershipAction,
      lastMessage: "save_exception:" + String(err)
    });
    return {status: "error", message: "membership_save_exception"};
  }

  if (!saved || jaccPaymentText_(saved.status).toLowerCase() !== "ok") {
    jaccPaymentWriteLedger_(ledgerSheet, existing, {
      key: key,
      userId: userId,
      status: "RETRYABLE",
      targetExpireDate: targetExpireDate,
      package: packageName,
      membershipAction: membershipAction,
      lastMessage: "membership_save_rejected"
    });
    return {status: "error", message: "membership_save_rejected"};
  }

  currentMember = jaccPaymentMemberSnapshot_(userId);
  if (!currentMember || !currentMember.expireDate) {
    // Keep PROCESSING. A retry checks the target expiry before writing again.
    jaccPaymentWriteLedger_(ledgerSheet, existing, {
      key: key,
      userId: userId,
      status: "PROCESSING",
      targetExpireDate: targetExpireDate,
      package: packageName,
      membershipAction: membershipAction,
      lastMessage: "authoritative_member_read_pending"
    });
    return {status: "error", message: "authoritative_expiry_missing"};
  }

  jaccPaymentAppendFinanceOnce_(key, data.payment || {});
  existing = jaccPaymentWriteLedger_(ledgerSheet, existing, {
    key: key,
    userId: userId,
    status: "COMPLETED",
    targetExpireDate: targetExpireDate,
    actualExpireDate: currentMember.expireDate,
    package: currentMember.package,
    membershipAction: membershipAction,
    lastMessage: "completed"
  });

  return jaccPaymentSuccessResponse_(existing, currentMember, false, false);
}
