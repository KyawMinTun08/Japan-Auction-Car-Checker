"""Website payment-slip upload adapter for JACC Google Login members.

Kept as a separate module from website_payment_upload.py rather than
extending it: that module's whole surface (user_id typed int, isdigit()
validation, Telegram inline-button callback_data tied to numeric ids
consumed by the existing slip_confirm_/slip_ok_/slip_no_ handlers) is
shared production code for Telegram-originated WEB members and must not be
touched by this feature. A Google Login member has a synthetic "G_<google
sub>" id, never a Telegram numeric id, so it gets its own upload endpoint
here and its own admin-approval path (the /googleapprove and /googlereject
bot commands in legacy_bot.py) instead of the existing button callbacks.

Every accepted slip is persisted to the durable Payment_Drafts sheet via
save_payment_draft before admins are notified, exactly like the existing
Telegram-submitted and website-submitted (Telegram-origin) slip paths, so a
Railway restart between "slip received" and "admin approves" cannot lose
the session.
"""
from __future__ import annotations

import io
import logging
import os
import re
import time
from collections import deque
from typing import Any, Awaitable, Callable

import httpx
from aiohttp import web

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_METHODS = {"kpay", "wave", "cb"}
GOOGLE_MEMBER_ID_PREFIX = "G_"


class GoogleMemberPaymentHttp:
    """Authenticated multipart endpoint for JACC Google Login payment slips."""

    def __init__(
        self,
        *,
        bot: Any,
        sheet_webhook: str,
        admin_ids: list[int],
        pending_payment: dict[Any, dict[str, Any]],
        plan_prices: dict[str, dict[int, int]],
        payment_method_info: dict[str, dict[str, Any]],
        gemini_reader: Callable[[bytes], Awaitable[dict[str, Any]]],
        parse_amount: Callable[[Any], int | None],
        transaction_key: Callable[[dict[str, Any]], str],
        payment_summary: Callable[[list[dict[str, Any]]], tuple[int, list[str]]],
        save_payment_draft: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        payment_qr_getter: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.bot = bot
        self.sheet_webhook = str(sheet_webhook or "").strip()
        self.admin_ids = [int(value) for value in admin_ids if str(value).isdigit()]
        self.pending_payment = pending_payment
        self.plan_prices = plan_prices
        self.payment_method_info = payment_method_info
        self.gemini_reader = gemini_reader
        self.parse_amount = parse_amount
        self.transaction_key = transaction_key
        self.payment_summary = payment_summary
        self.save_payment_draft = save_payment_draft
        self.payment_qr_getter = payment_qr_getter
        self.max_upload_bytes = min(
            MAX_UPLOAD_BYTES,
            max(256 * 1024, int(os.environ.get("PAYMENT_SLIP_MAX_BYTES", MAX_UPLOAD_BYTES))),
        )
        configured = os.environ.get(
            "PAYMENT_CORS_ORIGINS",
            "https://kyawmintun08.github.io,https://japan-auction-car-checker.pages.dev",
        )
        self.allowed_origins = {value.strip() for value in configured.split(",") if value.strip()}
        self.rate_window_seconds = 10 * 60
        self.rate_limit = 5
        self._rate_buckets: dict[str, deque[float]] = {}

    def _headers(self, request: web.Request) -> dict[str, str]:
        origin = request.headers.get("Origin", "")
        headers = {"Cache-Control": "no-store", "Vary": "Origin"}
        if origin in self.allowed_origins:
            headers.update(
                {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-JACC-User-ID, X-JACC-Device-ID, X-JACC-App",
                }
            )
        return headers

    def _json(self, request: web.Request, payload: dict[str, Any], status: int = 200) -> web.Response:
        return web.json_response(payload, status=status, headers=self._headers(request))

    async def options(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers=self._headers(request))

    def _allowed_origin(self, request: web.Request) -> bool:
        origin = request.headers.get("Origin", "")
        return not origin or origin in self.allowed_origins

    def _rate_allowed(self, member_id: str) -> bool:
        now = time.monotonic()
        bucket = self._rate_buckets.setdefault(member_id, deque())
        while bucket and now - bucket[0] > self.rate_window_seconds:
            bucket.popleft()
        if len(bucket) >= self.rate_limit:
            return False
        bucket.append(now)
        return True

    async def _verify_member(self, token: str, member_id: str, device_id: str, app_name: str) -> dict[str, Any]:
        if not self.sheet_webhook or not token or not member_id:
            return {"status": "error", "message": "web_access_required"}
        payload: dict[str, Any] = {
            "action": "verifyToken",
            "token": token,
            "userId": member_id,
        }
        if device_id:
            payload["deviceId"] = device_id
        if app_name:
            payload["app"] = app_name
        try:
            # Same Apps Script doPost() lock-contention exposure as every
            # other SHEET_WEBHOOK call in this project -- see
            # website_payment_upload.py's identical comment.
            async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
                response = await client.post(
                    self.sheet_webhook,
                    headers={"Content-Type": "text/plain"},
                    json=payload,
                )
            if response.is_error:
                return {"status": "error", "message": "session_unavailable"}
            data = response.json()
            if not isinstance(data, dict):
                return {"status": "error", "message": "invalid_session"}
            if str(data.get("status", "")).lower() != "ok":
                backend_message = str(data.get("message") or data.get("msg") or "invalid_session")
                if backend_message == "invalid_token":
                    backend_message = "invalid_session"
                return {"status": "error", "message": backend_message}
            returned_id = str(data.get("userId", member_id)).strip()
            if returned_id and returned_id != member_id:
                return {"status": "error", "message": "member_mismatch"}
            if not returned_id.startswith(GOOGLE_MEMBER_ID_PREFIX):
                # This endpoint is Google-Login-only. A Telegram-origin WEB
                # member (password login) must keep using the existing
                # website_payment_upload.py endpoint unchanged.
                return {"status": "error", "message": "google_login_required"}
            package = str(data.get("package", "")).strip().upper()
            if package not in {"WEB", "WEB-PROMO"}:
                return {"status": "error", "message": "web_premium_required"}
            return data
        except Exception:
            logger.exception("Google member payment session verification failed")
            return {"status": "error", "message": "session_unavailable"}

    async def _session(self, request: web.Request) -> dict[str, Any]:
        authorization = request.headers.get("Authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        member_id = str(request.headers.get("X-JACC-User-ID", "")).strip()
        if not member_id.startswith(GOOGLE_MEMBER_ID_PREFIX) or len(member_id) > 60:
            return {"status": "error", "message": "member_id_required"}
        return await self._verify_member(
            token,
            member_id,
            str(request.headers.get("X-JACC-Device-ID", "")).strip()[:100],
            str(request.headers.get("X-JACC-App", "web")).strip().lower()[:20],
        )

    @staticmethod
    def _valid_image_signature(data: bytes, mime: str) -> bool:
        if mime == "image/jpeg":
            return data.startswith(b"\xff\xd8\xff")
        if mime == "image/png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        if mime == "image/webp":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        return False

    @staticmethod
    def _ocr_bytes(data: bytes, mime: str) -> bytes:
        if mime == "image/jpeg":
            return data
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                converted = image.convert("RGB")
                output = io.BytesIO()
                converted.save(output, format="JPEG", quality=90, optimize=True)
                return output.getvalue()
        except Exception:
            logger.exception("Google member slip image conversion failed")
            return data

    @staticmethod
    def _safe_label(value: Any, fallback: str, limit: int = 80) -> str:
        text = str(value or fallback).strip()
        text = re.sub(r"[\r\n`*_]", " ", text)
        return text[:limit] or fallback

    async def _notify_admins(
        self,
        member_id: str,
        email: str,
        months: int,
        method: str,
        slips: list[dict[str, Any]],
        total_paid: int,
        expected: int,
    ) -> int:
        method_label = self._safe_label(
            self.payment_method_info.get(method, {}).get("label", method.upper() or "—"),
            method.upper() or "—",
        )
        _, slip_lines = self.payment_summary(slips)
        status = "ပြည့်ပြီ" if total_paid == expected else f"{abs(expected - total_paid):,} ks ကွာနေသည်"
        admin_text = (
            "Payment Slip အသစ် — Google Login signup (Telegram မရှိသူ)\n\n"
            f"Google Email: {self._safe_label(email, member_id)}\n"
            f"ID: {member_id}\n"
            f"Package: Web Premium — {months} လ\n"
            f"Method: {method_label}\n"
            f"Expected: {expected:,} ks\n"
            f"Total received: {total_paid:,} ks — {status}\n\n"
            "Slip အားလုံးကို Payment app ထဲတွင် Transaction No. တစ်ခုချင်းစီစစ်ပြီးမှ:\n"
            f"✅ Approve → /googleapprove {member_id}\n"
            f"❌ Reject → /googlereject {member_id}"
        )
        delivered = 0
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(chat_id=admin_id, text=admin_text)
                for index, slip in enumerate(slips, 1):
                    file_bytes = slip.get("file_bytes")
                    if not file_bytes:
                        continue
                    info = slip.get("slip_info", {})
                    amount = int(slip.get("amount_num", 0) or 0)
                    txn = self._safe_label(info.get("TRANSACTION_NO", info.get("REFERENCE", "UNKNOWN")), "UNKNOWN")
                    photo = io.BytesIO(file_bytes)
                    photo.name = f"jacc-google-slip-{member_id}-{index}.jpg"
                    await self.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo,
                        caption=f"Google slip {index} — {amount:,} ks — Txn: {txn}",
                    )
                delivered += 1
            except Exception:
                logger.exception("Google member payment admin notify failed for %s", admin_id)
        return delivered

    async def payment_methods(self, request: web.Request) -> web.Response:
        """Return safe payment labels/details without exposing Telegram file IDs."""
        if not self._allowed_origin(request):
            return self._json(request, {"status": "error", "code": "ORIGIN_NOT_ALLOWED"}, 403)
        session = await self._session(request)
        if str(session.get("status", "")).lower() != "ok":
            return self._json(request, {"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")}, 401)
        methods = []
        for method in ("kpay", "wave", "cb"):
            info = self.payment_method_info.get(method, {})
            methods.append(
                {
                    "key": method,
                    "label": self._safe_label(info.get("label"), method.upper()),
                    "name": self._safe_label(info.get("name"), method.upper()),
                    "number": self._safe_label(info.get("number"), "Contact admin"),
                    "owner": self._safe_label(info.get("owner"), "JACC payment account"),
                }
            )
        plans = [
            {"months": months, "amount": int(amount)}
            for months, amount in sorted(self.plan_prices.get("WEB", {}).items())
        ]
        return self._json(request, {"status": "ok", "methods": methods, "plans": plans})

    async def payment_qr(self, request: web.Request) -> web.StreamResponse:
        """Proxy a configured Telegram-hosted QR without exposing bot credentials."""
        if not self._allowed_origin(request):
            return self._json(request, {"status": "error", "code": "ORIGIN_NOT_ALLOWED"}, 403)
        session = await self._session(request)
        if str(session.get("status", "")).lower() != "ok":
            return self._json(request, {"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")}, 401)
        method = str(request.match_info.get("method", "")).strip().lower()
        if method not in ALLOWED_METHODS:
            return self._json(request, {"status": "error", "code": "PAYMENT_METHOD_INVALID"}, 400)
        if self.payment_qr_getter is None:
            return self._json(request, {"status": "error", "code": "QR_UNAVAILABLE"}, 503)
        try:
            file_id = str(await self.payment_qr_getter(method) or "").strip()
            if not file_id:
                return self._json(request, {"status": "error", "code": "QR_NOT_CONFIGURED"}, 404)
            telegram_file = await self.bot.get_file(file_id)
            output = io.BytesIO()
            downloader = getattr(telegram_file, "download_to_memory", None)
            if callable(downloader):
                await downloader(out=output)
            else:
                byte_downloader = getattr(telegram_file, "download_as_bytearray", None)
                if not callable(byte_downloader):
                    return self._json(request, {"status": "error", "code": "QR_DOWNLOAD_UNSUPPORTED"}, 502)
                output.write(bytes(await byte_downloader()))
            data = output.getvalue()
            if not data:
                return self._json(request, {"status": "error", "code": "QR_EMPTY"}, 502)
            file_path = str(getattr(telegram_file, "file_path", "") or "").lower()
            extension = file_path.rsplit(".", 1)[-1] if "." in file_path else "jpg"
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(extension, "image/jpeg")
            headers = self._headers(request)
            headers.update(
                {
                    "Cache-Control": "private, max-age=300",
                    "Content-Disposition": f'inline; filename="jacc-{method}-qr.{extension}"',
                }
            )
            return web.Response(body=data, content_type=mime, headers=headers)
        except Exception:
            logger.exception("Google member payment QR proxy failed for %s", method)
            return self._json(request, {"status": "error", "code": "QR_PROXY_FAILED"}, 502)

    async def upload(self, request: web.Request) -> web.Response:
        if not self._allowed_origin(request):
            return self._json(request, {"status": "error", "code": "ORIGIN_NOT_ALLOWED"}, 403)
        if request.content_length and request.content_length > self.max_upload_bytes + 64 * 1024:
            return self._json(request, {"status": "error", "code": "FILE_TOO_LARGE"}, 413)
        authorization = request.headers.get("Authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        try:
            form = await request.post()
        except web.HTTPRequestEntityTooLarge:
            return self._json(request, {"status": "error", "code": "FILE_TOO_LARGE"}, 413)
        except Exception:
            logger.exception("Google member payment multipart parse failed")
            return self._json(request, {"status": "error", "code": "INVALID_UPLOAD"}, 400)

        member_id = str(form.get("userId", "")).strip()
        if not member_id.startswith(GOOGLE_MEMBER_ID_PREFIX) or len(member_id) > 60:
            return self._json(request, {"status": "error", "code": "MEMBER_ID_REQUIRED"}, 400)
        device_id = str(form.get("deviceId", "")).strip()[:100]
        app_name = str(form.get("app", "web")).strip().lower()[:20]
        try:
            months = int(str(form.get("months", "1")).strip())
        except ValueError:
            months = 0
        method = str(form.get("method", "")).strip().lower()
        if months not in self.plan_prices.get("WEB", {}) or method not in ALLOWED_METHODS:
            return self._json(request, {"status": "error", "code": "PAYMENT_SELECTION_INVALID"}, 400)
        session = await self._verify_member(token, member_id, device_id, app_name)
        if str(session.get("status", "")).lower() != "ok":
            return self._json(request, {"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")}, 401)
        if not self._rate_allowed(member_id):
            return self._json(request, {"status": "error", "code": "RATE_LIMITED"}, 429)

        upload_file = form.get("slip")
        if upload_file is None or not hasattr(upload_file, "file"):
            return self._json(request, {"status": "error", "code": "SLIP_REQUIRED"}, 400)
        mime = str(getattr(upload_file, "content_type", "") or "").lower()
        if mime not in ALLOWED_MIME_TYPES:
            return self._json(request, {"status": "error", "code": "IMAGE_TYPE_NOT_ALLOWED"}, 415)
        file_bytes = upload_file.file.read(self.max_upload_bytes + 1)
        if len(file_bytes) > self.max_upload_bytes:
            return self._json(request, {"status": "error", "code": "FILE_TOO_LARGE"}, 413)
        if not self._valid_image_signature(file_bytes, mime):
            return self._json(request, {"status": "error", "code": "INVALID_IMAGE"}, 415)

        expected = int(self.plan_prices["WEB"][months])
        existing = self.pending_payment.get(member_id)
        if existing and existing.get("waiting_slip"):
            if int(existing.get("months", 0) or 0) != months or str(existing.get("method", "")).lower() != method:
                return self._json(request, {"status": "error", "code": "PAYMENT_SESSION_CONFLICT"}, 409)
            pay_data = existing
        else:
            pay_data = {
                "package": "WEB",
                "months": months,
                "amount": expected,
                "method": method,
                "waiting_slip": True,
                "username": self._safe_label(session.get("username"), member_id),
                "name": self._safe_label(session.get("username"), member_id),
                "slips": [],
                "source": "google_website",
            }
            self.pending_payment[member_id] = pay_data

        ocr_bytes = self._ocr_bytes(file_bytes, mime)
        try:
            slip_info = await self.gemini_reader(ocr_bytes)
        except Exception:
            logger.exception("Google member slip OCR failed")
            slip_info = {}
        amount_num = self.parse_amount(slip_info.get("AMOUNT")) if isinstance(slip_info, dict) else None
        if amount_num is None:
            return self._json(request, {"status": "error", "code": "SLIP_AMOUNT_UNREADABLE"}, 422)
        txn_key = self.transaction_key(slip_info)
        slips = pay_data.setdefault("slips", [])
        if txn_key and any(item.get("txn_key") == txn_key for item in slips):
            return self._json(request, {"status": "error", "code": "DUPLICATE_TRANSACTION"}, 409)
        slips.append({"slip_info": slip_info, "amount_num": amount_num, "txn_key": txn_key, "file_bytes": file_bytes})
        pay_data["slip_info"] = slip_info
        pay_data["file_bytes"] = file_bytes
        total_paid, _ = self.payment_summary(slips)
        pay_data["total_paid"] = total_paid
        pay_data["userId"] = member_id

        try:
            draft_result = await self.save_payment_draft(pay_data)
        except Exception:
            logger.exception("Google member payment draft persistence raised user=%s", member_id)
            draft_result = None
        if not isinstance(draft_result, dict) or draft_result.get("status") != "ok":
            logger.error("Google member payment draft persistence failed user=%s result=%s", member_id, draft_result)
            return self._json(request, {"status": "error", "code": "DRAFT_SAVE_FAILED"}, 503)

        remaining = expected - total_paid
        if remaining > 0:
            return self._json(
                request,
                {"status": "pending", "code": "SLIP_RECEIVED", "totalPaid": total_paid, "remaining": remaining},
                202,
            )

        delivered = await self._notify_admins(
            member_id, session.get("username", member_id), months, method, slips, total_paid, expected
        )
        if delivered == 0:
            return self._json(request, {"status": "error", "code": "ADMIN_NOTIFY_FAILED"}, 502)
        return self._json(
            request,
            {"status": "awaiting_admin", "code": "ADMIN_REVIEW_REQUIRED", "totalPaid": total_paid},
            202,
        )


def build_google_member_payment_http_service(
    *,
    bot: Any,
    sheet_webhook: str,
    admin_ids: list[int],
    pending_payment: dict[Any, dict[str, Any]],
    plan_prices: dict[str, dict[int, int]],
    payment_method_info: dict[str, dict[str, Any]],
    gemini_reader: Callable[[bytes], Awaitable[dict[str, Any]]],
    parse_amount: Callable[[Any], int | None],
    transaction_key: Callable[[dict[str, Any]], str],
    payment_summary: Callable[[list[dict[str, Any]]], tuple[int, list[str]]],
    save_payment_draft: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    payment_qr_getter: Callable[[str], Awaitable[str]] | None = None,
) -> GoogleMemberPaymentHttp | None:
    enabled = os.environ.get("GOOGLE_LOGIN_PAYMENT_ENABLED", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.info("Google Login payment upload disabled by GOOGLE_LOGIN_PAYMENT_ENABLED")
        return None
    if not str(sheet_webhook or "").strip() or not admin_ids:
        logger.warning("Google Login payment upload disabled: SHEET_WEBHOOK or ADMIN_IDS missing")
        return None
    return GoogleMemberPaymentHttp(
        bot=bot,
        sheet_webhook=sheet_webhook,
        admin_ids=admin_ids,
        pending_payment=pending_payment,
        plan_prices=plan_prices,
        payment_method_info=payment_method_info,
        gemini_reader=gemini_reader,
        parse_amount=parse_amount,
        transaction_key=transaction_key,
        payment_summary=payment_summary,
        save_payment_draft=save_payment_draft,
        payment_qr_getter=payment_qr_getter,
    )
