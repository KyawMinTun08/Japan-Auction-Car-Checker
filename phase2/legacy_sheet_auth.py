"""Scoped server-key injection for legacy Apps Script membership callers.

The legacy bot still contains several direct ``httpx.AsyncClient`` calls for
membership administration and background jobs. Rewriting every large handler
at once would increase rollout risk, so this module replaces only the
``legacy_bot.httpx`` global with a small proxy.

The proxy injects ``SHEET_SERVER_KEY`` only when all of these are true:

* the request URL is the configured JACC ``SHEET_WEBHOOK``;
* the request payload contains a protected membership action; and
* the request uses JSON, query parameters, or form data.

The current production Apps Script ``doGet`` is price-data only. One historical
broadcast caller still sends ``GET ?action=getMembers``; the proxy converts only
that protected Sheet request to authenticated POST JSON so the server key never
appears in a URL and the public price-data doGet contract stays unchanged.

All unrelated HTTP requests and all other modules keep the original httpx
module unchanged. Install before ``legacy_bot.main()`` registers handlers.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import phase2_membership_guard


_PROTECTED_ACTIONS = frozenset(
    {
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
)

_legacy: Any | None = None


def _runtime() -> Any:
    global _legacy
    if _legacy is None:
        import legacy_bot

        _legacy = legacy_bot
    return _legacy


def _same_sheet_url(url: object, configured: object) -> bool:
    return str(url or "").rstrip("/") == str(configured or "").rstrip("/")


def _protected_action(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    action = str(payload.get("action") or "").strip()
    return action if action in _PROTECTED_ACTIONS else ""


def _secure_request_kwargs(url: object, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Copy and authenticate one protected legacy Sheet request.

    The caller's original payload is never mutated. Missing credentials fail
    before any network request is attempted.
    """

    runtime = _runtime()
    if not _same_sheet_url(url, getattr(runtime, "SHEET_WEBHOOK", "")):
        return kwargs

    for field in ("json", "params", "data"):
        payload = kwargs.get(field)
        if not _protected_action(payload):
            continue

        server_key = phase2_membership_guard._sheet_server_key()
        if not server_key:
            raise RuntimeError("SHEET_SERVER_KEY is not configured")

        secured = dict(payload)
        # Always overwrite caller-provided input with the Railway-owned value.
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
    """Authenticate protected requests and retire the legacy GET member route."""

    secured_kwargs = _secure_request_kwargs(url, kwargs)
    normalised_method = str(method or "").upper()

    if (
        normalised_method == "GET"
        and _same_sheet_url(url, getattr(_runtime(), "SHEET_WEBHOOK", ""))
        and _protected_action(secured_kwargs.get("params"))
    ):
        updated = dict(secured_kwargs)
        payload = dict(updated.pop("params"))
        updated["json"] = payload
        return "POST", updated

    return str(method), secured_kwargs


def _authenticated_client_class(base_client):
    class AuthenticatedLegacyAsyncClient(base_client):
        _jacc_phase2_sheet_auth_client = True

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
    _jacc_phase2_sheet_auth_proxy = True

    def __init__(self, original_module: Any) -> None:
        self._original_module = original_module
        self.AsyncClient = _authenticated_client_class(original_module.AsyncClient)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original_module, name)


def install() -> SimpleNamespace:
    """Patch only ``legacy_bot.httpx`` and remain safe on repeated installs."""

    runtime = _runtime()
    current = runtime.httpx
    if getattr(current, "_jacc_phase2_sheet_auth_proxy", False):
        return SimpleNamespace(
            httpx=current,
            protected_actions=_PROTECTED_ACTIONS,
        )

    proxy = _HttpxProxy(current)
    runtime.httpx = proxy
    return SimpleNamespace(
        httpx=proxy,
        protected_actions=_PROTECTED_ACTIONS,
    )
