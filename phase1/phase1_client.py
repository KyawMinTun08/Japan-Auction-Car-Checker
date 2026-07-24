"""Async Supabase RPC client for JACC Phase 1.

Use this only from Railway/server code with SUPABASE_SERVICE_ROLE_KEY.
Do not import this into browser JavaScript or Flutter client code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class JaccPhase1Error(RuntimeError):
    """Raised when a Phase 1 RPC fails."""


@dataclass(frozen=True)
class OfferDispatch:
    offer_id: str
    request_id: str
    request_code: str
    broker_id: str
    broker_code: str
    broker_telegram_user_id: int | None
    service_type: str
    service_channel: str
    expires_at: str


class JaccPhase1Client:
    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not supabase_url or not service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

        self._base_url = supabase_url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout_seconds

    async def _rpc(self, function_name: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base_url}/rest/v1/rpc/{function_name}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, headers=self._headers, json=payload)

        if response.is_error:
            detail = response.text[:1_000]
            raise JaccPhase1Error(
                f"RPC {function_name} failed ({response.status_code}): {detail}"
            )

        if not response.content:
            return None
        return response.json()

    async def create_request_for_customer(
        self,
        *,
        customer_id: str,
        service_type: str,
        form_data: dict[str, Any],
    ) -> dict[str, Any]:
        data = await self._rpc(
            "jacc_create_request_for_customer",
            {
                "p_customer_id": customer_id,
                "p_service_type": service_type,
                "p_form_data": form_data,
            },
        )
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}

    async def dispatch_next_offer(self, request_id: str) -> OfferDispatch | None:
        data = await self._rpc(
            "jacc_dispatch_next_offer",
            {"p_request_id": request_id},
        )
        if not data:
            return None
        row = data[0] if isinstance(data, list) else data
        return OfferDispatch(**row)

    async def accept_offer(self, *, offer_id: str, broker_id: str) -> dict[str, Any]:
        data = await self._rpc(
            "jacc_accept_offer",
            {"p_offer_id": offer_id, "p_broker_id": broker_id},
        )
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}

    async def decline_offer(
        self,
        *,
        offer_id: str,
        broker_id: str,
        reason: str | None = None,
    ) -> str:
        request_id = await self._rpc(
            "jacc_decline_offer",
            {
                "p_offer_id": offer_id,
                "p_broker_id": broker_id,
                "p_reason": reason,
            },
        )
        if isinstance(request_id, str):
            return request_id
        raise JaccPhase1Error("Decline RPC did not return a request id")

    async def expire_pending_offers(self) -> list[str]:
        data = await self._rpc("jacc_expire_pending_offers", {})
        if not data:
            return []
        return [row["request_id"] for row in data]

    async def reassign_stale_requests(self) -> list[dict[str, Any]]:
        data = await self._rpc("jacc_reassign_stale_requests", {})
        return list(data or [])

    async def record_meaningful_update(
        self,
        *,
        request_id: str,
        actor_id: str,
        update_type: str,
        content: dict[str, Any] | None = None,
    ) -> None:
        await self._rpc(
            "jacc_record_meaningful_update",
            {
                "p_request_id": request_id,
                "p_actor_id": actor_id,
                "p_update_type": update_type,
                "p_content": content or {},
            },
        )
