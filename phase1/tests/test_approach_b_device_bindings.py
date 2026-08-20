import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODE = (ROOT / "Code.gs").read_text(encoding="utf-8")
BINDINGS = (ROOT / "apps-script" / "device-bindings.gs").read_text(encoding="utf-8")
LEGACY_PATCH = (ROOT / "apps-script" / "device-security-patch.gs").read_text(encoding="utf-8")
WEB = (ROOT / "index.html").read_text(encoding="utf-8")
FLUTTER = (ROOT / "flutter_app" / "lib" / "main.dart").read_text(encoding="utf-8")
JDM = (ROOT / "jdm_lookup_service.py").read_text(encoding="utf-8")
PAYMENT = (ROOT / "website_payment_upload.py").read_text(encoding="utf-8")
RESET = (ROOT / "device_reset_patch.py").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "phase1_production_launcher.py").read_text(encoding="utf-8")
SW = (ROOT / "sw.js").read_text(encoding="utf-8")


def test_members_columns_remain_a_to_i_and_no_j_device_column_is_active():
    expected = {
        'C_USERID': 0,
        'C_USERNAME': 1,
        'C_START': 2,
        'C_EXPIRE': 3,
        'C_STATUS': 4,
        'C_CANCELCOUNT': 5,
        'C_PASSWORD': 6,
        'C_PACKAGE': 7,
        'C_TOKEN': 8,
    }
    for name, index in expected.items():
        assert re.search(rf"var\s+{name}\s*=\s*{index};", CODE)
    assert "C_DEVICEID" not in BINDINGS
    assert "function _verifyAndBindDevice_" in BINDINGS


def test_backend_accepts_device_context_on_all_core_routes():
    assert 'verifyLogin(data.password, data.deviceId, data.app)' in CODE
    assert 'verifyToken(data.token, data.deviceId, data.app, data.userId)' in CODE
    assert 'function verifyLogin(password, deviceId, app)' in CODE
    assert 'function verifyToken(token, deviceId, app, userId)' in CODE
    assert "case \"resetMemberDevice\":" in CODE
    assert "_authorizeFinanceReport_(data.serverKey)" in CODE
    assert "function _authorizeWebMember_(token, userId, deviceId, app)" in CODE


def test_separate_binding_and_session_sheets_store_hashes_and_revoke_sessions():
    assert "var DEVICE_BINDINGS_SHEET = 'DeviceBindings';" in BINDINGS
    assert "var AUTH_SESSIONS_SHEET = 'AuthSessions';" in BINDINGS
    assert "JACC_DEVICE_HASH_SECRET" in BINDINGS
    assert "Utilities.DigestAlgorithm.SHA_256" in BINDINGS
    assert "_revokeMemberSessions_" in BINDINGS
    assert "sessionHash" in BINDINGS
    assert "deviceHash" in BINDINGS


def test_old_patch_is_non_executable_archive():
    assert "DEPRECATED ARCHIVE" in LEGACY_PATCH
    assert "function verifyAndBindDevice_" not in LEGACY_PATCH
    assert "function resetMemberDevice" not in LEGACY_PATCH


def test_frontend_propagates_device_context_to_secondary_authenticated_calls():
    assert "function sessionDeviceFields()" in WEB
    assert "getSearchWatches" in WEB and "sessionDeviceFields()" in WEB
    assert "getMyRequestsWeb" in WEB and "sessionDeviceFields()" in WEB
    assert "X-JACC-Device-ID" in WEB
    assert "X-JACC-App" in WEB


def test_flutter_uses_contract_compatible_installation_id_and_client_marker():
    assert "?app=flutter&jacc_app=1" in FLUTTER
    assert "build=2026.08.20.5" in FLUTTER
    assert "Random.secure()" in FLUTTER
    assert "return 'JACC-$hex';" in FLUTTER
    assert "body.action === 'getData'" in FLUTTER


def test_telegram_reset_is_admin_only_and_uses_server_key():
    assert "if not _legacy.ADMIN_IDS or user_id not in _legacy.ADMIN_IDS" in RESET
    assert '"resetMemberDevice"' in RESET
    assert '"serverKey"' in RESET
    assert "import device_reset_patch" in LAUNCHER


def test_railway_adapters_forward_device_context():
    assert 'payload["deviceId"]' in JDM
    assert 'payload["app"]' in JDM
    assert "X-JACC-Device-ID" in JDM
    assert "X-JACC-App" in JDM
    assert 'payload["deviceId"] = device_id' in PAYMENT
    assert 'data.get("message") or data.get("msg")' in PAYMENT


def test_pwa_cache_version_matches_frontend_app_version():
    assert "APP_VERSION     = '2026.08.20-startup-diagnostics-v8';" in WEB
    assert "params.get('app')==='flutter'" in WEB
    assert "params.set('build','2026.08.20.5')" in WEB
    assert "jacc-2026.08.20-startup-diagnostics-v8" in SW
