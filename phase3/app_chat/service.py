"""Staged Railway API for JACC in-app Broker–Customer chat.

This module is intentionally not imported by any production launcher.
It validates the existing Phase 2 Apps Script v4 membership/device session on
*every* request and uses the Supabase service role only from Railway.

No session token, device ID, password, message body or service key is logged.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx
from aiohttp import web


_DEVICE_RE = re.compile(r"^JACC-[a-f0-9]{48}$")
_REQUEST_CODE_RE = re.compile(r"^[A-Z][A-Z0-9-]{3,31}$")
_ALLOWED_APPS = {"web", "pwa", "flutter"}
_MAX_JSON_BYTES = 16_384
_MAX_MESSAGE_CHARS = 4_000
_MAX_REASON_CHARS = 500


class ChatAuthError(RuntimeError):
    """The membership/device session is missing or rejected."""


class ChatInputError(RuntimeError):
    """The client supplied an invalid bounded input."""


class ChatBackendError(RuntimeError):
    """A protected backend call failed."""


@dataclass(frozen=True)
class ChatConfig:
    sheet_webhook: str
    supabase_url: str
    service_role_key: str
    allowed_origins: frozenset[str]
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "ChatConfig":
        sheet_webhook = os.environ.get("SHEET_WEBHOOK", "").strip()
        supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
        service_role_key = os.environ.get(
            "SUPABASE_SERVICE_ROLE_KEY", ""
        ).strip()
        origins = frozenset(
            origin.strip().rstrip("/")
            for origin in os.environ.get(
                "JACC_CHAT_ALLOWED_ORIGINS", ""
            ).split(",")
            if origin.strip()
        )
        if not sheet_webhook or not supabase_url or not service_role_key:
            raise ValueError(
                "SHEET_WEBHOOK, SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY are required"
            )
        if not origins:
            raise ValueError("JACC_CHAT_ALLOWED_ORIGINS is required")
        return cls(
            sheet_webhook=sheet_webhook,
            supabase_url=supabase_url,
            service_role_key=service_role_key,
            allowed_origins=origins,
        )


@dataclass(frozen=True)
class VerifiedActor:
    profile_id: str
    telegram_user_id: int
    role: str
    member_user_id: str


class ChatSessionVerifier:
    """Verify Phase 2 membership/device state, then map to Supabase profile."""

    def __init__(self, config: ChatConfig) -> None:
        self._config = config
        self._service_headers = {
            "apikey": config.service_role_key,
            "Authorization": f"Bearer {config.service_role_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _required_text(
        payload: dict[str, Any],
        key: str,
        *,
        max_length: int,
    ) -> str:
        value = str(payload.get(key) or "").strip()
        if not value or len(value) > max_length:
            raise ChatAuthError(f"{key}_invalid")
        return value

    async def verify(self, payload: dict[str, Any]) -> VerifiedActor:
        auth = payload.get("auth")
        if not isinstance(auth, dict):
            raise ChatAuthError("auth_missing")

        token = self._required_text(auth, "token", max_length=512)
        member_user_id = self._required_text(auth, "userId", max_length=24)
        device_id = self._required_text(auth, "deviceId", max_length=64)
        client_app = self._required_text(auth, "app", max_length=16).lower()

        if not member_user_id.isdigit():
            raise ChatAuthError("user_id_invalid")
        if not _DEVICE_RE.fullmatch(device_id):
            raise ChatAuthError("device_id_invalid")
        if client_app not in _ALLOWED_APPS:
            raise ChatAuthError("client_app_invalid")

        verification_payload = {
            "action": "verifyToken",
            "token": token,
            "userId": member_user_id,
            "deviceId": device_id,
            "app": client_app,
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    self._config.sheet_webhook,
                    headers={"Content-Type": "text/plain;charset=utf-8"},
                    content=json.dumps(
                        verification_payload,
                        separators=(",", ":"),
                    ),
                )
        except httpx.HTTPError as exc:
            raise ChatBackendError("membership_backend_unavailable") from exc

        if response.is_error:
            raise ChatBackendError("membership_backend_rejected_http")

        try:
            result = response.json()
        except ValueError as exc:
            raise ChatBackendError("membership_backend_invalid_json") from exc

        if str(result.get("status") or "").lower() != "ok":
            reason = str(
                result.get("message")
                or result.get("error")
                or result.get("msg")
                or "session_rejected"
            ).strip().lower()
            raise ChatAuthError(reason[:80])

        returned_user_id = str(result.get("userId") or member_user_id).strip()
        if returned_user_id != member_user_id:
            raise ChatAuthError("session_user_mismatch")

        telegram_user_id = int(member_user_id)
        url = f"{self._config.supabase_url}/rest/v1/jacc_profiles"
        params = {
            "telegram_user_id": f"eq.{telegram_user_id}",
            "select": "id,role,account_active,telegram_user_id",
            "limit": "1",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds
            ) as client:
                profile_response = await client.get(
                    url,
                    headers=self._service_headers,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise ChatBackendError("profile_lookup_unavailable") from exc

        if profile_response.is_error:
            raise ChatBackendError("profile_lookup_failed")

        profiles = profile_response.json()
        if not profiles:
            raise ChatAuthError("profile_not_found")
        profile = profiles[0]
        if not profile.get("account_active"):
            raise ChatAuthError("profile_inactive")

        return VerifiedActor(
            profile_id=str(profile["id"]),
            telegram_user_id=telegram_user_id,
            role=str(profile.get("role") or "customer"),
            member_user_id=member_user_id,
        )


class ChatStore:
    """Service-role-only Supabase RPC wrapper."""

    def __init__(self, config: ChatConfig) -> None:
        self._base_url = config.supabase_url
        self._timeout = config.timeout_seconds
        self._headers = {
            "apikey": config.service_role_key,
            "Authorization": f"Bearer {config.service_role_key}",
            "Content-Type": "application/json",
        }

    async def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base_url}/rest/v1/rpc/{name}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    headers=self._headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ChatBackendError("chat_backend_unavailable") from exc

        if response.is_error:
            # Do not relay raw database detail to the client because it can
            # contain schema names and internal values.
            raise ChatBackendError(
                _safe_rpc_error(response.text, response.status_code)
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ChatBackendError("chat_backend_invalid_json") from exc


class SlidingWindowLimiter:
    """Small per-process abuse guard; database idempotency remains authoritative."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        events = self._events[key]
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True


class AppChatService:
    def __init__(
        self,
        config: ChatConfig,
        *,
        verifier: ChatSessionVerifier | None = None,
        store: ChatStore | None = None,
    ) -> None:
        self.config = config
        self.verifier = verifier or ChatSessionVerifier(config)
        self.store = store or ChatStore(config)
        self.send_limiter = SlidingWindowLimiter(30, 60.0)
        self.general_limiter = SlidingWindowLimiter(180, 60.0)

    def routes(self) -> list[web.RouteDef]:
        return [
            web.post("/api/v1/chat/threads", self.list_threads),
            web.post("/api/v1/chat/open", self.open_thread),
            web.post("/api/v1/chat/messages", self.list_messages),
            web.post("/api/v1/chat/send", self.send_text),
            web.post("/api/v1/chat/read", self.mark_read),
            web.post("/api/v1/chat/close", self.close_thread),
        ]

    async def _prepare(
        self,
        request: web.Request,
    ) -> tuple[dict[str, Any], VerifiedActor]:
        _assert_origin(request, self.config.allowed_origins)
        if request.content_length is not None:
            if request.content_length <= 0 or request.content_length > _MAX_JSON_BYTES:
                raise ChatInputError("payload_size_invalid")
        if request.content_type not in {
            "application/json",
            "text/plain",
        }:
            raise ChatInputError("content_type_invalid")

        try:
            payload = await request.json(loads=json.loads)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ChatInputError("invalid_json") from exc
        if not isinstance(payload, dict):
            raise ChatInputError("payload_invalid")

        actor = await self.verifier.verify(payload)
        if not self.general_limiter.allow(actor.profile_id):
            raise web.HTTPTooManyRequests(
                text=json.dumps({"ok": False, "error": "rate_limited"}),
                content_type="application/json",
            )
        return payload, actor

    async def list_threads(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._list_threads)

    async def _list_threads(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        limit = _bounded_int(payload.get("limit"), 1, 100, 50)
        rows = await self.store.rpc(
            "jacc_chat_list_threads",
            {"p_actor_id": actor.profile_id, "p_limit": limit},
        )
        return {"ok": True, "threads": list(rows or [])}

    async def open_thread(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._open_thread)

    async def _open_thread(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        request_code = str(payload.get("requestCode") or "").strip().upper()
        if not _REQUEST_CODE_RE.fullmatch(request_code):
            raise ChatInputError("request_code_invalid")
        rows = await self.store.rpc(
            "jacc_chat_open_by_request_code",
            {
                "p_request_code": request_code,
                "p_actor_id": actor.profile_id,
            },
        )
        thread = _first_row(rows)
        return {"ok": True, "thread": thread}

    async def list_messages(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._list_messages)

    async def _list_messages(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        thread_id = _uuid_text(payload.get("threadId"), "thread_id_invalid")
        before = _optional_timestamp(payload.get("before"))
        limit = _bounded_int(payload.get("limit"), 1, 100, 50)
        rows = await self.store.rpc(
            "jacc_chat_list_messages",
            {
                "p_thread_id": thread_id,
                "p_actor_id": actor.profile_id,
                "p_before": before,
                "p_limit": limit,
            },
        )
        # SQL returns newest first for stable cursor pagination. The client can
        # reverse only for visual display.
        return {"ok": True, "messages": list(rows or [])}

    async def send_text(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._send_text)

    async def _send_text(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        if not self.send_limiter.allow(actor.profile_id):
            raise web.HTTPTooManyRequests(
                text=json.dumps({"ok": False, "error": "send_rate_limited"}),
                content_type="application/json",
            )
        thread_id = _uuid_text(payload.get("threadId"), "thread_id_invalid")
        client_message_id = _uuid_text(
            payload.get("clientMessageId"),
            "client_message_id_invalid",
        )
        body = str(payload.get("body") or "").strip()
        if not 1 <= len(body) <= _MAX_MESSAGE_CHARS:
            raise ChatInputError("message_length_invalid")
        rows = await self.store.rpc(
            "jacc_chat_send_text",
            {
                "p_thread_id": thread_id,
                "p_actor_id": actor.profile_id,
                "p_client_message_id": client_message_id,
                "p_body": body,
                "p_source": "app",
            },
        )
        return {"ok": True, "message": _first_row(rows)}

    async def mark_read(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._mark_read)

    async def _mark_read(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        thread_id = _uuid_text(payload.get("threadId"), "thread_id_invalid")
        last_message = payload.get("lastReadMessageId")
        last_message_id = (
            _uuid_text(last_message, "last_read_message_id_invalid")
            if last_message
            else None
        )
        unread = await self.store.rpc(
            "jacc_chat_mark_read",
            {
                "p_thread_id": thread_id,
                "p_actor_id": actor.profile_id,
                "p_last_read_message_id": last_message_id,
            },
        )
        if isinstance(unread, list):
            unread = unread[0] if unread else 0
        if isinstance(unread, dict):
            unread = next(iter(unread.values()), 0)
        return {"ok": True, "unreadCount": int(unread or 0)}

    async def close_thread(self, request: web.Request) -> web.Response:
        return await self._handle(request, self._close_thread)

    async def _close_thread(
        self, payload: dict[str, Any], actor: VerifiedActor
    ) -> dict[str, Any]:
        thread_id = _uuid_text(payload.get("threadId"), "thread_id_invalid")
        reason = str(payload.get("reason") or "").strip()
        if len(reason) > _MAX_REASON_CHARS:
            raise ChatInputError("close_reason_too_long")
        status = await self.store.rpc(
            "jacc_chat_close",
            {
                "p_thread_id": thread_id,
                "p_actor_id": actor.profile_id,
                "p_reason": reason or None,
            },
        )
        if isinstance(status, list):
            status = status[0] if status else "closed"
        if isinstance(status, dict):
            status = next(iter(status.values()), "closed")
        return {"ok": True, "status": str(status or "closed")}

    async def _handle(
        self,
        request: web.Request,
        operation: Callable[
            [dict[str, Any], VerifiedActor],
            Awaitable[dict[str, Any]],
        ],
    ) -> web.Response:
        origin = request.headers.get("Origin", "").rstrip("/")
        try:
            payload, actor = await self._prepare(request)
            result = await operation(payload, actor)
            response = web.json_response(result)
        except ChatAuthError as exc:
            response = web.json_response(
                {"ok": False, "error": str(exc) or "unauthorized"},
                status=401,
            )
        except ChatInputError as exc:
            response = web.json_response(
                {"ok": False, "error": str(exc) or "invalid_request"},
                status=400,
            )
        except ChatBackendError as exc:
            code = str(exc) or "chat_backend_error"
            status = 403 if code in {
                "chat_access_denied",
                "chat_send_denied",
            } else 409 if code in {
                "chat_thread_closed",
                "chat_request_has_no_assigned_broker",
            } else 502
            response = web.json_response(
                {"ok": False, "error": code},
                status=status,
            )
        except web.HTTPException as exc:
            response = exc
        except Exception:
            # The caller receives no traceback or data. Production integration
            # should log only an opaque correlation ID and exception class.
            response = web.json_response(
                {"ok": False, "error": "internal_error"},
                status=500,
            )

        if origin and origin in self.config.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def install_chat_routes(
    app: web.Application,
    config: ChatConfig | None = None,
    *,
    verifier: ChatSessionVerifier | None = None,
    store: ChatStore | None = None,
) -> AppChatService:
    """Install staged routes into an existing aiohttp application.

    Calling this function is the explicit production activation boundary. The
    Phase 3 branch does not call it from any launcher.
    """

    service = AppChatService(
        config or ChatConfig.from_env(),
        verifier=verifier,
        store=store,
    )
    app.add_routes(service.routes())
    return service


def _assert_origin(request: web.Request, allowed: frozenset[str]) -> None:
    origin = request.headers.get("Origin", "").strip().rstrip("/")
    # Native Android WebView and same-server calls may omit Origin. Browser
    # calls with an Origin must match the explicit allowlist.
    if origin and origin not in allowed:
        raise ChatAuthError("origin_denied")


def _uuid_text(value: Any, error: str) -> str:
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ChatInputError(error) from exc


def _optional_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) > 40:
        raise ChatInputError("before_invalid")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ChatInputError("before_invalid") from exc
    return text


def _bounded_int(
    value: Any,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ChatInputError("limit_invalid") from exc
    if parsed < minimum or parsed > maximum:
        raise ChatInputError("limit_invalid")
    return parsed


def _first_row(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        if not value or not isinstance(value[0], dict):
            raise ChatBackendError("chat_backend_empty_result")
        return value[0]
    if isinstance(value, dict):
        return value
    raise ChatBackendError("chat_backend_empty_result")


def _safe_rpc_error(detail: str, status_code: int) -> str:
    normalized = (detail or "").lower()
    known = {
        "chat_access_denied": "chat_access_denied",
        "chat_send_denied": "chat_send_denied",
        "chat_thread_closed": "chat_thread_closed",
        "chat_thread_not_found": "chat_thread_not_found",
        "chat_request_not_found": "chat_request_not_found",
        "chat_request_has_no_assigned_broker": (
            "chat_request_has_no_assigned_broker"
        ),
        "chat_actor_not_active": "chat_actor_not_active",
        "chat_message_length_invalid": "message_length_invalid",
        "chat_close_reason_too_long": "close_reason_too_long",
    }
    for marker, public_code in known.items():
        if marker in normalized:
            return public_code
    return f"chat_backend_http_{status_code}"


__all__ = [
    "AppChatService",
    "ChatAuthError",
    "ChatBackendError",
    "ChatConfig",
    "ChatInputError",
    "ChatSessionVerifier",
    "ChatStore",
    "VerifiedActor",
    "install_chat_routes",
]
