"""Guarded transformer for the current deployed JACC Code.gs contract.

This transformer is intentionally narrow. It patches only the exact Phase 2
integration points verified from the owner-supplied current Code.gs source and
refuses unknown drift.

It does not embed Apps Script secrets and does not add the Phase 2 .gs modules;
those remain separate files in the same Apps Script project.
"""

from __future__ import annotations

import argparse
from pathlib import Path


class AppsScriptPatchError(RuntimeError):
    """Raised when Code.gs no longer matches the reviewed release contract."""


_PHASE2_MARKER = "var phase2 = jaccPhase2PreflightAndRoute_(data);"

_POST_OLD = """    var data = JSON.parse(e.postData.contents);
    var payload = data;
    var phase3 = handlePhase3PaymentAction_(data);"""

_POST_NEW = """    var data = JSON.parse(e.postData.contents);
    var payload = data;
    var phase2 = jaccPhase2PreflightAndRoute_(data);
    if (phase2.handled) return _json(phase2.response);
    var phase3 = handlePhase3PaymentAction_(data);"""

_LOGIN_OLD = """    // Flutter app: first successful login binds the member to this app install.
    var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
    if (!deviceCheck.ok) return deviceCheck;"""

_LOGIN_NEW = """    // Phase 2: bind WEB access to one browser/PWA/Flutter installation.
    var deviceCheck = jaccEnforceDeviceBinding_(
      sheet,
      i + 1,
      {deviceId: deviceId, app: app},
      memberPackage
    );
    if (!deviceCheck.ok) return deviceCheck;"""

_TOKEN_EARLY_OLD = """    var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);
    if (!deviceCheck.ok) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      return deviceCheck;
    }

"""

_TOKEN_INSERT_OLD = """    if (!expireDate || expireDate < now) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      // Clear expired token
      return {status:"error", message:"expired"};
    }
    return {"""

_TOKEN_INSERT_NEW = """    if (!expireDate || expireDate < now) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      // Clear expired token
      return {status:"error", message:"expired"};
    }

    // Phase 2: enforce the same installation after package/status/expiry checks.
    var deviceCheck = jaccEnforceDeviceBinding_(
      sheet,
      i + 1,
      {deviceId: deviceId, app: app},
      memberPackage
    );
    if (!deviceCheck.ok) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      return deviceCheck;
    }

    return {"""

_GET_DATA_OLD = """ case 'getData': {
  var tokenResult = verifyToken(data.token);
  if (tokenResult.status !== 'ok') return _json({status:'error', msg:'invalid_token'});"""

_GET_DATA_NEW = """ case 'getData': {
  var tokenResult = verifyToken(data.token, data.deviceId, data.app);
  if (tokenResult.status !== 'ok') return _json(tokenResult);"""


def _replace_exactly_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise AppsScriptPatchError(
            f"{label} contract drift: expected exactly one reviewed anchor, found {count}"
        )
    return source.replace(old, new, 1)


def _validate_patched(source: str) -> None:
    required = (
        _PHASE2_MARKER,
        "if (phase2.handled) return _json(phase2.response);",
        "verifyToken(data.token, data.deviceId, data.app)",
        "if (tokenResult.status !== 'ok') return _json(tokenResult);",
        "{deviceId: deviceId, app: app}",
        "jaccEnforceDeviceBinding_(",
    )
    for marker in required:
        if marker not in source:
            raise AppsScriptPatchError(f"patched Code.gs is missing marker: {marker}")

    if source.count("jaccEnforceDeviceBinding_(") != 2:
        raise AppsScriptPatchError(
            "patched Code.gs must enforce device binding exactly in verifyLogin "
            "and verifyToken"
        )

    forbidden = (
        "var tokenResult = verifyToken(data.token);",
        "var deviceCheck = verifyAndBindDevice_(sheet, i + 1, deviceId, app);",
    )
    for marker in forbidden:
        if marker in source:
            raise AppsScriptPatchError(f"legacy device contract is still active: {marker}")


def apply_patch_text(source: str) -> str:
    """Return a guarded Phase 2 Code.gs candidate."""

    if _PHASE2_MARKER in source:
        _validate_patched(source)
        return source

    patched = _replace_exactly_once(source, _POST_OLD, _POST_NEW, "doPost")
    patched = _replace_exactly_once(
        patched, _LOGIN_OLD, _LOGIN_NEW, "verifyLogin device binding"
    )
    patched = _replace_exactly_once(
        patched, _TOKEN_EARLY_OLD, "", "verifyToken early raw device binding"
    )
    patched = _replace_exactly_once(
        patched,
        _TOKEN_INSERT_OLD,
        _TOKEN_INSERT_NEW,
        "verifyToken validated device binding",
    )
    patched = _replace_exactly_once(
        patched, _GET_DATA_OLD, _GET_DATA_NEW, "getData token/device propagation"
    )

    _validate_patched(patched)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Current Code.gs source")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the patched candidate here instead of replacing the input",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail unless the source is already patched and valid",
    )
    args = parser.parse_args()

    source = args.path.read_text(encoding="utf-8")
    patched = apply_patch_text(source)

    if args.check:
        if patched != source:
            raise AppsScriptPatchError("Code.gs still needs the Phase 2 patch")
        print("Apps Script Phase 2 Code.gs contract: valid")
        return 0

    target = args.output or args.path
    target.write_text(patched, encoding="utf-8")
    print(f"Apps Script Phase 2 Code.gs candidate written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
