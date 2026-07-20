// JACC one-device security patch
// Add DeviceID as the LAST column in Members sheet (column J when current columns are A:I).
// Current expected indexes:
// A UserID, B Username, C Start, D Expire, E Status,
// F CancelCount, G Password, H Package, I Token, J DeviceID

var C_DEVICEID = 9;

function normalizeDeviceId_(value) {
  return String(value || '').trim();
}

function isFlutterApp_(app, deviceId) {
  return String(app || '').toLowerCase() === 'flutter' && normalizeDeviceId_(deviceId) !== '';
}

function verifyAndBindDevice_(sheet, rowIndex, deviceId, app) {
  var incoming = normalizeDeviceId_(deviceId);

  // Browser login remains compatible and is not device-locked.
  if (!isFlutterApp_(app, incoming)) {
    return {ok: true, deviceBound: false};
  }

  var current = normalizeDeviceId_(sheet.getRange(rowIndex, C_DEVICEID + 1).getValue());

  // First successful Flutter login binds this member to the installation.
  if (!current) {
    sheet.getRange(rowIndex, C_DEVICEID + 1).setValue(incoming);
    SpreadsheetApp.flush();
    return {ok: true, deviceBound: true, firstBind: true};
  }

  if (current !== incoming) {
    return {
      ok: false,
      status: 'error',
      message: 'device_mismatch'
    };
  }

  return {ok: true, deviceBound: true, firstBind: false};
}

function resetMemberDevice(userId) {
  var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName(MEMBERS);
  var rows = sheet.getDataRange().getValues();
  var target = String(userId || '').trim();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_USERID] || '').trim() === target) {
      sheet.getRange(i + 1, C_DEVICEID + 1).clearContent();
      return {status: 'ok', message: 'device_reset'};
    }
  }
  return {status: 'error', message: 'member_not_found'};
}

/*
INTEGRATION REQUIRED IN doPost:

case 'verifyLogin':
  return _json(verifyLogin(data.password, data.deviceId, data.app));

case 'verifyToken':
  return _json(verifyToken(data.token, data.deviceId, data.app));

case 'resetMemberDevice':
  return _json(resetMemberDevice(data.userId));

INTEGRATION REQUIRED INSIDE verifyLogin:

1. Change signature:
   function verifyLogin(password, deviceId, app)

2. After password/status/expiry checks succeed and before returning token:

   var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
   if (!deviceCheck.ok) return deviceCheck;

3. Return deviceBound in the successful response if useful:

   deviceBound: deviceCheck.deviceBound

INTEGRATION REQUIRED INSIDE verifyToken:

1. Change signature:
   function verifyToken(token, deviceId, app)

2. After matching the token row:

   var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
   if (!deviceCheck.ok) return deviceCheck;

ADMIN RESET:

Call resetMemberDevice(userId) from the Apps Script editor, or expose the
resetMemberDevice action only to an authenticated admin interface. Do not allow
an unauthenticated public request to reset a member device.
*/
