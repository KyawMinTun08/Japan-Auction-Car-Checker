/**
 * JACC Phase 2 one-installation device binding.
 *
 * STAGED ONLY. Deploy in the same Apps Script version as the Phase 2
 * membership security and payment patches.
 *
 * Canonical Members schema:
 * A UserID, B Username, C StartDate, D ExpireDate, E Status,
 * F CancelCount, G Password, H Package, I Token, J DeviceID.
 *
 * DeviceID policy:
 * - WEB/PREMIUM members must send app + deviceId on verifyLogin, verifyToken,
 *   and protected getData access;
 * - the first successful request binds Members!J;
 * - only a SHA-256 fingerprint is stored, never the raw installation ID;
 * - the same installation may log out and log in again;
 * - a different installation receives device_mismatch until an authenticated
 *   admin reset clears Members!J;
 * - IP addresses are never device identifiers.
 */

var JACC_DEVICE_COLUMN = 10;
var JACC_DEVICE_PREFIX = "v2:";
var JACC_DEVICE_MIN_LENGTH = 20;
var JACC_DEVICE_MAX_LENGTH = 200;
var JACC_DEVICE_ALLOWED_APPS = {
  web: true,
  pwa: true,
  flutter: true
};

function jaccDeviceText_(value) {
  return String(value || "").trim();
}

function jaccDevicePackageRequiresBinding_(value) {
  var pkg = jaccDeviceText_(value).toUpperCase();
  return pkg.indexOf("WEB") >= 0 || pkg.indexOf("PREMIUM") >= 0;
}

function jaccDeviceRequest_(data) {
  var app = jaccDeviceText_(data && data.app).toLowerCase();
  var deviceId = jaccDeviceText_(data && data.deviceId);

  if (!JACC_DEVICE_ALLOWED_APPS[app]) {
    return {
      ok: false,
      status: "error",
      message: "device_required"
    };
  }
  if (
    deviceId.length < JACC_DEVICE_MIN_LENGTH ||
    deviceId.length > JACC_DEVICE_MAX_LENGTH
  ) {
    return {
      ok: false,
      status: "error",
      message: "device_invalid"
    };
  }
  return {ok: true, app: app, deviceId: deviceId};
}

function jaccDeviceDigestHex_(value) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value || ""),
    Utilities.Charset.UTF_8
  );
  return bytes.map(function (byteValue) {
    var unsigned = byteValue < 0 ? byteValue + 256 : byteValue;
    return ("0" + unsigned.toString(16)).slice(-2);
  }).join("");
}

function jaccDeviceFingerprint_(deviceId) {
  return JACC_DEVICE_PREFIX + jaccDeviceDigestHex_(deviceId);
}

function jaccDeviceConstantTimeEqual_(left, right) {
  var a = String(left || "");
  var b = String(right || "");
  var maxLength = Math.max(a.length, b.length);
  var difference = a.length ^ b.length;
  for (var i = 0; i < maxLength; i++) {
    difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return difference === 0;
}

function jaccDeviceSuccess_(app, boundNow) {
  return {
    ok: true,
    status: "ok",
    deviceBound: true,
    deviceBoundNow: !!boundNow,
    clientApp: app
  };
}

/**
 * Enforce binding for one known member row.
 *
 * The deployed doPost currently holds a ScriptLock around action routing. This
 * helper therefore reuses an already-held lock instead of waiting on the same
 * non-reentrant lock and timing out. When called outside that router it safely
 * acquires and releases the lock itself.
 *
 * sheet: Members sheet
 * rowNumber: 1-based sheet row (not array index)
 * data: request payload containing app/deviceId
 * packageValue: authoritative package from column H
 */
function jaccEnforceDeviceBinding_(sheet, rowNumber, data, packageValue) {
  if (!jaccDevicePackageRequiresBinding_(packageValue)) {
    return {ok: true, status: "ok", deviceBound: false};
  }

  var request = jaccDeviceRequest_(data);
  if (!request.ok) return request;

  var lock = LockService.getScriptLock();
  var releaseHere = false;
  try {
    if (!lock.hasLock()) {
      lock.waitLock(10000);
      releaseHere = true;
    }
  } catch (lockError) {
    return {
      ok: false,
      status: "error",
      message: "device_lock_busy"
    };
  }

  try {
    var cell = sheet.getRange(rowNumber, JACC_DEVICE_COLUMN);
    var stored = jaccDeviceText_(cell.getDisplayValue());
    var fingerprint = jaccDeviceFingerprint_(request.deviceId);

    if (!stored) {
      cell.setValue(fingerprint);
      SpreadsheetApp.flush();
      return jaccDeviceSuccess_(request.app, true);
    }

    if (stored.indexOf(JACC_DEVICE_PREFIX) === 0) {
      if (jaccDeviceConstantTimeEqual_(stored, fingerprint)) {
        return jaccDeviceSuccess_(request.app, false);
      }
      return {
        ok: false,
        status: "error",
        message: "device_mismatch"
      };
    }

    // Compatibility for any historical raw DeviceID. A matching request is
    // upgraded immediately to the hashed v2 format.
    if (jaccDeviceConstantTimeEqual_(stored, request.deviceId)) {
      cell.setValue(fingerprint);
      SpreadsheetApp.flush();
      return jaccDeviceSuccess_(request.app, false);
    }

    return {
      ok: false,
      status: "error",
      message: "device_mismatch"
    };
  } finally {
    if (releaseHere) lock.releaseLock();
  }
}

/**
 * Protected server-side reset. The Phase 2 membership preflight must verify
 * JACC_SERVER_KEY before this function is reachable.
 */
function jaccResetMemberDevice_(data) {
  var userId = jaccDeviceText_(data && data.userId).replace(/\.0$/, "");
  if (!/^\d+$/.test(userId)) {
    return {status: "error", message: "invalid_user_id"};
  }

  var ss = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  if (!sheet) return {status: "error", message: "members_sheet_missing"};

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return {status: "error", message: "member_not_found"};
  var ids = sheet.getRange(2, 1, lastRow - 1, 1).getDisplayValues();
  for (var i = 0; i < ids.length; i++) {
    if (jaccDeviceText_(ids[i][0]).replace(/\.0$/, "") === userId) {
      sheet.getRange(i + 2, JACC_DEVICE_COLUMN).clearContent();
      SpreadsheetApp.flush();
      return {status: "ok", message: "device_reset", userId: userId};
    }
  }
  return {status: "error", message: "member_not_found"};
}

/**
 * REQUIRED integration points in deployed Code.gs:
 *
 * verifyLogin, after password/status/expiry/package are validated and before
 * token generation/return:
 *
 *   var device = jaccEnforceDeviceBinding_(
 *     sheet, memberRowNumber, data, memberPackage
 *   );
 *   if (!device.ok) return device;
 *
 * verifyToken, after token/status/expiry/package are validated:
 *
 *   var device = jaccEnforceDeviceBinding_(
 *     sheet, memberRowNumber, data, memberPackage
 *   );
 *   if (!device.ok) return device;
 *
 * getData, after locating and validating the token owner and before returning
 * cars:
 *
 *   var device = jaccEnforceDeviceBinding_(
 *     membersSheet, memberRowNumber, data, memberPackage
 *   );
 *   if (!device.ok) return device;
 *
 * Protected doPost route:
 *
 *   case "resetMemberDevice":
 *     return _json(jaccResetMemberDevice_(data));
 *
 * The reset route must remain inside JACC_PRIVILEGED_MEMBER_ACTIONS so it
 * cannot be called from browser code.
 */
