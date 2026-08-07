from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HELPER = (ROOT / "phase2" / "website_device_binding.js").read_text(encoding="utf-8")


def test_production_login_sends_device_identity():
    assert 'data-jacc-device-binding="v4"' in INDEX
    assert "JACCDeviceBinding.withDevice('verifyLogin'" in INDEX
    assert "JSON.stringify({action:'verifyLogin',password:pw})" not in INDEX


def test_production_data_and_session_use_same_device_contract():
    assert "JACCDeviceBinding.withDevice('getData'" in INDEX
    assert "async function restoreSession()" in INDEX
    assert "JACCDeviceBinding.saveSession(" in INDEX
    assert "JACCDeviceBinding.clearSession()" in INDEX


def test_device_helper_contract_is_v4_and_secure_random():
    assert "const SESSION_VERSION = 'v4';" in HELPER
    assert "const INSTALLATION_KEY = 'jacc_installation_id';" in HELPER
    assert "source.getRandomValues(bytes)" in HELPER
    assert "'verifyLogin', 'verifyToken', 'getData'" in HELPER


def test_device_errors_are_not_collapsed_into_generic_server_error():
    assert "JACCDeviceBinding.isDeviceError(result)" in INDEX
    assert "JACCDeviceBinding.deviceErrorMessage(result)" in INDEX
