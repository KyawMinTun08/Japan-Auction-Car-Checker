from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import phase2_membership_guard
from phase2 import legacy_sheet_auth


class BaseClientStub:
    calls: list[tuple] = []

    async def request(self, method, url, *args, **kwargs):
        self.__class__.calls.append((method, url, args, kwargs))
        return {"ok": True}


class HttpxModuleStub:
    AsyncClient = BaseClientStub
    sentinel = "unchanged"


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    BaseClientStub.calls = []
    runtime = SimpleNamespace(
        SHEET_WEBHOOK="https://script.google.invalid/exec",
        SHEET_SERVER_KEY="RAILWAY-ONLY-KEY",
        httpx=HttpxModuleStub(),
    )
    monkeypatch.setattr(legacy_sheet_auth, "_legacy", runtime)
    monkeypatch.setattr(phase2_membership_guard, "_legacy", runtime)
    return runtime


def test_protected_json_request_gets_server_key_without_mutating_input(reset_state) -> None:
    runtime = reset_state
    original = {"action": "getMembers"}
    installed = legacy_sheet_auth.install()

    client = runtime.httpx.AsyncClient()
    asyncio.run(
        client.request(
            "POST",
            runtime.SHEET_WEBHOOK,
            json=original,
            timeout=10,
        )
    )

    assert original == {"action": "getMembers"}
    _, _, _, kwargs = BaseClientStub.calls[-1]
    assert kwargs["json"] == {
        "action": "getMembers",
        "serverKey": "RAILWAY-ONLY-KEY",
    }
    assert installed.httpx.sentinel == "unchanged"


def test_protected_get_params_are_authenticated(reset_state) -> None:
    runtime = reset_state
    legacy_sheet_auth.install()

    client = runtime.httpx.AsyncClient()
    asyncio.run(
        client.request(
            "GET",
            runtime.SHEET_WEBHOOK,
            params={"action": "getMembers"},
        )
    )

    _, _, _, kwargs = BaseClientStub.calls[-1]
    assert kwargs["params"]["serverKey"] == "RAILWAY-ONLY-KEY"


def test_unrelated_sheet_action_is_unchanged(reset_state) -> None:
    runtime = reset_state
    payload = {"action": "getCarsCount"}
    legacy_sheet_auth.install()

    client = runtime.httpx.AsyncClient()
    asyncio.run(
        client.request("POST", runtime.SHEET_WEBHOOK, json=payload)
    )

    _, _, _, kwargs = BaseClientStub.calls[-1]
    assert kwargs["json"] == payload
    assert "serverKey" not in kwargs["json"]


def test_protected_action_to_other_url_is_unchanged(reset_state) -> None:
    runtime = reset_state
    legacy_sheet_auth.install()

    client = runtime.httpx.AsyncClient()
    asyncio.run(
        client.request(
            "POST",
            "https://other.invalid/api",
            json={"action": "getMembers"},
        )
    )

    _, _, _, kwargs = BaseClientStub.calls[-1]
    assert kwargs["json"] == {"action": "getMembers"}


def test_missing_server_key_fails_before_network(reset_state) -> None:
    runtime = reset_state
    runtime.SHEET_SERVER_KEY = ""
    legacy_sheet_auth.install()

    client = runtime.httpx.AsyncClient()
    with pytest.raises(RuntimeError, match="SHEET_SERVER_KEY"):
        asyncio.run(
            client.request(
                "POST",
                runtime.SHEET_WEBHOOK,
                json={"action": "getPassword", "userId": "123"},
            )
        )

    assert BaseClientStub.calls == []


def test_install_is_idempotent(reset_state) -> None:
    runtime = reset_state
    first = legacy_sheet_auth.install().httpx
    second = legacy_sheet_auth.install().httpx

    assert first is second
    assert runtime.httpx is first
