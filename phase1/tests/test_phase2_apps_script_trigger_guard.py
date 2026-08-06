from __future__ import annotations

from pathlib import Path


PATCH = Path("phase2/apps_script_trigger_guard.gs")


def _source() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_trigger_health_detects_only_exact_legacy_handler() -> None:
    source = _source()
    assert 'JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER = "monthlyPasswordReset"' in source
    assert "ScriptApp.getProjectTriggers()" in source
    assert "trigger.getHandlerFunction()" in source
    assert "handler !== JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER" in source
    assert "monthlyPasswordResetTriggerCount" in source
    assert "monthlyPasswordResetEnabled" in source


def test_disable_helper_deletes_only_matching_triggers() -> None:
    source = _source()
    function_body = source.split(
        "function jaccDisableMonthlyPasswordResetTriggers_()", 1
    )[1]
    assert "ScriptApp.deleteTrigger(trigger)" in function_body
    assert "handler !== JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER" in function_body
    assert "jaccPhase2TriggerHealth_()" in function_body
    assert 'status: health.safe ? "ok" : "error"' in function_body


def test_trigger_guard_is_not_exposed_as_web_route() -> None:
    source = _source()
    assert "function doPost" not in source
    assert "function doGet" not in source
    assert 'case "' not in source
    assert "manual editor/admin tools only" in source


def test_trigger_guard_contains_no_secret_or_member_data() -> None:
    source = _source()
    assert "JACC_SERVER_KEY=" not in source
    assert "SHEET_SERVER_KEY=" not in source
    assert "BOT_TOKEN=" not in source
    assert "getDataRange" not in source
    assert "Members" not in source
