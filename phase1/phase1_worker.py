"""Railway worker for JACC Phase 1.

Responsibilities:
- Expire 10-minute broker offers.
- Dispatch the next broker sequentially.
- Reassign requests after 48 hours without a meaningful update.
- Send Telegram fallback notifications to brokers during the pilot.

Run:
    python phase1_worker.py
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from phase1_client import JaccPhase1Client, OfferDispatch


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jacc-phase1-worker")

POLL_SECONDS = max(15, int(os.getenv("PHASE1_POLL_SECONDS", "30")))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [
    value.strip()
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
]


async def telegram_send(chat_id: int | str, text: str) -> bool:
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not set; notification skipped")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Telegram notification failed for chat_id=%s", chat_id)
        return False


async def notify_offer(offer: OfferDispatch) -> None:
    if offer.broker_telegram_user_id is None:
        logger.info(
            "Offer %s created for broker %s; dashboard push pending",
            offer.offer_id,
            offer.broker_code,
        )
        return

    service_label = "🏆 Auction Car" if offer.service_type == "auction" else "🔍 Outside Car"
    text = (
        "🔔 *JACC Broker Offer*\n\n"
        f"🆔 Request: `{offer.request_code}`\n"
        f"📌 Service: {service_label}\n"
        f"👷 Broker: `{offer.broker_code}`\n\n"
        "⏱ ဒီ Offer သည် ၁၀ မိနစ်အတွင်း သက်တမ်းကုန်မည်။\n"
        "Broker Dashboard သို့မဟုတ် Bot မှ Accept / Decline လုပ်ပါ။"
    )
    await telegram_send(offer.broker_telegram_user_id, text)


async def notify_admin(text: str) -> None:
    for admin_id in ADMIN_IDS:
        await telegram_send(admin_id, text)


async def dispatch_request(client: JaccPhase1Client, request_id: str) -> None:
    offer = await client.dispatch_next_offer(request_id)
    if offer is None:
        logger.info("No eligible broker currently available for request=%s", request_id)
        return
    logger.info(
        "Dispatched request=%s offer=%s broker=%s expires=%s",
        offer.request_code,
        offer.offer_id,
        offer.broker_code,
        offer.expires_at,
    )
    await notify_offer(offer)


async def run_cycle(client: JaccPhase1Client) -> None:
    expired_request_ids = await client.expire_pending_offers()
    for request_id in expired_request_ids:
        await dispatch_request(client, request_id)

    stale = await client.reassign_stale_requests()
    for row in stale:
        request_id = row["request_id"]
        request_code = row["request_code"]
        urgent = bool(row.get("urgent_auction"))
        await notify_admin(
            "🚨 *Broker Auto Reassign*\n\n"
            f"🆔 `{request_code}`\n"
            "အကြောင်းရင်း: ၄၈ နာရီအတွင်း Meaningful Update မရှိ\n"
            f"Urgent Auction: `{'YES' if urgent else 'NO'}`"
        )
        await dispatch_request(client, request_id)


async def main() -> None:
    client = JaccPhase1Client(
        supabase_url=SUPABASE_URL,
        service_role_key=SUPABASE_SERVICE_ROLE_KEY,
    )

    logger.info("JACC Phase 1 worker started; poll=%ss", POLL_SECONDS)
    while True:
        try:
            await run_cycle(client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker cycle failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
