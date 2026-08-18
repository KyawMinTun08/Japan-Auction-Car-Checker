from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from aiohttp import web

logger = logging.getLogger(__name__)

_INVISIBLE_RE = re.compile(r"[\u0000-\u001f\u007f\u200b-\u200d\u2060\ufeff]")
_DASH_RE = re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]")
_PREFIX_RE = re.compile(r"^([A-Z0-9]{2,20})(?:-|$)")


class JdmLookupError(RuntimeError):
    """Expected, user-safe JDM lookup failure."""


class JdmGradeService:
    """Local JDM model/chassis lookup with an adapter seam for future providers."""

    def __init__(self, *, supabase_url: str, service_role_key: str, sheet_webhook: str) -> None:
        self.base_url = supabase_url.rstrip("/")
        self.sheet_webhook = sheet_webhook.strip()
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self.timeout = float(os.environ.get("JDM_LOOKUP_TIMEOUT", "8"))
        # Gemini can take longer than the database lookup; keep its timeout separate.
        self.ai_timeout = float(os.environ.get("JDM_AI_TIMEOUT", "30"))
        self.cache_days = int(os.environ.get("JDM_CACHE_DAYS", "30"))
        self.hash_salt = os.environ.get("JDM_HASH_SALT", "jacc-jdm-cache-v1")
        self.provider_key = "local_jacc"
        # AI explanation is optional and server-side only; the key is never sent to the browser.
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()

    @staticmethod
    def normalize_chassis(raw: str) -> str:
        value = _INVISIBLE_RE.sub("", str(raw or ""))
        value = _DASH_RE.sub("-", value).strip().upper()
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"[^A-Z0-9-]", "", value)
        value = re.sub(r"-+", "-", value).strip("-")
        if not value or len(value) < 3 or len(value) > 40:
            raise JdmLookupError("INVALID_CHASSIS")
        return value

    def chassis_prefix(self, normalized: str) -> str:
        match = _PREFIX_RE.match(normalized)
        if match:
            return match.group(1)
        # Some imported records arrive without a dash. Use the full value only
        # as a last-resort lookup key; never infer a model from a short prefix.
        return normalized

    def chassis_hash(self, normalized: str) -> str:
        return hashlib.sha256(
            f"{self.hash_salt}:{normalized}".encode("utf-8")
        ).hexdigest()

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.base_url or not self.headers.get("apikey"):
            raise JdmLookupError("JDM_DATABASE_NOT_CONFIGURED")
        url = f"{self.base_url}/rest/v1/{table}"
        request_headers = dict(self.headers)
        if method.upper() == "POST" and table == "jacc_lookup_cache":
            request_headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=payload,
            )
        if response.is_error:
            logger.error("JDM database request failed: table=%s status=%s", table, response.status_code)
            raise JdmLookupError("JDM_DATABASE_UNAVAILABLE")
        data = response.json()
        return data if isinstance(data, list) else []

    async def _read_cache(self, chassis_hash: str) -> dict[str, Any] | None:
        rows = await self._request(
            "GET",
            "jacc_lookup_cache",
            params={
                "chassis_number_hash": f"eq.{chassis_hash}",
                "lookup_kind": "eq.model_info",
                "provider_key": f"eq.{self.provider_key}",
                "select": "status,response_payload,checked_at,expires_at",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        expires_at = row.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if expiry < datetime.now(timezone.utc):
                    return None
            except ValueError:
                return None
        return row

    async def _write_cache(
        self,
        *,
        chassis_hash: str,
        normalized_chassis: str,
        status: str,
        response_payload: dict[str, Any],
        error_code: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = now.replace(microsecond=0)
        # Keep cache lifetime deterministic without adding a dependency.
        from datetime import timedelta

        expires = expires + timedelta(days=self.cache_days)
        payload = {
            "chassis_number_hash": chassis_hash,
            "normalized_chassis": normalized_chassis,
            "lookup_kind": "model_info",
            "provider_key": self.provider_key,
            "status": status,
            "response_payload": response_payload,
            "error_code": error_code,
            "checked_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "updated_at": now.isoformat(),
        }
        await self._request(
            "POST",
            "jacc_lookup_cache",
            params={"on_conflict": "chassis_number_hash,lookup_kind,provider_key"},
            payload=payload,
        )

    async def _lookup_local(self, prefix: str) -> dict[str, Any]:
        code_rows = await self._request(
            "GET",
            "jacc_chassis_codes",
            params={
                "chassis_prefix_normalized": f"eq.{prefix}",
                "is_active": "eq.true",
                "select": "id,model_id,chassis_prefix_normalized,engine_code,transmission,body_type,production_from_year,production_to_year,confidence,verified,source_id",
                "limit": "20",
            },
        )
        if not code_rows:
            return {"status": "not_found", "matches": []}

        model_ids = sorted({str(row["model_id"]) for row in code_rows if row.get("model_id")})
        model_rows: list[dict[str, Any]] = []
        if model_ids:
            model_rows = await self._request(
                "GET",
                "jacc_vehicle_models",
                params={
                    "id": "in.(" + ",".join(model_ids) + ")",
                    "select": "id,make_id,canonical_name,body_type,vehicle_category",
                    "limit": "50",
                },
            )
        make_ids = sorted({str(row["make_id"]) for row in model_rows if row.get("make_id")})
        grade_rows: list[dict[str, Any]] = []
        if model_ids:
            grade_rows = await self._request(
                "GET",
                "jacc_factory_grades",
                params={
                    "model_id": "in.(" + ",".join(model_ids) + ")",
                    "is_active": "eq.true",
                    "select": "id,chassis_code_id,model_id,grade_code,grade_name,trim_level,equipment,production_from_year,production_to_year,confidence,verified,source_id",
                    "limit": "100",
                },
            )
        make_rows: list[dict[str, Any]] = []
        if make_ids:
            make_rows = await self._request(
                "GET",
                "jacc_vehicle_makes",
                params={
                    "id": "in.(" + ",".join(make_ids) + ")",
                    "select": "id,make_key,display_name",
                    "limit": "50",
                },
            )
        model_by_id = {str(row["id"]): row for row in model_rows}
        make_by_id = {str(row["id"]): row for row in make_rows}
        matches: list[dict[str, Any]] = []
        for code in code_rows:
            model = model_by_id.get(str(code.get("model_id")), {})
            make = make_by_id.get(str(model.get("make_id")), {})
            code_id = str(code.get("id") or "")
            model_id = str(code.get("model_id") or "")
            factory_grades = [
                {
                    "grade_code": grade.get("grade_code"),
                    "grade_name": grade.get("grade_name"),
                    "trim_level": grade.get("trim_level"),
                    "equipment": grade.get("equipment") or {},
                    "production_from_year": grade.get("production_from_year"),
                    "production_to_year": grade.get("production_to_year"),
                    "confidence": grade.get("confidence"),
                    "verified": bool(grade.get("verified")),
                    "source_id": grade.get("source_id"),
                }
                for grade in grade_rows
                if str(grade.get("model_id") or "") == model_id
                and (not grade.get("chassis_code_id") or str(grade.get("chassis_code_id")) == code_id)
            ]
            matches.append(
                {
                    "chassis_prefix": code.get("chassis_prefix_normalized"),
                    "make": make.get("display_name"),
                    "model": model.get("canonical_name"),
                    "body_type": code.get("body_type") or model.get("body_type"),
                    "vehicle_category": model.get("vehicle_category"),
                    "engine_code": code.get("engine_code"),
                    "transmission": code.get("transmission"),
                    "production_from_year": code.get("production_from_year"),
                    "production_to_year": code.get("production_to_year"),
                    "confidence": code.get("confidence"),
                    "verified": bool(code.get("verified")),
                    "factory_grades": factory_grades,
                }
            )
        return {"status": "ok", "matches": matches}

    async def verify_web_session(
        self,
        token: str,
        user_id: str = "",
        device_id: str = "",
        app_name: str = "web",
    ) -> dict[str, Any]:
        if not self.sheet_webhook or not token:
            return {"status": "error", "message": "web_access_required"}
        payload: dict[str, Any] = {"action": "verifyToken", "token": token}
        if user_id:
            payload["userId"] = str(user_id).strip()
        if device_id:
            payload["deviceId"] = str(device_id).strip()[:160]
        if app_name:
            payload["app"] = str(app_name).strip().lower()[:20]
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.post(
                    self.sheet_webhook,
                    headers={"Content-Type": "text/plain"},
                    json=payload,
                )
            if response.is_error:
                return {"status": "error", "message": "session_unavailable"}
            payload = response.json()
            return payload if isinstance(payload, dict) else {"status": "error", "message": "invalid_session_response"}
        except Exception:
            logger.exception("JDM web session verification failed")
            return {"status": "error", "message": "session_unavailable"}

    def _verified_fallback_explanation(self, safe_payload: dict[str, Any], reason: str) -> dict[str, Any]:
        """Return a transparent, non-generative explanation from verified lookup facts only."""
        labels = (
            ("make", "Make"),
            ("model", "Model"),
            ("body_type", "Body type"),
            ("vehicle_category", "Vehicle category"),
            ("engine_code", "Engine code"),
            ("transmission", "Transmission"),
            ("production_from_year", "Production from"),
            ("production_to_year", "Production to"),
        )
        lines = [
            "Gemini AI မရရှိသေးသောကြောင့် verified lookup facts ကို template ဖြင့်သာ ပြထားပါသည်။",
            "Known facts",
            f"- Chassis: {safe_payload.get('chassis') or 'မရှိသေးပါ'}",
        ]
        for match in safe_payload.get("matches", [])[:5]:
            facts = []
            for key, label in labels:
                value = match.get(key)
                if value not in (None, "", [], {}):
                    facts.append(f"{label}: {value}")
            if facts:
                lines.append("- " + ", ".join(facts))
        lines.extend(
            [
                "Uncertain or missing",
                "- Auction grade, mileage, condition, inspection, accident history, ownership, and final landed cost data မရှိသေးပါ။",
                "Before-bid checks",
                "- Auction sheet, inspection report, source/date evidence နှင့် broker/admin review ကို bid မတင်မီ အတည်ပြုပါ။",
            ]
        )
        return {
            "status": "ok",
            "chassis": safe_payload.get("chassis"),
            "text": "\n".join(lines),
            "provider": "verified-template",
            "notice": reason,
            "source": safe_payload,
        }

    async def explain_burmese(self, raw_chassis: str, lookup_payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = {
            "chassis": lookup_payload.get("chassis"),
            "chassis_prefix": lookup_payload.get("chassis_prefix"),
            "provider": lookup_payload.get("provider"),
            "checked_at": lookup_payload.get("checked_at"),
            "status": lookup_payload.get("status"),
            "matches": lookup_payload.get("matches", [])[:5],
        }
        if not self.gemini_api_key:
            return self._verified_fallback_explanation(safe_payload, "AI_EXPLANATION_NOT_CONFIGURED")
        prompt = (
            "You are the JACC vehicle explanation assistant. Explain the supplied verified lookup data in easy Burmese. "
            "Use ONLY the JSON facts. Never invent auction grade, accident history, mileage, price, ownership, or safety claims. "
            "If a fact is missing, say 'မရှိသေးပါ'. Do not say buy or do not buy. Return exactly three short sections: "
            "Known facts, Uncertain or missing, Before-bid checks. Keep technical model/chassis names in English.\n\n"
            + json.dumps(safe_payload, ensure_ascii=False)
        )
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + self.gemini_model + ":generateContent?key=" + self.gemini_api_key
        try:
            async with httpx.AsyncClient(timeout=self.ai_timeout) as client:
                response = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            if response.is_error:
                logger.warning("Gemini explanation unavailable: status=%s; using verified fallback", response.status_code)
                return self._verified_fallback_explanation(safe_payload, "AI_PROVIDER_UNAVAILABLE")
            data = response.json()
            parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = "\n".join(str(part.get("text") or "") for part in parts).strip()
            if not text:
                return self._verified_fallback_explanation(safe_payload, "AI_EMPTY_RESPONSE")
            return {"status": "ok", "chassis": safe_payload["chassis"], "text": text, "provider": "gemini", "source": safe_payload}
        except Exception:
            logger.exception("Gemini Burmese explanation request failed; using verified fallback")
            return self._verified_fallback_explanation(safe_payload, "AI_PROVIDER_UNAVAILABLE")

    async def lookup(self, raw_chassis: str) -> dict[str, Any]:
        normalized = self.normalize_chassis(raw_chassis)
        prefix = self.chassis_prefix(normalized)
        hashed = self.chassis_hash(normalized)
        cached = await self._read_cache(hashed)
        if cached:
            payload = dict(cached.get("response_payload") or {})
            payload["cached"] = True
            payload["checked_at"] = cached.get("checked_at")
            return payload

        result = await self._lookup_local(prefix)
        result.update(
            {
                "chassis": normalized,
                "chassis_prefix": prefix,
                "provider": self.provider_key,
                "cached": False,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await self._write_cache(
            chassis_hash=hashed,
            normalized_chassis=normalized,
            status="hit" if result.get("status") == "ok" else "not_found",
            response_payload=result,
        )
        return result


class JdmLookupHttp:
    """Small aiohttp adapter mounted beside the existing Railway health server."""

    def __init__(self, service: JdmGradeService) -> None:
        self.service = service
        configured = os.environ.get(
            "JDM_CORS_ORIGINS",
            "https://kyawmintun08.github.io,https://japan-auction-car-checker.pages.dev",
        )
        self.allowed_origins = {value.strip() for value in configured.split(",") if value.strip()}

    def _headers(self, request: web.Request) -> dict[str, str]:
        origin = request.headers.get("Origin", "")
        headers = {
            "Cache-Control": "no-store",
            "Vary": "Origin",
        }
        if origin in self.allowed_origins:
            headers.update(
                {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-JACC-User-ID, X-JACC-Device-ID, X-JACC-App",
                }
            )
        return headers

    async def options(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers=self._headers(request))

    async def explain(self, request: web.Request) -> web.Response:
        headers = self._headers(request)
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        user_id = request.headers.get("X-JACC-User-ID", "").strip()
        device_id = request.headers.get("X-JACC-Device-ID", "").strip()[:160]
        app_name = request.headers.get("X-JACC-App", "web").strip().lower()[:20]
        session = await self.service.verify_web_session(token, user_id, device_id, app_name)
        if session.get("status") != "ok":
            return web.json_response({"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")}, status=401, headers=headers)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"status": "error", "code": "INVALID_JSON"}, status=400, headers=headers)
        raw = str(body.get("chassis", "")).strip()
        if not raw:
            return web.json_response({"status": "error", "code": "CHASSIS_REQUIRED"}, status=400, headers=headers)
        try:
            lookup_payload = await self.service.lookup(raw)
            return web.json_response(await self.service.explain_burmese(raw, lookup_payload), headers=headers)
        except JdmLookupError as exc:
            code = str(exc)
            status = 503 if code in {"JDM_DATABASE_UNAVAILABLE", "AI_PROVIDER_UNAVAILABLE", "AI_EXPLANATION_NOT_CONFIGURED"} else 400
            return web.json_response({"status": "error", "code": code}, status=status, headers=headers)
        except Exception:
            logger.exception("Burmese explanation failed")
            return web.json_response({"status": "error", "code": "EXPLANATION_FAILED"}, status=500, headers=headers)

    async def lookup(self, request: web.Request) -> web.Response:
        headers = self._headers(request)
        raw = request.query.get("chassis", "")
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        user_id = request.headers.get("X-JACC-User-ID", "").strip()
        device_id = request.headers.get("X-JACC-Device-ID", "").strip()[:160]
        app_name = request.headers.get("X-JACC-App", "web").strip().lower()[:20]
        session = await self.service.verify_web_session(token, user_id, device_id, app_name)
        if session.get("status") != "ok":
            return web.json_response(
                {"status": "error", "code": session.get("message", "WEB_ACCESS_REQUIRED")},
                status=401,
                headers=headers,
            )
        if not raw:
            return web.json_response(
                {"status": "error", "code": "CHASSIS_REQUIRED"},
                status=400,
                headers=headers,
            )
        try:
            payload = await self.service.lookup(raw)
        except JdmLookupError as exc:
            code = str(exc)
            status = 503 if code == "JDM_DATABASE_UNAVAILABLE" else 400
            return web.json_response(
                {"status": "error", "code": code},
                status=status,
                headers=headers,
            )
        except Exception:
            logger.exception("JDM lookup failed")
            return web.json_response(
                {"status": "error", "code": "LOOKUP_FAILED"},
                status=500,
                headers=headers,
            )
        return web.json_response(payload, headers=headers)


def build_jdm_http_service() -> JdmLookupHttp | None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    sheet_webhook = os.environ.get("SHEET_WEBHOOK", "").strip()
    if not url or not key or not sheet_webhook:
        logger.warning("JDM lookup disabled: Supabase or SHEET_WEBHOOK credentials missing")
        return None
    return JdmLookupHttp(
        JdmGradeService(
            supabase_url=url,
            service_role_key=key,
            sheet_webhook=sheet_webhook,
        )
    )
