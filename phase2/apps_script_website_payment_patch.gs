/**
 * JACC Phase 2 adapter for the existing website Registration/Payment.gs flow.
 * STAGED ONLY. The existing jaccReviewPayment_ function must delegate here.
 */

function jaccWebsitePaymentApprovalKey_(paymentId) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(paymentId || ''),
    Utilities.Charset.UTF_8
  );
  var hex = bytes.map(function(value) {
    var unsigned = value < 0 ? value + 256 : value;
    return ('0' + unsigned.toString(16)).slice(-2);
  }).join('');
  return 'JACC-PAY-' + hex.slice(0, 32);
}

function jaccWebsitePaymentPublicActivation_(activation) {
  return {
    status: 'ok',
    expireDate: String((activation && activation.expireDate) || ''),
    package: String((activation && activation.package) || ''),
    duplicate: Boolean(activation && activation.duplicate),
    recovered: Boolean(activation && activation.recovered)
  };
}

function jaccReviewWebsitePayment_(paymentId, approved, adminNote) {
  paymentId = String(paymentId || '').trim();
  if (!paymentId) return {ok:false, error:'MISSING_PAYMENT_ID'};

  var paySh = jaccSheet_(JACC_PAY_SHEET);
  var payRow = jaccFindRow_(paySh, 1, paymentId);
  if (payRow === -1) return {ok:false, error:'PAYMENT_NOT_FOUND'};

  var row = paySh.getRange(payRow, 1, 1, 11).getDisplayValues()[0];
  var currentStatus = String(row[7] || '').toUpperCase();
  var registrationCode = String(row[1] || '').trim();
  var telegramId = String(row[2] || '').trim();
  var packageName = jaccPaymentPackage_(row[3]);
  var regSh = jaccSheet_(JACC_REG_SHEET);
  var regRow = jaccFindRow_(regSh, 1, registrationCode);

  // Final APPROVED is proof that membership activation completed. Repair a
  // partially completed Registration status write without extending again.
  if (approved && currentStatus === 'APPROVED') {
    if (regRow !== -1) regSh.getRange(regRow, 5).setValue('APPROVED');
    return {ok:true, paymentId:paymentId, status:'APPROVED', duplicate:true};
  }
  if (currentStatus !== 'PENDING') {
    return {ok:false, error:'PAYMENT_ALREADY_REVIEWED', status:currentStatus};
  }
  if (regRow === -1) {
    return {ok:false, error:'REGISTRATION_NOT_FOUND', status:'PENDING'};
  }

  var reg = regSh.getRange(regRow, 1, 1, 6).getDisplayValues()[0];
  var username = String(reg[2] || telegramId).trim() || telegramId;

  if (approved) {
    if (typeof jaccApproveMembershipPayment_ !== 'function') {
      return {ok:false, error:'PHASE2_PAYMENT_APPROVAL_NOT_AVAILABLE', status:'PENDING'};
    }

    var currentMember = typeof jaccPaymentMemberSnapshot_ === 'function'
      ? jaccPaymentMemberSnapshot_(telegramId)
      : null;
    var password = '';
    if (
      packageName === 'WEB' &&
      (!currentMember || currentMember.package !== 'WEB' || !currentMember.password)
    ) {
      password = generateJaccWebPassword_();
    }

    var activation = jaccApproveMembershipPayment_({
      idempotencyKey: jaccWebsitePaymentApprovalKey_(paymentId),
      userId: telegramId,
      username: username,
      days: 30,
      package: packageName,
      password: password,
      membershipAction: 'website_payment',
      payment: {
        userId: telegramId,
        username: username,
        package: packageName,
        months: 1,
        amount: row[4],
        payType: row[5],
        transactionNo: paymentId,
        status: 'APPROVED'
      }
    });

    if (!activation || activation.status !== 'ok') {
      var activationError = String(
        (activation && (activation.message || activation.error)) ||
        'membership_activation_failed'
      );
      paySh.getRange(payRow, 11).setValue('ACTIVATION_FAILED:' + activationError);
      return {
        ok:false,
        error:'MEMBERSHIP_ACTIVATION_FAILED',
        activationError:activationError,
        status:'PENDING'
      };
    }

    // Registration is written first. Payment APPROVED is the final completion
    // marker, so a crash before it remains retryable with the same ledger key.
    regSh.getRange(regRow, 5).setValue('APPROVED');
    paySh.getRange(payRow, 10).setValue(new Date());
    paySh.getRange(payRow, 11).setValue(String(adminNote || ''));
    paySh.getRange(payRow, 8).setValue('APPROVED');

    jaccTelegram_(
      telegramId,
      '✅ <b>JACC Membership Approved</b>\nYour account is now active.'
    );

    return {
      ok:true,
      paymentId:paymentId,
      status:'APPROVED',
      activation:jaccWebsitePaymentPublicActivation_(activation)
    };
  }

  regSh.getRange(regRow, 5).setValue('REJECTED');
  paySh.getRange(payRow, 10).setValue(new Date());
  paySh.getRange(payRow, 11).setValue(String(adminNote || ''));
  paySh.getRange(payRow, 8).setValue('REJECTED');

  jaccTelegram_(
    telegramId,
    '❌ <b>JACC Payment Rejected</b>\nPlease contact the administrator or submit a new slip.'
  );

  return {ok:true, paymentId:paymentId, status:'REJECTED'};
}
