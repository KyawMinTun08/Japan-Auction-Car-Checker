from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")
ANDROID = (ROOT / "android-app/app/src/main/java/com/kyawmintun/jacc/MainActivity.kt").read_text(encoding="utf-8")


def test_login_form_exposes_mobile_friendly_remember_control() -> None:
    assert 'id="rememberLogin"' in INDEX
    assert "Save Login on this device" in INDEX
    assert 'autocomplete="current-password"' in INDEX
    assert 'name="password"' in INDEX


def test_saved_password_is_encrypted_and_not_written_to_local_storage() -> None:
    assert "crypto.subtle.generateKey" in INDEX
    assert "crypto.subtle.encrypt" in INDEX
    assert "crypto.subtle.decrypt" in INDEX
    assert "indexedDB" in INDEX
    assert "localStorage.setItem(REMEMBER_LOGIN_KEY,'1')" in INDEX
    assert "localStorage.setItem(REMEMBER_LOGIN_KEY,password" not in INDEX
    assert "const REMEMBER_LOGIN_KEY = 'jacc_remember_login_v1';" in INDEX
    assert "nativeRememberLoginBridge" in INDEX
    assert "JACCRememberLogin" in INDEX


def test_invalid_session_can_fall_back_to_saved_login() -> None:
    assert "async function restoreRememberedLogin()" in INDEX
    assert "const remembered=await restoreRememberedLogin();" in INDEX
    assert "if(remembered.ok){markStartupStage('LOGIN_RESTORE_OK','SESSION_OK');return true;}" in INDEX
    assert "await clearRememberedLogin();" in INDEX
    assert "secure Save Login မရနိုင်ပါ" in INDEX


def test_explicit_logout_and_account_control_remove_saved_login() -> None:
    assert "async function forgetSavedLogin()" in INDEX
    assert 'onclick="forgetSavedLogin()"' in INDEX
    assert "await clearRememberedLogin();location.reload();" in INDEX


def test_pwa_cache_and_android_webview_keep_the_new_flow() -> None:
    assert "jacc-2026.08.20-startup-diagnostics-v6" in SW
    assert "domStorageEnabled = true" in ANDROID
    assert "databaseEnabled = true" in ANDROID
    assert "clearCache(true)" in ANDROID
    assert "WebSettings.LOAD_NO_CACHE" in ANDROID
    assert "startupRecoveryAttempted" in ANDROID
    assert "recovery=2026.08.20.5" in ANDROID
    assert "clearFormData" not in ANDROID
    assert "clearHistory" in ANDROID


if __name__ == "__main__":
    raise SystemExit("Run with pytest -q phase1/tests/test_save_login.py")
