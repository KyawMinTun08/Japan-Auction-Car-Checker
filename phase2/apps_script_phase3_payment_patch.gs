/**
 * JACC Phase 2 adapter for the existing Phase3Payments.gs flow.
 *
 * STAGED ONLY. Deploy with the membership security, payment approval ledger,
 * device binding, and Railway Phase 2 installer. The current Phase3Payments.gs
 * functions must delegate to these helpers through the guarded transformer.
 */

var JACC_PHASE3_ALLOWED_METHODS = {
  KPAY: true,
  WAVEPAY: true,
  PROMPTPAY: true,
  THAI_BANK: true
};

function jaccPhase3Text_(value) {
  return String(value == null ? "" : value).trim();
}

function jaccPhase3Package_(value) {
  var text = jaccPhase3Text_(value).toUpperCase().replace(/[_-]+/g, " ");
  if (text.indexOf("WEB") >= 0 || text.indexOf("PREMIUM") >= 0) return "WEB";
  if (text === "CH" || text === "CHANNEL" || text.indexOf("STANDARD") >= 0) return "CH";
  return "";
}

function jaccPhase3Months_(value) {
  var months = Number(value || 1);
  if (!isFinite(months) || Math.floor(months) !== months || months < 1 || months > 12) {
    return 0;
  }
  return months;
}

function jaccPhase3Method_(value) {
  var method = jaccPhase3Text_(value).toUpperCase();
  return JACC_PHASE3_ALLOWED_METHODS[method] ? method : "";
}

function jaccPhase3Mime_(value) {
  var mime = jaccPhase3Text_(value || "image/jpeg").toLowerCase();
  if (mime === "image/jpg") mime = "image/jpeg";
  return ["image/jpeg", "image/png", "image/webp"].indexOf(mime) >= 0 ? mime : "";
}

function jaccPhase3PaymentId_() {
  return "WP-" + Utilities.getUuid().replace(/-/g, "").slice(0, 20).toUpperCase();
}

function jaccPhase3ApprovalKey_(paymentId) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    "JACC-PHASE3-PAYMENT:" + jaccPhase3Text_(paymentId),
    Utilities.Charset.UTF_8
  );
  var hex = bytes.map(function(value) {
    var unsigned = value < 0 ? value + 256 : value;
    return ("0" + unsigned.toString(16)).slice(-2);
  }).join("");
  return "JACC-PAY-" + hex.slice(0, 32);
}

function jaccPhase3PendingForUser_(sheet, userId) {
  if (!sheet || sheet.getLastRow() < 2) return null;
  var rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 13).getDisplayValues();
  for (var i = 0; i < rows.length; i++) {
    if (jaccPhase3Text_(rows[i][2]) !== userId) continue;
    if (jaccPhase3Text_(rows[i][9]).toUpperCase() !== "PENDING") continue;
    return {
      row: i + 2,
      paymentId: jaccPhase3Text_(rows[i][0]),
      status: "PENDING"
    };
  }
  return null;
}

function jaccSubmitPhase3WebPayment_(body) {
  body = body || {};

  var userId = jaccPhase3Text_(body.userId).replace(/\.0$/, "");
  var username = jaccPhase3Text_(body.username).replace(/^@+/, "").slice(0, 64);
  var packageName = jaccPhase3Package_(body.package || "WEB");
  var months = jaccPhase3Months_(body.months);
  var amount = Number(body.amount || 0);
  var method = jaccPhase3Method_(body.method);
  var imageData = String(body.slipBase64 || "");
  var mimeType = jaccPhase3Mime_(body.mimeType || "image/jpeg");

  if (!/^\d+$/.test(userId)) return {ok:false, error:"INVALID_USER_ID"};
  if (!packageName) return {ok:false, error:"INVALID_PACKAGE"};
  if (!months) return {ok:false, error:"INVALID_MONTHS"};
  if (!isFinite(amount) || amount <= 0 || amount > 1000000000) {
    return {ok:false, error:"INVALID_AMOUNT"};
  }
  if (!method) return {ok:false, error:"INVALID_METHOD"};
  if (!mimeType) return {ok:false, error:"INVALID_SLIP_TYPE"};
  if (!imageData) return {ok:false, error:"MISSING_SLIP"};

  var rawBase64 = imageData.indexOf(",") >= 0 ? imageData.split(",").pop() : imageData;
  var estimatedBytes = Math.floor(rawBase64.length * 3 / 4);
  if (!rawBase64 || estimatedBytes > 5 * 1024 * 1024) {
    return {ok:false, error:"SLIP_TOO_LARGE"};
  }

  var sheet = getPaymentSheet_();
  var existing = jaccPhase3PendingForUser_(sheet, userId);
  if (existing) {
    return {
      ok:true,
      paymentId:existing.paymentId,
      status:"PENDING",
      duplicate:true
    };
  }

  var paymentId = jaccPhase3PaymentId_();
  var slipUrl = savePaymentSlip_(paymentId, rawBase64, mimeType);

  sheet.appendRow([
    paymentId,
    new Date(),
    userId,
    username,
    packageName,
    months,
    amount,
    method,
    slipUrl,
    "PENDING",
    "",
    "",
    new Date()
  ]);

  var warning = "";
  try {
    notifyPaymentAdmin_({
      paymentId: paymentId,
      userId: userId,
      username: username,
      packageName: packageName,
      months: months,
      amount: amount,
      method: method,
      slipUrl: slipUrl
    });
  } catch (notifyError) {
    warning = "ADMIN_NOTIFICATION_FAILED";
    sheet.getRange(sheet.getLastRow(), 12).setValue(warning);
    Logger.log("Phase 3 admin notification failed: " + notifyError);
  }

  return {
    ok:true,
    paymentId:paymentId,
    status:"PENDING",
    warning:warning || undefined
  };
}

function jaccGetPhase3WebPaymentStatus_(paymentId, userId) {
  var wantedPayment = jaccPhase3Text_(paymentId);
  var wantedUser = jaccPhase3Text_(userId).replace(/\.0$/, "");
  if (!wantedPayment || !/^\d+$/.test(wantedUser)) {
    return {ok:false, error:"INVALID_STATUS_REQUEST"};
  }

  var row = findPaymentRow_(wantedPayment);
  if (!row || jaccPhase3Text_(row.values[2]).replace(/\.0$/, "") !== wantedUser) {
    return {ok:false, error:"PAYMENT_NOT_FOUND"};
  }

  return {
    ok:true,
    paymentId:jaccPhase3Text_(row.values[0]),
    status:jaccPhase3Text_(row.values[9]).toUpperCase(),
    package:jaccPhase3Package_(row.values[4]) || "CH",
    months:Number(row.values[5] || 1),
    amount:Number(row.values[6] || 0),
    method:jaccPhase3Method_(row.values[7]) || "",
    updatedAt:row.values[12]
  };
}

function jaccPhase3Password_(currentMember, packageName) {
  if (packageName !== "WEB") return "";
  if (currentMember && currentMember.package === "WEB" && currentMember.password) {
    return currentMember.password;
  }
  if (typeof generateJaccWebPassword_ === "function") return generateJaccWebPassword_();
  if (typeof generateWebPassword_ === "function") return generateWebPassword_();
  return "";
}

function jaccPhase3PublicActivation_(activation) {
  return {
    status:"ok",
    expireDate:jaccPhase3Text_(activation && activation.expireDate),
    package:jaccPhase3Text_(activation && activation.package),
    duplicate:Boolean(activation && activation.duplicate),
    recovered:Boolean(activation && activation.recovered)
  };
}

function jaccReviewPhase3WebPayment_(paymentId, approved, adminId, reason) {
  var lock = LockService.getScriptLock();
  var releaseHere = false;
  try {
    if (!lock.hasLock()) {
      lock.waitLock(30000);
      releaseHere = true;
    }
  } catch (lockError) {
    return {ok:false, error:"PAYMENT_LOCK_BUSY"};
  }

  try {
    return jaccReviewPhase3WebPaymentLocked_(paymentId, approved, adminId, reason);
  } finally {
    if (releaseHere) lock.releaseLock();
  }
}

function jaccReviewPhase3WebPaymentLocked_(paymentId, approved, adminId, reason) {
  paymentId = jaccPhase3Text_(paymentId);
  if (!paymentId) return {ok:false, error:"MISSING_PAYMENT_ID"};

  var row = findPaymentRow_(paymentId);
  if (!row) return {ok:false, error:"PAYMENT_NOT_FOUND"};

  var currentStatus = jaccPhase3Text_(row.values[9]).toUpperCase();
  var userId = jaccPhase3Text_(row.values[2]).replace(/\.0$/, "");
  var username = jaccPhase3Text_(row.values[3]);
  var packageName = jaccPhase3Package_(row.values[4]);
  var months = jaccPhase3Months_(row.values[5]);

  if (approved && currentStatus === "APPROVED") {
    return {ok:true, status:"APPROVED", alreadyApproved:true};
  }
  if (!approved && currentStatus === "REJECTED") {
    return {ok:true, status:"REJECTED", alreadyRejected:true};
  }
  if (currentStatus !== "PENDING") {
    return {ok:false, error:"PAYMENT_ALREADY_REVIEWED", status:currentStatus};
  }
  if (!/^\d+$/.test(userId) || !packageName || !months) {
    return {ok:false, error:"INVALID_STORED_PAYMENT", status:"PENDING"};
  }

  if (!approved) {
    var rejectReason = jaccPhase3Text_(reason || "Payment could not be verified").slice(0, 500);
    row.sheet.getRange(row.row, 10, 1, 4).setValues([[
      "REJECTED",
      jaccPhase3Text_(adminId),
      rejectReason,
      new Date()
    ]]);
    sendPaymentTelegramMessage_(
      userId,
      "❌ JACC Payment Rejected.\n\nReason: " + rejectReason +
      "\n\nPlease upload a clear payment slip again."
    );
    return {ok:true, status:"REJECTED"};
  }

  if (typeof jaccApproveMembershipPayment_ !== "function") {
    return {ok:false, error:"PHASE2_PAYMENT_APPROVAL_NOT_AVAILABLE", status:"PENDING"};
  }

  var currentMember = typeof jaccPaymentMemberSnapshot_ === "function"
    ? jaccPaymentMemberSnapshot_(userId)
    : null;
  var password = jaccPhase3Password_(currentMember, packageName);
  if (packageName === "WEB" && !password) {
    return {ok:false, error:"WEB_PASSWORD_GENERATOR_MISSING", status:"PENDING"};
  }

  var activation = jaccApproveMembershipPayment_({
    idempotencyKey:jaccPhase3ApprovalKey_(paymentId),
    userId:userId,
    username:username || (currentMember ? currentMember.username : userId),
    days:months * 30,
    package:packageName,
    password:password,
    membershipAction:"phase3_website_payment",
    payment:{
      date:Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy"),
      time:Utilities.formatDate(new Date(), "Asia/Bangkok", "HH:mm:ss"),
      userId:userId,
      username:username,
      package:packageName,
      months:months,
      amount:row.values[6],
      payType:row.values[7],
      transactionNo:paymentId,
      status:"APPROVED"
    }
  });

  if (!activation || activation.status !== "ok") {
    var activationError = jaccPhase3Text_(
      activation && (activation.message || activation.error)
    ) || "membership_activation_failed";
    row.sheet.getRange(row.row, 12).setValue("ACTIVATION_FAILED:" + activationError);
    row.sheet.getRange(row.row, 13).setValue(new Date());
    return {
      ok:false,
      error:"MEMBERSHIP_ACTIVATION_FAILED",
      activationError:activationError,
      status:"PENDING"
    };
  }

  row.sheet.getRange(row.row, 10, 1, 4).setValues([[
    "APPROVED",
    jaccPhase3Text_(adminId),
    "",
    new Date()
  ]]);

  var customerMessage =
    "✅ JACC Payment Approved!\n\n" +
    "📦 Package: " + packageName + "\n" +
    "📅 Duration: " + months + " month(s)";
  if (packageName === "WEB" && activation.password) {
    customerMessage += "\n🔑 Website Password: " + activation.password;
  }
  var delivered = sendPaymentTelegramMessage_(userId, customerMessage);

  return {
    ok:true,
    status:"APPROVED",
    activation:jaccPhase3PublicActivation_(activation),
    deliveryFailed:!delivered
  };
}
