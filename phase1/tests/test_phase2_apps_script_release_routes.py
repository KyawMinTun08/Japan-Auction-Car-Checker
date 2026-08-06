from __future__ import annotations

from pathlib import Path


ROUTES = Path("phase2/apps_script_release_routes.gs")


def _source() -> str:
    return ROUTES.read_text(encoding="utf-8")


def test_release_router_runs_preflight_before_protected_actions() -> None:
    source = _source()
    preflight = source.index("jaccMembershipPreflight_(data)")
    payment = source.index('case "approveMembershipPayment"')
    reset = source.index('case "resetMemberDevice"')
    assert preflight < payment
    assert preflight < reset
    assert "if (guard) return jaccPhase2Handled_(guard)" in source


def test_release_router_handles_only_new_phase2_actions() -> None:
    source = _source()
    assert "jaccApproveMembershipPayment_(data)" in source
    assert "jaccResetMemberDevice_(data)" in source
    assert "return jaccPhase2NotHandled_()" in source
    for legacy_action in ("saveMember", "getMembers", "verifyLogin", "verifyToken"):
        assert f'case "{legacy_action}"' not in source


def test_release_router_documents_minimal_post_only_integration() -> None:
    source = _source()
    assert "var phase2 = jaccPhase2PreflightAndRoute_(data)" in source
    assert "if (phase2.handled) return _json(phase2.response)" in source
    assert "before handlePhase3PaymentAction_(data)" in source
    assert "current production doGet(e) unchanged" in source
    assert "authenticated POST JSON" in source
    assert "URL query parameters" in source
    assert "Existing legacy switch/cases remain" in source


def test_release_router_contains_no_secret() -> None:
    source = _source()
    assert "SHEET_SERVER_KEY=" not in source
    assert "JACC_SERVER_KEY=" not in source
    assert "sk-" not in source
    assert "AIza" not in source
