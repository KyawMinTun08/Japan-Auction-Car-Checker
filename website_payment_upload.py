"""Authenticated website payment-slip upload adapter for the existing Railway bot.

The adapter deliberately forwards the submitted image to the existing Telegram
admin review flow instead of persisting payment images in a new database. The
existing in-memory pending_payment map remains the source of truth for the
current bot process; a restart requires the member to submit the slip again.
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
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # Unit tests can exercise the HTTP adapter without Telegram installed.
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_METHODS = {"kpay", "wave", "cb"}


class WebsitePaymentHttp:
    """Small authenticated multipart endpoint mounted beside the bot health API."""

    def __init__(
        self,
        *,
        bot: Any,
        sheet_webhook: str,
        admin_ids: list[int],
        pending_payment: dict[int, dict[str, Any]],
        plan_prices: dict[str, dict[int, int]],
        plan_names: dict[str, str],
        payment_method_info: dict[str, dict[str, Any]],
        gemini_reader: Callable[[bytes], Awaitable[dict[str, Any]]],
        parse_amount: Callable[[Any], int | None],
        transaction_key: Callable[[dict[str, Any]], str],
        payment_summary: Callable[[list[dict[str, Any]]], tuple[int, list[str]]],
        payment_qr_getter: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.bot = bot
        self.sheet_webhook = str(sheet_webhook or "").strip()
        self.admin_ids = [int(value) for value in admin_ids if str(value).isdigit()]
        self.pending_payment = pending_payment
        self.plan_prices = plan_prices
        self.plan_names = plan_names
        self.payment_method_info = payment_method_info
        self.gemini_reader = gemini_reader
        self.parse_amount = parse_amount
        self.transaction_key = transaction_key
        self.payment_summary = payment_summary
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
        self._rate_buckets: dict[int, deque[float]] = {}

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

    def _rate_allowed(self, user_id: int) -> bool:
        now = time.monotonic()
        bucket = self._rate_buckets.setdefault(user_id, deque())
        while bucket and now - bucket[0] > self.rate_window_seconds:
            bucket.popleft()
        if len(bucket) >= self.rate_limit:
            return False
        bucket.append(now)
        return True

    async def _verify_member(self, token: str, user_id: int, device_id: str, app_name: str) -> dict[str, Any]:
        if not self.sheet_webhook or not token or not user_id:
            return {"status": "error", "message": "web_access_required"}
        payload: dict[str, Any] = {
            "action": "verifyToken",
            "token": token,
            "userId": str(user_id),
        }
        if device_id:
            payload["deviceId"] = device_id
        if app_name:
            payload["app"] = app_name
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                response = await client.post(
                    self.sheet_webhook,
                    headers={"Content-Type": "text/plain"},
                    json=payload,
                )
            if response.is_error:
                return {"status": "error", "message": "session_unavailable"}
            data = response.json()
            if not isinstance(data, dict) or str(data.get("status", "")).lower() != "ok":
                return {"status": "error", "message": "invalid_session"}
            returned_id = str(data.get("userId", user_id)).strip()
            if returned_id and returned_id != str(user_id):
                return {"status": "error", "message": "member_mismatch"}
            package = str(data.get("package", "")).strip().upper()
            if package not in {"WEB", "WEB-PROMO"}:
                return {"status": "error", "message": "web_premium_required"}
            return data
        except Exception:
            logger.exception("Website payment session verification failed")
            return {"status": "error", "message": "session_unavailable"}

    async def _verify_payment_read_session(self, request: web.Request) -> dict[str, Any]:
        authorization = request.headers.get("Authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        raw_user_id = str(request.headers.get("X-JACC-User-ID", "")).strip()
        if not raw_user_id.isdigit() or len(raw_user_id) > 20:
            return {"status": "error", "message": "member_id_required"}
        return await self._verify_member(
            token,
            int(raw_user_id),
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
            logger.exception("Website slip image conversion failed")
            return data

    @staticmethod
    def _safe_label(value: Any, fallback: str, limit: int = 80) -> str:
        text = str(value or fallback).strip()
        text = re.sub(r"[\r\n`*_]", " ", text)
        return text[:limit] or fallback

    async def _notify_admins(self, user_id: int, pay_data: dict[str, Any], slips: list[dict[str, Any]], total_paid: int, expected: int) -> int:
        username = self._safe_label(pay_data.get("username"), str(user_id))
        package = self._safe_label(self.plan_names.get("WEB", "Web Premium"), "Web Premium")
        months = int(pay_data.get("months", 1))
        method = str(pay_data.get("method", "")).lower()
        method_label = self._safe_label(
            self.payment_method_info.get(method, {}).get("label", method.upper() or "—"),
            method.upper() or "—",
        )
        _, slip_lines = self.payment_summary(slips)
        status = "ပြည့်ပြီ" if total_paid == expected else f"{abs(expected - total_paid):,} ks ကွာနေသည်"
        admin_text = (
            "Payment Slip အသစ် — Website upload\n\n"
            f"User: {username}\n"
            f"ID: {user_id}\n"
            f"Package: {package} — {months} လ\n"
            f"Method: {method_label}\n"
            f"Expected: {expected:,} ks\n"
            f"Total received: {total_paid:,} ks — {status}\n\n"
            "Slip အားလုံးကို Payment app ထဲတွင် Transaction No. တစ်ခုချင်းစီစစ်ပြီးမှ Confirm လုပ်ပါ။"
        )
        markup = None
        if InlineKeyboardButton is not None and InlineKeyboardMarkup is not None:
            markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Message member", url=f"tg://user?id={user_id}")],
                    [
                        InlineKeyboardButton("Confirm", callback_data=f"slip_confirm_{user_id}"),
                        InlineKeyboardButton("Reject", callback_data=f"slip_no_{user_id}"),
                    ],
                ]
            )
        delivered = 0
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(chat_id=admin_id, text=admin_text, reply_markup=markup)
                for index, slip in enumerate(slips, 1):
                    file_bytes = slip.get("file_bytes")
                    if not file_bytes:
                        continue
                    info = slip.get("slip_info", {})
                    amount = int(slip.get("amount_num", 0) or 0)
                    txn = self._safe_label(info.get("TRANSACTION_NO", info.get("REFERENCE", "UNKNOWN")), "UNKNOWN")
                    photo = io.BytesIO(file_bytes)
                    photo.name = f"jacc-web-slip-{user_id}-{index}.jpg"
                    await self.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo,
                        caption=f"Website slip {index} — {amount:,} ks — Txn: {txn}",
                    )
                delivered += 1
            except Exception:
                logger.exception("Website payment admin notify failed for %s", admin_id)
        return delivered

    async def payment_methods(self, request: web.Request) -> web.Response:
        """Return safe payment labels/details without exposing Telegram file IDs."""
        if not self._allowed_origin(request):
            return self._json(request, {"status": "error", "code": "ORIGIN_NOT_ALLOWED"}, 403)
        session = await self._verify_payment_read_session(request)
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
        return self._json(request, {"status": "ok", "methods": methods})

    async def payment_qr(self, request: web.Request) -> web.StreamResponse:
        """Proxy a configured Telegram-hosted QR without exposing bot credentials."""
        if not self._allowed_origin(request):
            return self._json(request, {"status": "error", "code": "ORIGIN_NOT_ALLOWED"}, 403)
        session = await self._verify_payment_read_session(request)
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
            logger.exception("Payment QR proxy failed for %s", method)
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
            logger.exception("Website payment multipart parse failed")
            return self._json(request, {"status": "error", "code": "INVALID_UPLOAD"}, 400)

        raw_user_id = str(form.get("userId", "")).strip()
        if not raw_user_id.isdigit() or len(raw_user_id) > 20:
            return self._json(request, {"status": "error", "code": "MEMBER_ID_REQUIRED"}, 400)
        user_id = int(raw_user_id)
        device_id = str(form.get("deviceId", "")).strip()[:100]
        app_name = str(form.get("app", "web")).strip().lower()[:20]
        try:
            months = int(str(form.get("months", "1")).strip())
        except ValueError:
            months = 0
        method = str(form.get("method", "")).strip().lower()
        if months not in self.plan_prices.get("WEB", {}) or method not in ALLOWED_METHODS:
            return self._json(request, {"status": "error", "code": "PAYMENT_SELECTION_INVALID"}, 400)
        session = await self._verify_member(token, user_id, device_id, app_name)
        if str(session.get("status", "")).lower() != "ok":
            return self._json(request, {"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")}, 401)
        if not self._rate_allowed(user_id):
            return self._json(request, {"status": "error", "code": "RATE_LIMITED"}, 429)

        upload = form.get("slip")
        if upload is None or not hasattr(upload, "file"):
            return self._json(request, {"status": "error", "code": "SLIP_REQUIRED"}, 400)
        mime = str(getattr(upload, "content_type", "") or "").lower()
        if mime not in ALLOWED_MIME_TYPES:
            return self._json(request, {"status": "error", "code": "IMAGE_TYPE_NOT_ALLOWED"}, 415)
        file_bytes = upload.file.read(self.max_upload_bytes + 1)
        if len(file_bytes) > self.max_upload_bytes:
            return self._json(request, {"status": "error", "code": "FILE_TOO_LARGE"}, 413)
        if not self._valid_image_signature(file_bytes, mime):
            return self._json(request, {"status": "error", "code": "INVALID_IMAGE"}, 415)

        existing = self.pending_payment.get(user_id)
        expected = int(self.plan_prices["WEB"][months])
        if existing and existing.get("waiting_slip"):
            if (
                str(existing.get("package", "WEB")).upper() != "WEB"
                or int(existing.get("months", 0) or 0) != months
                or str(existing.get("method", "")).lower() != method
            ):
                return self._json(request, {"status": "error", "code": "PAYMENT_SESSION_CONFLICT"}, 409)
            pay_data = existing
        else:
            pay_data = {
                "package": "WEB",
                "months": months,
                "amount": expected,
                "method": method,
                "waiting_slip": True,
                "username": self._safe_label(session.get("username"), str(user_id)),
                "name": self._safe_label(session.get("username"), str(user_id)),
                "slips": [],
                "source": "website",
            }
            self.pending_payment[user_id] = pay_data

        ocr_bytes = self._ocr_bytes(file_bytes, mime)
        try:
            slip_info = await self.gemini_reader(ocr_bytes)
        except Exception:
            logger.exception("Website slip OCR failed")
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
        remaining = expected - total_paid
        if remaining > 0:
            return self._json(
                request,
                {"status": "pending", "code": "SLIP_RECEIVED", "totalPaid": total_paid, "remaining": remaining},
                202,
            )

        delivered = await self._notify_admins(user_id, pay_data, slips, total_paid, expected)
        if delivered == 0:
            return self._json(request, {"status": "error", "code": "ADMIN_NOTIFY_FAILED"}, 502)
        return self._json(
            request,
            {"status": "awaiting_admin", "code": "ADMIN_REVIEW_REQUIRED", "totalPaid": total_paid},
            202,
        )


def build_website_payment_http_service(
    *,
    bot: Any,
    sheet_webhook: str,
    admin_ids: list[int],
    pending_payment: dict[int, dict[str, Any]],
    plan_prices: dict[str, dict[int, int]],
    plan_names: dict[str, str],
    payment_method_info: dict[str, dict[str, Any]],
    gemini_reader: Callable[[bytes], Awaitable[dict[str, Any]]],
    parse_amount: Callable[[Any], int | None],
    transaction_key: Callable[[dict[str, Any]], str],
    payment_summary: Callable[[list[dict[str, Any]]], tuple[int, list[str]]],
    payment_qr_getter: Callable[[str], Awaitable[str]] | None = None,
) -> WebsitePaymentHttp | None:
    enabled = os.environ.get("PAYMENT_UPLOAD_ENABLED", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        logger.info("Website payment upload disabled by PAYMENT_UPLOAD_ENABLED")
        return None
    if not str(sheet_webhook or "").strip() or not admin_ids:
        logger.warning("Website payment upload disabled: SHEET_WEBHOOK or ADMIN_IDS missing")
        return None
    return WebsitePaymentHttp(
        bot=bot,
        sheet_webhook=sheet_webhook,
        admin_ids=admin_ids,
        pending_payment=pending_payment,
        plan_prices=plan_prices,
        plan_names=plan_names,
        payment_method_info=payment_method_info,
        gemini_reader=gemini_reader,
        parse_amount=parse_amount,
        transaction_key=transaction_key,
        payment_summary=payment_summary,
        payment_qr_getter=payment_qr_getter,
    )
