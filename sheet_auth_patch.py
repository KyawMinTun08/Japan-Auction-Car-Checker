"""Authenticate protected Apps Script membership calls from the Railway bot.

The Apps Script Phase 2 preflight requires a server-owned key for privileged
membership and payment actions. This patch accepts either Railway's
SHEET_SERVER_KEY or the existing JACC_SERVER_KEY variable, injects it only for
calls to the configured SHEET_WEBHOOK, never logs it, and never adds it to
unrelated network requests.
"""

from __future__ import annotations

import os
from typing import Any

import queue_launcher as _queue


_legacy = _queue._legacy
_PROTECTED_ACTIONS = frozenset(
    {
        "saveMember",
        "approveMembershipPayment",
        "approvePayment",
        "rejectPayment",
        "approveWebPayment",
        "rejectWebPayment",
        "getMembers",
        "getPassword",
        "resetPassword",
        "updateMemberId",
        "getBackupCSV",
        "updateStatus",
        "resetMemberDevice",
    }
)


def _sheet_server_key() -> str:
    return str(
        getattr(_legacy, "SHEET_SERVER_KEY", "")
        or getattr(_legacy, "JACC_SERVER_KEY", "")
        or os.environ.get("SHEET_SERVER_KEY", "")
        or os.environ.get("JACC_SERVER_KEY", "")
    ).strip()


def _same_sheet_url(url: object) -> bool:
    configured = getattr(_legacy, "SHEET_WEBHOOK", "")
    return str(url or "").rstrip("/") == str(configured or "").rstrip("/")


def _protected_action(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    action = str(payload.get("action") or "").strip()
    return action if action in _PROTECTED_ACTIONS else ""


def _secure_request_kwargs(url: object, kwargs: dict[str, Any]) -> dict[str, Any]:
    if not _same_sheet_url(url):
        return kwargs

    for field in ("json", "params", "data"):
        payload = kwargs.get(field)
        if not _protected_action(payload):
            continue

        server_key = _sheet_server_key()
        if not server_key:
            raise RuntimeError("Railway server key is not configured")

        secured = dict(payload)
        secured["serverKey"] = server_key
        updated = dict(kwargs)
        updated[field] = secured
        return updated

    return kwargs


def _normalise_sheet_request(
    method: object,
    url: object,
    kwargs: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    secured_kwargs = _secure_request_kwargs(url, kwargs)
    normalised_method = str(method or "").upper()

    if (
        normalised_method == "GET"
        and _same_sheet_url(url)
        and _protected_action(secured_kwargs.get("params"))
    ):
        updated = dict(secured_kwargs)
        payload = dict(updated.pop("params"))
        updated["json"] = payload
        return "POST", updated

    return str(method), secured_kwargs


def _authenticated_client_class(base_client):
    class AuthenticatedLegacyAsyncClient(base_client):
        _jacc_sheet_auth_client = True

        async def request(self, method, url, *args, **kwargs):
            normalised_method, secured_kwargs = _normalise_sheet_request(
                method,
                url,
                kwargs,
            )
            return await super().request(
                normalised_method,
                url,
                *args,
                **secured_kwargs,
            )

    AuthenticatedLegacyAsyncClient.__name__ = "AuthenticatedLegacyAsyncClient"
    return AuthenticatedLegacyAsyncClient


class _HttpxProxy:
    _jacc_sheet_auth_proxy = True

    def __init__(self, original_module: Any) -> None:
        self._original_module = original_module
        self.AsyncClient = _authenticated_client_class(original_module.AsyncClient)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original_module, name)


def install() -> None:
    current = _legacy.httpx
    if getattr(current, "_jacc_sheet_auth_proxy", False):
        return
    _legacy.httpx = _HttpxProxy(current)
    _legacy.logger.info("Protected Sheet authentication patch installed")


install()
