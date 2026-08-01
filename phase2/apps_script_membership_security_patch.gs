/**
 * JACC Phase 2 Apps Script membership security preflight.
 *
 * STAGED ONLY — do not deploy by itself.
 *
 * Deployment contract:
 * 1. Set Script Property JACC_SERVER_KEY to a new random secret.
 * 2. Set the same value as Railway environment variable SHEET_SERVER_KEY.
 * 3. Install the scoped Railway legacy Sheet-auth proxy.
 * 4. Insert the preflight call immediately after parsing data in doPost(e).
 * 5. Insert the same preflight at the start of doGet(e) because the legacy
 *    broadcast-photo path reads getMembers with query parameters.
 * 6. Deploy the payment-approval patch in the same Apps Script version.
 * 7. Deploy a new Apps Script version and run the Phase 2 acceptance tests.
 *
 * Never put the key in this file, GitHub, the website, Flutter assets, logs,
 * Telegram messages, or Google Sheet cells.
 */

var JACC_SERVER_KEY_PROPERTY = "JACC_SERVER_KEY";
var JACC_MEMBER_SCHEMA_CANONICAL = [
  "USERID",
  "USERNAME",
  "STARTDATE",
  "EXPIREDATE",
  "STATUS",
  "CANCELCOUNT",
  "PASSWORD",
  "PACKAGE",
  "TOKEN",
  "DEVICEID"
];

var JACC_PRIVILEGED_MEMBER_ACTIONS = {
  saveMember: true,
  approveMembershipPayment: true,
  getMembers: true,
  getPassword: true,
  resetPassword: true,
  updateMemberId: true,
  getBackupCSV: true,
  updateStatus: true,
  resetMemberDevice: true
};

function jaccCanonicalHeader_(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

function jaccSha256Bytes_(value) {
  return Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    String(value || ""),
    Utilities.Charset.UTF_8
  );
}

function jaccConstantTimeEqual_(left, right) {
  var a = jaccSha256Bytes_(left);
  var b = jaccSha256Bytes_(right);
  if (a.length !== b.length) return false;

  var difference = 0;
  for (var i = 0; i < a.length; i++) {
    difference |= (a[i] ^ b[i]);
  }
  return difference === 0;
}

function jaccServerKeyCheck_(data) {
  var configured = String(
    PropertiesService.getScriptProperties()
      .getProperty(JACC_SERVER_KEY_PROPERTY) || ""
  ).trim();

  if (!configured) {
    return {
      ok: false,
      status: "error",
      message: "server_key_not_configured"
    };
  }

  var provided = String(
    (data && (data.serverKey || data.server_key)) || ""
  ).trim();

  if (!provided || !jaccConstantTimeEqual_(configured, provided)) {
    return {
      ok: false,
      status: "error",
      message: "unauthorized"
    };
  }

  return {ok: true, status: "ok"};
}

function jaccMemberSchemaHealth_() {
  var ss = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  if (!sheet) {
    return {
      ok: false,
      status: "error",
      message: "members_sheet_missing"
    };
  }

  var actual = sheet.getRange(1, 1, 1, 10).getDisplayValues()[0]
    .map(jaccCanonicalHeader_);
  var mismatches = [];

  for (var i = 0; i < JACC_MEMBER_SCHEMA_CANONICAL.length; i++) {
    if (actual[i] !== JACC_MEMBER_SCHEMA_CANONICAL[i]) {
      mismatches.push({
        column: i + 1,
        expected: JACC_MEMBER_SCHEMA_CANONICAL[i],
        actual: actual[i] || ""
      });
    }
  }

  if (mismatches.length) {
    return {
      ok: false,
      status: "error",
      message: "member_schema_mismatch",
      schemaVersion: "JACC_MEMBERS_V2_AJ",
      mismatches: mismatches
    };
  }

  return {
    ok: true,
    status: "ok",
    message: "member_schema_ok",
    schemaVersion: "JACC_MEMBERS_V2_AJ",
    columns: JACC_MEMBER_SCHEMA_CANONICAL.length
  };
}

/**
 * Return null when the request may continue. Return a JSON response object when
 * doPost(e) or doGet(e) must stop immediately.
 */
function jaccMembershipPreflight_(data) {
  var action = String((data && data.action) || "").trim();

  // Safe diagnostic: returns column names/version only, never member rows.
  if (action === "memberSchemaHealth") {
    return jaccMemberSchemaHealth_();
  }

  if (!JACC_PRIVILEGED_MEMBER_ACTIONS[action]) {
    return null;
  }

  var auth = jaccServerKeyCheck_(data);
  if (!auth.ok) return auth;

  var schema = jaccMemberSchemaHealth_();
  if (!schema.ok) return schema;

  return null;
}

/**
 * REQUIRED doPost(e) integration, immediately after JSON.parse:
 *
 *   var data = JSON.parse(e.postData.contents);
 *   var membershipGuard = jaccMembershipPreflight_(data);
 *   if (membershipGuard) return _json(membershipGuard);
 *
 * REQUIRED doGet(e) integration, before routing e.parameter actions:
 *
 *   var data = (e && e.parameter) ? e.parameter : {};
 *   var membershipGuard = jaccMembershipPreflight_(data);
 *   if (membershipGuard) return _json(membershipGuard);
 *
 * The doPost switch must also route:
 *
 *   case "approveMembershipPayment":
 *     return _json(jaccApproveMembershipPayment_(data));
 *
 * Keep verifyLogin and verifyToken public. They authenticate with a member
 * password/token and must never receive JACC_SERVER_KEY from browser code.
 */
