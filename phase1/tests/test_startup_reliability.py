from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "index.html"
SW = ROOT / "sw.js"
DEVICE = ROOT / "phase2/website_device_binding.js"


def test_frontend_uses_bounded_data_fetch_and_cache_fallback() -> None:
    source = INDEX.read_text(encoding="utf-8")
    assert "const REQUEST_TIMEOUT_MS = 12000" in source
    assert "const DATA_CACHE_KEY = 'jacc_cars_cache_v2'" in source
    assert "const DATA_CACHE_SCHEMA_VERSION = 'jacc-cars-v2'" in source
    assert "parsed.version==='2026.08.19-ai-console-v2'" in source
    assert "schemaVersion:DATA_CACHE_SCHEMA_VERSION" in source
    assert "function dataCacheKey()" in source
    assert "function readCarsCache()" in source
    assert "function writeCarsCache(cars)" in source
    assert "if(!SESSION||!SESSION.userId)return null;" in source
    assert "fetchWithTimeout(WEBHOOK" in source
    assert "async function fetchJsonWithTimeout" in source
    assert "const DATA_REQUEST_TIMEOUT_MS = 45000;" in source
    assert "const APP_VERSION     = '2026.08.20-startup-diagnostics-v6';" in source
    assert "const STARTUP_WATCHDOG_TIMEOUT_MS = 60000;" in source
    assert "armStartupWatchdog(timeoutMs=STARTUP_WATCHDOG_TIMEOUT_MS)" in source
    assert "},DATA_REQUEST_TIMEOUT_MS);" in source
    assert "function armStartupWatchdog" in source
    assert "function showStartupRecoveryError" in source
    assert "function markStartupStage(stage, code='')" in source
    assert "function safeStartupCode(error,prefix)" in source
    assert "Error code: <strong>" in source
    assert "async function retryStartupData()" in source
    assert "if(!SESSION||!SESSION.token||!SESSION.userId){location.reload();return;}" in source
    assert "try{await init();}finally{startupRetryInFlight=false;}" in source
    assert "onclick=\"retryStartupData()\"" in source
    assert "init().finally(()=>{loadMyRequests();syncSavedSearchAlerts();});" in source
    assert "await Promise.race([result.text(),timeout])" in source
    assert "Live data မရသေးပါ — Cached data ဖြင့် ဆက်သုံးနိုင်ပါတယ်" in source
    assert "verifyStoredSession({webhook:WEBHOOK,timeoutMs:REQUEST_TIMEOUT_MS})" in source


def test_service_worker_delivers_startup_fix() -> None:
    source = SW.read_text(encoding="utf-8")
    assert "jacc-2026.08.20-startup-diagnostics-v6" in source
    assert "BASE_PATH + '/phase2/website_device_binding.js'" in source


def test_payment_api_origin_is_allowed_by_csp() -> None:
    source = INDEX.read_text(encoding="utf-8")
    assert "https://japan-auction-car-checker-production-3624.up.railway.app" in source


def test_device_binding_has_abortable_session_timeout() -> None:
    source = DEVICE.read_text(encoding="utf-8")
    assert "function postJson(webhook, payload, fetchImpl, timeoutMs)" in source
    assert "request_timeout" in source
    assert "config.timeoutMs" in source
    assert "AbortController" in source
