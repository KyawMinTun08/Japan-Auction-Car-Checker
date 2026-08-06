from __future__ import annotations

from pathlib import Path

import pytest

from phase2.apply_website_device_binding import (
    WebsitePatchError,
    apply_patch_text,
)


FRONTEND = Path("phase2/website_device_binding.js")
BACKEND = Path("phase2/apps_script_device_binding_patch.gs")
INDEX = Path("index.html")


LEGACY_AUTH_CONTRACT = """</div>
</div>

<script>
const SHEET_ID
-- fixture --
const SESSION_KEY = 'jan_session';
const SESSION_VER = 'v3';
const MAX_LOGIN_TRIES = 5;
-- fixture --
body:JSON.stringify({action:'verifyLogin',password:pw})
-- fixture --
      if(reason==='wrong_password'||reason.includes('password')){
-- fixture --
    SESSION={ver:SESSION_VER,token:result.token,userId:result.userId,username:result.username,package:result.package,expireDate:result.expireDate,loginTime:Date.now()};
    localStorage.setItem(SESSION_KEY,JSON.stringify(SESSION));
-- fixture --
function checkSession(){
  try{
    const s=localStorage.getItem(SESSION_KEY);if(!s)return false;
    const parsed=JSON.parse(s);if(!parsed||!parsed.token)return false;
    if(parsed.ver!==SESSION_VER){localStorage.removeItem(SESSION_KEY);return false;}
    SESSION=parsed;return true;
  }catch(e){return false;}
}
-- fixture --
body:JSON.stringify({action:'getData',token:SESSION.token})
-- fixture --
    if(result.status!=='ok')throw new Error(result.msg||'Data fetch failed');
-- fixture --
window.addEventListener('DOMContentLoaded',function(){
  if(checkSession()){showApp();}
  else{document.getElementById('loginOverlay').style.display='flex';document.getElementById('loadingOverlay').style.display='none';}
});
"""


def _assert_generated_contract(source: str) -> None:
    assert 'data-jacc-device-binding="v4"' in source
    assert "const SESSION_VER = JACCDeviceBinding.SESSION_VERSION" in source
    assert "JACCDeviceBinding.withDevice('verifyLogin'" in source
    assert "JACCDeviceBinding.withDevice('getData'" in source
    assert "async function restoreSession()" in source
    assert "verifyStoredSession({webhook:WEBHOOK})" in source
    assert "window.addEventListener('DOMContentLoaded',async function()" in source
    assert "function checkSession()" not in source
    assert "JSON.stringify({action:'verifyLogin',password:pw})" not in source
    assert "JSON.stringify({action:'getData',token:SESSION.token})" not in source


def test_frontend_uses_secure_stable_installation_id() -> None:
    source = FRONTEND.read_text(encoding="utf-8")

    assert "jacc_installation_id" in source
    assert "getRandomValues" in source
    assert "Uint8Array(24)" in source
    assert "JACC-[a-f0-9]{48}" in source
    assert "SESSION_VERSION = 'v4'" in source
    assert "logout keeps the installation ID" in source
    assert "IP addresses are logging/diagnostic data only" in source


def test_frontend_protects_login_token_restore_and_data_access() -> None:
    source = FRONTEND.read_text(encoding="utf-8")

    for action in ("verifyLogin", "verifyToken", "getData"):
        assert action in source
    assert "DEVICE_ACTIONS" in source
    assert "deviceId: getInstallationId" in source
    assert "verifyStoredSession" in source
    assert "clearSession(storage)" in source
    assert "device_mismatch" in source
    assert "device_required" in source
    assert "device_lock_busy" in source


def test_frontend_never_contains_server_key_or_member_password() -> None:
    source = FRONTEND.read_text(encoding="utf-8")

    assert "SHEET_SERVER_KEY" not in source
    assert "JACC_SERVER_KEY" not in source
    assert "serverKey" not in source
    assert "password:" not in source


def test_apps_script_stores_hash_not_raw_device_id() -> None:
    source = BACKEND.read_text(encoding="utf-8")

    assert "Utilities.computeDigest" in source
    assert "DigestAlgorithm.SHA_256" in source
    assert 'JACC_DEVICE_PREFIX = "v2:"' in source
    assert "cell.setValue(fingerprint)" in source
    assert "cell.setValue(request.deviceId)" not in source
    assert "deviceFingerprint" not in source
    assert "JACC_DEVICE_COLUMN = 10" in source


def test_apps_script_one_device_policy_is_fail_closed_and_lock_safe() -> None:
    source = BACKEND.read_text(encoding="utf-8")

    for app in ("web", "pwa", "flutter"):
        assert f"{app}: true" in source
    for reason in (
        "device_required",
        "device_invalid",
        "device_lock_busy",
        "device_mismatch",
    ):
        assert reason in source
    assert "lock.hasLock()" in source
    assert "if (!lock.hasLock())" in source
    assert "lock.waitLock(10000)" in source
    assert "releaseHere = true" in source
    assert "if (releaseHere) lock.releaseLock()" in source
    assert "non-reentrant lock" in source


def test_device_reset_is_server_protected_by_contract() -> None:
    source = BACKEND.read_text(encoding="utf-8")
    security = Path("phase2/apps_script_membership_security_patch.gs").read_text(
        encoding="utf-8"
    )

    assert "jaccResetMemberDevice_" in source
    assert "clearContent()" in source
    assert "resetMemberDevice: true" in security
    assert "must remain inside JACC_PRIVILEGED_MEMBER_ACTIONS" in source


def test_website_patcher_transforms_legacy_auth_contract() -> None:
    patched = apply_patch_text(LEGACY_AUTH_CONTRACT)

    assert patched != LEGACY_AUTH_CONTRACT
    _assert_generated_contract(patched)


def test_current_index_contains_generated_contract_and_is_idempotent() -> None:
    current = INDEX.read_text(encoding="utf-8")

    _assert_generated_contract(current)
    assert apply_patch_text(current) == current


def test_website_patcher_refuses_unknown_drift() -> None:
    with pytest.raises(WebsitePatchError):
        apply_patch_text("<html><body>unknown website</body></html>")
