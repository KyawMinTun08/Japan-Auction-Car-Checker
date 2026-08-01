from __future__ import annotations

from pathlib import Path


PATCH = Path("phase2/apps_script_membership_security_patch.gs")


def _source() -> str:
    return PATCH.read_text(encoding="utf-8")


def test_patch_contains_no_literal_server_secret() -> None:
    source = _source()
    assert "JACC_SERVER_KEY_PROPERTY" in source
    assert 'getProperty(JACC_SERVER_KEY_PROPERTY)' in source
    assert "SHEET_SERVER_KEY" in source
    assert "sk-" not in source
    assert "AIza" not in source
    assert "Bearer " not in source


def test_privileged_member_actions_are_protected() -> None:
    source = _source()
    actions = {
        "saveMember",
        "approveMembershipPayment",
        "getMembers",
        "getPassword",
        "resetPassword",
        "updateMemberId",
        "getBackupCSV",
        "updateStatus",
        "resetMemberDevice",
    }
    for action in actions:
        assert f"{action}: true" in source

    assert "jaccServerKeyCheck_(data)" in source
    assert "if (!auth.ok) return auth" in source
    assert 'message: "server_key_not_configured"' in source
    assert 'message: "unauthorized"' in source


def test_member_schema_preflight_requires_live_a_to_j_contract() -> None:
    source = _source()
    expected = [
        "USERID",
        "USERNAME",
        "STARTDATE",
        "EXPIREDDATE",
        "STATUS",
        "CANCELCOUNT",
        "PASSWORD",
        "PACKAGE",
        "TOKEN",
        "DEVICEID",
    ]
    for header in expected:
        assert f'"{header}"' in source

    assert 'schemaVersion: "JACC_MEMBERS_V2_AJ"' in source
    assert 'message: "member_schema_mismatch"' in source
    assert 'action === "memberSchemaHealth"' in source


def test_member_login_and_token_routes_remain_public_by_design() -> None:
    source = _source()
    privileged_block = source.split(
        "var JACC_PRIVILEGED_MEMBER_ACTIONS = {", 1
    )[1].split("};", 1)[0]

    assert "verifyLogin" not in privileged_block
    assert "validateLogin" not in privileged_block
    assert "verifyToken" not in privileged_block
    assert "Keep verifyLogin and verifyToken public" in source


def test_patch_documents_atomic_rollout_contract() -> None:
    source = _source()
    assert "Set Script Property JACC_SERVER_KEY" in source
    assert "Railway environment variable SHEET_SERVER_KEY" in source
    assert "scoped Railway legacy Sheet-auth proxy" in source
    assert "doPost(e)" in source
    assert "doGet(e)" in source
    assert "e.parameter" in source
    assert 'case "approveMembershipPayment"' in source
    assert "jaccApproveMembershipPayment_(data)" in source
    assert "Never put the key" in source
