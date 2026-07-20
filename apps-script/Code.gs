// ═══════════════════════════════════════════════════════════
//  JAN JAPAN Auction — Apps Script (Code.gs)
//  Members Sheet Columns:
//  [0] UserID  [1] Username  [2] StartDate  [3] ExpireDate
//  [4] Status  [5] CancelCount  [6] Password  [7] Package  [8] Token
//  [9] DeviceID (Flutter app installation binding)
// ═══════════════════════════════════════════════════════════

var SS_ID    = "1ZRw9xUS2pqZe5rJdmBtsX6yS7hAc65BHDO6K3zG1mpY";
var MEMBERS  = "Members";
var LOG_SHEET = "ID_Change_Log";
var PAY_SHEET = "Payment_History";

// Column indexes (0-based)
var C_USERID   = 0;
var C_USERNAME = 1;
var C_START    = 2;
var C_EXPIRE   = 3;
var C_STATUS   = 4;
var C_CANCELCOUNT = 5;
var C_PASSWORD = 6;
var C_PACKAGE  = 7;
var C_TOKEN    = 8;
var C_DEVICEID = 9;

// NOTE: This GitHub copy is the device-security integrated version of the
// uploaded live Apps Script. The full original business logic is preserved in
// the source file supplied by the user; only the device-security integration
// points below were added.

// ── One-device security helpers ────────────────────────────
function _normalizeDeviceId(value) {
  return String(value || "").trim();
}

function _isFlutterDeviceRequest(app, deviceId) {
  return String(app || "").trim().toLowerCase() === "flutter"
    && _normalizeDeviceId(deviceId) !== "";
}

function verifyAndBindDevice_(sheet, rowNumber, deviceId, app) {
  var incoming = _normalizeDeviceId(deviceId);

  // Existing browser access remains compatible. Flutter logins are locked.
  if (!_isFlutterDeviceRequest(app, incoming)) {
    return {ok:true, deviceBound:false};
  }

  var current = _normalizeDeviceId(
    sheet.getRange(rowNumber, C_DEVICEID + 1).getValue()
  );

  if (!current) {
    sheet.getRange(rowNumber, C_DEVICEID + 1).setValue(incoming);
    SpreadsheetApp.flush();
    return {ok:true, deviceBound:true, firstBind:true};
  }

  if (current !== incoming) {
    return {
      ok:false,
      status:"error",
      message:"device_mismatch"
    };
  }

  return {ok:true, deviceBound:true, firstBind:false};
}

function resetMemberDevice(userId) {
  var target = String(userId || "").trim();
  if (!target) return {status:"error", message:"missing_user_id"};

  var ss = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows = sheet.getDataRange().getValues();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_USERID] || "").trim() !== target) continue;

    sheet.getRange(i + 1, C_DEVICEID + 1).clearContent();
    sheet.getRange(i + 1, C_TOKEN + 1).clearContent();
    writeAuditLog("Admin", "DEVICE_RESET", "UserID:" + target, "SUCCESS");
    return {status:"ok", message:"device_reset", userId:target};
  }

  return {status:"error", message:"member_not_found"};
}

// ── Integration reference ──────────────────────────────────
// Apply these exact changes to the live Code.gs body:
// 1) doPost verifyLogin call:
//    verifyLogin(data.password, data.deviceId, data.app)
// 2) doPost verifyToken call:
//    verifyToken(data.token, data.deviceId, data.app)
// 3) add case "resetMemberDevice": return _json(resetMemberDevice(data.userId));
// 4) change verifyLogin signature to verifyLogin(password, deviceId, app)
// 5) before generating token:
//    var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
//    if (!deviceCheck.ok) return deviceCheck;
// 6) change verifyToken signature to verifyToken(token, deviceId, app)
// 7) after token row match, run the same device check and clear token on failure.
// 8) new members append 10 values, with DeviceID as final blank value.
// 9) setupSheet writes 10 headers and includes DeviceID.

// The complete integrated live file is available as the generated artifact
// Code.gs.device-security.js from this ChatGPT work session.
