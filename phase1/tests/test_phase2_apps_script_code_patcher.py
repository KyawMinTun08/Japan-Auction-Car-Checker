from __future__ import annotations

import pytest

from phase2.apply_apps_script_code_gs import (
    AppsScriptPatchError,
    apply_patch_text,
)


CURRENT_CONTRACT = """function doPost(e) {
  try {
    var lock = LockService.getScriptLock();
    lock.waitLock(30000);
    var ss   = SpreadsheetApp.openById(SS_ID);
    var data = JSON.parse(e.postData.contents);
    var payload = data;
    var phase3 = handlePhase3PaymentAction_(data);

    switch (data.action) {
      case "verifyLogin":
        var loginResult = verifyLogin(data.password, data.deviceId, data.app);
        return _json(loginResult);
    }
  } finally {
    lock.releaseLock();
  }
}

function verifyLogin(password, deviceId, app) {
  var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName(MEMBERS);
  var memberPackage = "WEB";
  var i = 1;

    // Flutter app: first successful login binds the member to this app install.
    var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
    if (!deviceCheck.ok) return deviceCheck;

  return {status:"ok"};
}

function verifyToken(token, deviceId, app) {
  var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName(MEMBERS);
  var memberPackage = "WEB";
  var i = 1;
  var now = new Date();

    var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
    if (!deviceCheck.ok) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      return deviceCheck;
    }

    var expireDate = new Date();
    if (!expireDate || expireDate < now) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      // Clear expired token
      return {status:"error", message:"expired"};
    }
    return {status:"ok"};
}

function verifyAndBindDevice_(sheet, rowNumber, deviceId, app) {
  return {ok:true};
}

function getDataRoute(data) {
 case 'getData': {
  var tokenResult = verifyToken(data.token);
  if (tokenResult.status !== 'ok') return _json({status:'error', msg:'invalid_token'});
  return _json({status:'ok'});
 }
}
"""


def test_transformer_patches_exact_current_contract() -> None:
    patched = apply_patch_text(CURRENT_CONTRACT)

    assert "var phase2 = jaccPhase2PreflightAndRoute_(data);" in patched
    assert "if (phase2.handled) return _json(phase2.response);" in patched
    assert patched.index("jaccPhase2PreflightAndRoute_") < patched.index(
        "handlePhase3PaymentAction_"
    )
    assert patched.count("jaccEnforceDeviceBinding_(") == 2
    assert "verifyToken(data.token, data.deviceId, data.app)" in patched
    assert "if (tokenResult.status !== 'ok') return _json(tokenResult);" in patched
    assert "var tokenResult = verifyToken(data.token);" not in patched
    assert (
        "var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);"
        not in patched
    )


def test_transformer_is_idempotent() -> None:
    patched = apply_patch_text(CURRENT_CONTRACT)
    assert apply_patch_text(patched) == patched


def test_transformer_keeps_public_do_get_out_of_scope() -> None:
    source = """function doGet(e) { return priceData(); }\n""" + CURRENT_CONTRACT
    patched = apply_patch_text(source)
    assert "function doGet(e) { return priceData(); }" in patched


def test_transformer_refuses_unknown_drift() -> None:
    with pytest.raises(AppsScriptPatchError, match="doPost contract drift"):
        apply_patch_text(CURRENT_CONTRACT.replace("var payload = data;", ""))


def test_device_binding_moves_after_expiry_validation() -> None:
    patched = apply_patch_text(CURRENT_CONTRACT)
    verify_token = patched.split("function verifyToken", 1)[1].split(
        "function verifyAndBindDevice_", 1
    )[0]

    assert verify_token.index('message:"expired"') < verify_token.index(
        "jaccEnforceDeviceBinding_("
    )
