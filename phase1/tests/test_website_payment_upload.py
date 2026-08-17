from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass, field

import httpx
from aiohttp import web

from website_payment_upload import WebsitePaymentHttp


@dataclass
class FakeBot:
    messages: list[dict] = field(default_factory=list)
    photos: list[dict] = field(default_factory=list)

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)

    async def send_photo(self, **kwargs):
        photo = kwargs.get("photo")
        self.photos.append(
            {"chat_id": kwargs.get("chat_id"), "caption": kwargs.get("caption"), "bytes": photo.read()}
        )


async def _start_server(app: web.Application):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


async def _exercise_upload_flow():
    async def sheet_verify(request):
        payload = await request.json()
        if payload.get("token") != "valid-token":
            return web.json_response({"status": "error", "message": "invalid_token"})
        return web.json_response(
            {"status": "ok", "userId": "123", "username": "QA Premium", "package": "WEB"}
        )

    sheet_app = web.Application()
    sheet_app.router.add_post("/verify", sheet_verify)
    sheet_runner, sheet_url = await _start_server(sheet_app)

    bot = FakeBot()
    pending = {}

    async def read_slip(_data):
        return {
            "TYPE": "KPay",
            "AMOUNT": "30000",
            "TRANSACTION_NO": "WEB-TEST-001",
            "DATE": "17/08/2026",
            "TIME": "10:00",
        }

    service = WebsitePaymentHttp(
        bot=bot,
        sheet_webhook=sheet_url + "/verify",
        admin_ids=[999],
        pending_payment=pending,
        plan_prices={"WEB": {1: 30000, 2: 55000, 3: 80000}},
        plan_names={"WEB": "Web Premium"},
        payment_method_info={"kpay": {"label": "KPay"}},
        gemini_reader=read_slip,
        parse_amount=lambda value: int(str(value).replace(",", "")) if value else None,
        transaction_key=lambda info: str(info.get("TRANSACTION_NO", "")).replace("-", "").upper(),
        payment_summary=lambda slips: (
            sum(item["amount_num"] for item in slips),
            ["slip summary"],
        ),
    )
    payment_app = web.Application(client_max_size=8 * 1024 * 1024 + 64 * 1024)
    payment_app.router.add_options("/api/payment/slip", service.options)
    payment_app.router.add_post("/api/payment/slip", service.upload)
    payment_runner, payment_url = await _start_server(payment_app)

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    origin = "https://kyawmintun08.github.io"
    headers = {"Origin": origin, "Authorization": "Bearer valid-token"}
    data = {"userId": "123", "months": "1", "method": "kpay", "deviceId": "JACC-qa", "app": "web"}

    async with httpx.AsyncClient() as client:
        first = await client.post(
            payment_url + "/api/payment/slip",
            headers=headers,
            data=data,
            files={"slip": ("payment.png", io.BytesIO(png), "image/png")},
        )
        duplicate = await client.post(
            payment_url + "/api/payment/slip",
            headers=headers,
            data=data,
            files={"slip": ("payment.png", io.BytesIO(png), "image/png")},
        )
        bad_auth = await client.post(
            payment_url + "/api/payment/slip",
            headers={"Origin": origin, "Authorization": "Bearer bad-token"},
            data=data,
            files={"slip": ("payment.png", io.BytesIO(png), "image/png")},
        )
        bad_origin = await client.post(
            payment_url + "/api/payment/slip",
            headers={"Origin": "https://evil.example", "Authorization": "Bearer valid-token"},
            data=data,
            files={"slip": ("payment.png", io.BytesIO(png), "image/png")},
        )

    try:
        assert first.status_code == 202 and first.json()["status"] == "awaiting_admin"
        assert duplicate.status_code == 409 and duplicate.json()["code"] == "DUPLICATE_TRANSACTION"
        assert bad_auth.status_code == 401 and bad_auth.json()["code"] == "invalid_session"
        assert bad_origin.status_code == 403 and bad_origin.json()["code"] == "ORIGIN_NOT_ALLOWED"
        assert len(bot.messages) == 1 and bot.messages[0]["chat_id"] == 999
        assert len(bot.photos) == 1 and bot.photos[0]["bytes"] == png
        assert pending[123]["source"] == "website"
    finally:
        await payment_runner.cleanup()
        await sheet_runner.cleanup()


def test_website_payment_upload_flow():
    asyncio.run(_exercise_upload_flow())
