"""JACC database-backed message delivery and recovery worker.

This worker is intentionally separate from ``phase1_worker.py`` so broker
assignment failures cannot stop message delivery retries.

Supported pilot delivery channels:
- telegram: sends with BOT_TOKEN
- app / broker_dashboard / admin_dashboard: posts to the optional internal
  delivery webhook configured with JACC_INTERNAL_DELIVERY_WEBHOOK

Run:
    python recovery_worker.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass
from typing import Any

import httpx


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jacc-recovery-worker")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
INTERNAL_WEBHOOK = os.getenv("JACC_INTERNAL_DELIVERY_WEBHOOK", "")
INTERNAL_WEBHOOK_SECRET = os.getenv("JACC_INTERNAL_DELIVERY_SECRET", "")
POLL_SECONDS = max(5, int(os.getenv("RECOVERY_POLL_SECONDS", "15")))
BATCH_SIZE = max(1, min(100, int(os.getenv("RECOVERY_BATCH_SIZE", "20"))))
CONCURRENCY = max(1, min(20, int(os.getenv("RECOVERY_CONCURRENCY", "5"))))
WORKER_ID = os.getenv("RECOVERY_WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")
ADMIN_IDS = [
    value.strip()
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
]


class DeliveryError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response[:1_000]


@dataclass(frozen=True)
class DeliveryResult:
    provider_message_id: str | None = None
    provider_status: int | None = None
    response_excerpt: str = ""


class RecoveryClient:
    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self.headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

    async def rpc(self, function_name: str, payload: dict[str, Any]) -> Any:
        url = f"{SUPABASE_URL}/rest/v1/rpc/{function_name}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=self.headers, json=payload)
        if response.is_error:
            raise DeliveryError(
                f"RPC {function_name} failed",
                status_code=response.status_code,
                response=response.text,
            )
        return response.json() if response.content else None

    async def recover_stuck(self) -> list[dict[str, Any]]:
        data = await self.rpc("jacc_recover_stuck_outbox", {})
        return list(data or [])

    async def claim(self) -> list[dict[str, Any]]:
        data = await self.rpc(
            "jacc_claim_outbox_messages",
            {"p_worker_id": WORKER_ID, "p_limit": BATCH_SIZE},
        )
        return list(data or [])

    async def mark_sent(self, item_id: str, result: DeliveryResult) -> None:
        await self.rpc(
            "jacc_mark_outbox_sent",
            {
                "p_outbox_id": item_id,
                "p_worker_id": WORKER_ID,
                "p_provider_message_id": result.provider_message_id,
                "p_provider_status": result.provider_status,
                "p_response_excerpt": result.response_excerpt,
            },
        )

    async def mark_failed(self, item_id: str, error: DeliveryError) -> str:
        data = await self.rpc(
            "jacc_mark_outbox_failed",
            {
                "p_outbox_id": item_id,
                "p_worker_id": WORKER_ID,
                "p_error_message": str(error),
                "p_provider_status": error.status_code,
                "p_response_excerpt": error.response,
            },
        )
        if isinstance(data, str):
            return data
        if isinstance(data, list) and data:
            return str(data[0])
        return "retrying"


async def deliver_telegram(payload: dict[str, Any]) -> DeliveryResult:
    if not BOT_TOKEN:
        raise DeliveryError("BOT_TOKEN is not configured")

    chat_id = payload.get("chat_id")
    text = payload.get("text")
    if chat_id is None or not isinstance(text, str) or not text.strip():
        raise DeliveryError("Telegram payload requires chat_id and non-empty text")

    request_payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": text,
    }
    if payload.get("parse_mode"):
        request_payload["parse_mode"] = payload["parse_mode"]
    if payload.get("reply_markup"):
        request_payload["reply_markup"] = payload["reply_markup"]

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=request_payload)

    if response.is_error:
        raise DeliveryError(
            "Telegram delivery failed",
            status_code=response.status_code,
            response=response.text,
        )

    body = response.json()
    if not body.get("ok"):
        raise DeliveryError("Telegram returned ok=false", response=response.text)

    message_id = body.get("result", {}).get("message_id")
    return DeliveryResult(
        provider_message_id=str(message_id) if message_id is not None else None,
        provider_status=response.status_code,
        response_excerpt=response.text[:1_000],
    )


async def deliver_internal(channel: str, payload: dict[str, Any]) -> DeliveryResult:
    if not INTERNAL_WEBHOOK:
        raise DeliveryError(f"Internal delivery webhook is not configured for {channel}")

    headers = {"Content-Type": "application/json"}
    if INTERNAL_WEBHOOK_SECRET:
        headers["X-JACC-Delivery-Secret"] = INTERNAL_WEBHOOK_SECRET

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            INTERNAL_WEBHOOK,
            headers=headers,
            json={"channel": channel, "payload": payload},
        )

    if response.is_error:
        raise DeliveryError(
            f"Internal {channel} delivery failed",
            status_code=response.status_code,
            response=response.text,
        )

    provider_id = response.headers.get("X-JACC-Message-ID")
    return DeliveryResult(
        provider_message_id=provider_id,
        provider_status=response.status_code,
        response_excerpt=response.text[:1_000],
    )


async def deliver(item: dict[str, Any]) -> DeliveryResult:
    channel = str(item.get("channel", ""))
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise DeliveryError("Outbox payload must be a JSON object")

    if channel == "telegram":
        return await deliver_telegram(payload)
    if channel in {"app", "broker_dashboard", "admin_dashboard"}:
        return await deliver_internal(channel, payload)
    raise DeliveryError(f"Unsupported delivery channel: {channel}")


async def notify_dead_letter(item: dict[str, Any], error: DeliveryError) -> None:
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    text = (
        "🚨 JACC Message Dead Letter\n\n"
        f"Outbox: {item.get('id')}\n"
        f"Channel: {item.get('channel')}\n"
        f"Request: {item.get('request_id') or '-'}\n"
        f"Error: {str(error)[:500]}"
    )
    await asyncio.gather(
        *(deliver_telegram({"chat_id": admin_id, "text": text}) for admin_id in ADMIN_IDS),
        return_exceptions=True,
    )


async def process_item(client: RecoveryClient, semaphore: asyncio.Semaphore, item: dict[str, Any]) -> None:
    async with semaphore:
        item_id = str(item["id"])
        try:
            result = await deliver(item)
            await client.mark_sent(item_id, result)
            logger.info("Delivered outbox=%s channel=%s", item_id, item.get("channel"))
        except DeliveryError as exc:
            status = await client.mark_failed(item_id, exc)
            logger.warning("Delivery failed outbox=%s next_status=%s error=%s", item_id, status, exc)
            if status == "dead_letter":
                await notify_dead_letter(item, exc)
        except Exception as exc:  # defensive conversion so the item is never left locked
            logger.exception("Unexpected delivery error outbox=%s", item_id)
            wrapped = DeliveryError(f"Unexpected delivery error: {exc}")
            status = await client.mark_failed(item_id, wrapped)
            if status == "dead_letter":
                await notify_dead_letter(item, wrapped)


async def run_cycle(client: RecoveryClient, cycle_number: int) -> None:
    if cycle_number % 20 == 0:
        recovered = await client.recover_stuck()
        if recovered:
            logger.warning("Recovered %d stuck outbox item(s)", len(recovered))

    items = await client.claim()
    if not items:
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(*(process_item(client, semaphore, item) for item in items))


async def main() -> None:
    client = RecoveryClient()
    cycle_number = 0
    logger.info(
        "JACC recovery worker started worker_id=%s poll=%ss batch=%s concurrency=%s",
        WORKER_ID,
        POLL_SECONDS,
        BATCH_SIZE,
        CONCURRENCY,
    )

    while True:
        cycle_number += 1
        try:
            await run_cycle(client, cycle_number)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Recovery worker cycle failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
