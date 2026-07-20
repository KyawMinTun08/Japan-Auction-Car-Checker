/*
 * JACC one-device security patch
 *
 * Members sheet columns:
 * A UserID
 * B Username
 * C Start
 * D Expire
 * E Status
 * F CancelCount
 * G Password
 * H Package
 * I Token
 * J DeviceID
 * K DeviceBoundAt
 * L DeviceResetCount
 *
 * Merge the constants and helper functions into the existing Apps Script.
 * Update the existing verifyLogin action to call verifyLoginWithDevice().
 */

var C_USERID       = 0;
var C_USERNAME     = 1;
var C_START        = 2;
var C_EXPIRE       = 3;
var C_STATUS       = 4;
var C_CANCELCOUNT  = 5;
var C_PASSWORD     = 6;
var C_PACKAGE      = 7;
var C_TOKEN        = 8;
var C_DEVICE_ID    = 9;
var C_DEVICE_BOUND = 10;
var C_DEVICE_RESET = 11;

function normaliseDeviceId_(value) {
  return String(value || '').trim().toLowerCase();
}

function isWebPackage_(pkg) {
  pkg = String(pkg || '').trim().toUpperCase();
  return pkg === 'WEB' || pkg === 'WEB-PROMO' || pkg === 'PREMIUM';
}

function isMemberExpired_(expireValue) {
  if (!expireValue) return true;
  var expire = expireValue instanceof Date ? expireValue : new Date(expireValue);
  if (isNaN(expire.getTime())) return true;
  var endOfDay = new Date(expire);
  endOfDay.setHours(23, 59, 59, 999);
  return Date.now() > endOfDay.getTime();
}

function makeLoginResponse_(ok, extra) {
  var result = { ok: Boolean(ok) };
  Object.keys(extra || {}).forEach(function (key) {
    result[key] = extra[key];
  });
  return result;
}

/**
 * Secure login for the Flutter app and website.
 *
 * Expected payload:
 * {
 *   action: 'verifyLogin',
 *   password: '...',
 *   deviceId: 'uuid-or-empty',
 *   client: 'flutter' | 'web'
 * }
 */
function verifyLoginWithDevice(password, deviceId, client) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);

  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Members');
    if (!sheet) {
      return makeLoginResponse_(false, { reason: 'members_sheet_missing' });
    }

    var cleanPassword = String(password || '').trim();
    var cleanDeviceId = normaliseDeviceId_(deviceId);
    var cleanClient = String(client || 'web').trim().toLowerCase();

    if (!cleanPassword) {
      return makeLoginResponse_(false, { reason: 'password_required' });
    }

    var lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      return makeLoginResponse_(false, { reason: 'wrong_password' });
    }

    var requiredColumns = C_DEVICE_RESET + 1;
    if (sheet.getMaxColumns() < requiredColumns) {
      sheet.insertColumnsAfter(sheet.getMaxColumns(), requiredColumns - sheet.getMaxColumns());
    }

    var rows = sheet.getRange(2, 1, lastRow - 1, requiredColumns).getValues();

    for (var i = 0; i < rows.length; i++) {
      var storedPassword = String(rows[i][C_PASSWORD] || '').trim();
      if (!storedPassword || storedPassword !== cleanPassword) continue;

      var status = String(rows[i][C_STATUS] || '').trim().toUpperCase();
      if (status === 'BANNED' || status === 'KICKED' || status === 'INACTIVE') {
        return makeLoginResponse_(false, { reason: 'account_' + status.toLowerCase() });
      }

      if (isMemberExpired_(rows[i][C_EXPIRE])) {
        return makeLoginResponse_(false, { reason: 'expired' });
      }

      var pkg = String(rows[i][C_PACKAGE] || 'CH').trim().toUpperCase();
      if (!isWebPackage_(pkg)) {
        return makeLoginResponse_(false, { reason: 'web_package_required' });
      }

      var storedDeviceId = normaliseDeviceId_(rows[i][C_DEVICE_ID]);
      var rowNumber = i + 2;

      // Browser logins remain compatible. Flutter logins must provide an installation ID.
      if (cleanClient === 'flutter' && !cleanDeviceId) {
        return makeLoginResponse_(false, { reason: 'device_id_required' });
      }

      if (cleanDeviceId) {
        if (!storedDeviceId) {
          sheet.getRange(rowNumber, C_DEVICE_ID + 1).setValue(cleanDeviceId);
          sheet.getRange(rowNumber, C_DEVICE_BOUND + 1).setValue(new Date());
          storedDeviceId = cleanDeviceId;
        } else if (storedDeviceId !== cleanDeviceId) {
          return makeLoginResponse_(false, {
            reason: 'different_device',
            message: 'ဒီ Member account ကို အခြားဖုန်းတစ်လုံးမှာ ချိတ်ထားပြီးသား ဖြစ်ပါတယ်။'
          });
        }
      }

      var token = String(rows[i][C_TOKEN] || '').trim();
      if (!token) {
        token = Utilities.getUuid().replace(/-/g, '');
        sheet.getRange(rowNumber, C_TOKEN + 1).setValue(token);
      }

      return makeLoginResponse_(true, {
        token: token,
        userId: String(rows[i][C_USERID] || ''),
        username: String(rows[i][C_USERNAME] || ''),
        package: pkg,
        expireDate: rows[i][C_EXPIRE],
        deviceBound: Boolean(storedDeviceId),
        deviceId: storedDeviceId
      });
    }

    return makeLoginResponse_(false, { reason: 'wrong_password' });
  } finally {
    lock.releaseLock();
  }
}

/**
 * Admin-only helper. Run manually after confirming the member identity.
 */
function resetMemberDeviceByUserId(userId) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Members');
  if (!sheet) throw new Error('Members sheet not found');

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;

  var rows = sheet.getRange(2, 1, lastRow - 1, C_DEVICE_RESET + 1).getValues();
  var target = String(userId || '').trim();

  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i][C_USERID] || '').trim() !== target) continue;

    var rowNumber = i + 2;
    var resetCount = Number(rows[i][C_DEVICE_RESET] || 0) + 1;
    sheet.getRange(rowNumber, C_DEVICE_ID + 1).clearContent();
    sheet.getRange(rowNumber, C_DEVICE_BOUND + 1).clearContent();
    sheet.getRange(rowNumber, C_DEVICE_RESET + 1).setValue(resetCount);
    return true;
  }

  return false;
}

/**
 * Add the new headers once. Existing values are preserved.
 */
function ensureDeviceSecurityColumns() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Members');
  if (!sheet) throw new Error('Members sheet not found');

  var headers = ['DeviceID', 'DeviceBoundAt', 'DeviceResetCount'];
  for (var i = 0; i < headers.length; i++) {
    var column = C_DEVICE_ID + 1 + i;
    if (!sheet.getRange(1, column).getValue()) {
      sheet.getRange(1, column).setValue(headers[i]);
    }
  }
}
