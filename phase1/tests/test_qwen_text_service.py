import asyncio
import os
from contextlib import asynccontextmanager

import pytest
from aiohttp import web

from qwen_text_service import QwenTextError, QwenTextHttp, QwenTextService


@asynccontextmanager
async def _server(app: web.Application):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def _service(**overrides):
    env = {
        "JACC_AI_ENABLED": "true",
        "JACC_AI_PROVIDER": "qwencloud",
        "JACC_AI_MODEL": "qwen3.7-flash",
        "JACC_AI_API_KEY": "qwen-test-key",
        "JACC_AI_DAILY_LIMIT": "10",
        "JACC_AI_TOPIC_ONLY": "true",
    }
    old = {key: os.environ.get(key) for key in env}
    os.environ.update({**env, **overrides})
    service = QwenTextService(
        supabase_url="http://127.0.0.1:1",
        service_role_key="db-test-key",
        sheet_webhook="http://127.0.0.1:1/verify",
    )
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return service


def test_topic_gate_and_normalization():
    assert QwenTextService.normalize_query("  Toyota   Crown\u200b 2020 ") == "Toyota Crown 2020"
    assert QwenTextService.is_car_topic("Toyota Crown under 1,500,000")
    assert QwenTextService.is_car_topic("Crown 2012 ဈေးနှုန်းလေးတွေပြပါ")
    assert QwenTextService.is_car_topic("Corolla 2010 price ရှာပါ")
    assert QwenTextService.is_grade_topic("Toyota Crown auction grade ဘယ်လောက်လဲ")
    assert not QwenTextService.is_grade_topic("ဒီနေ့မိုးရွာမလား")
    assert not QwenTextService.is_car_topic("price and model")
    assert not QwenTextService.is_car_topic("Write a poem about rain")


def test_grade_plan_is_validated_without_inventing_grade_values():
    plan = QwenTextService._validate_plan(
        {
            "intent": "grade_info",
            "grade_requested": True,
            "chassis": "GRS210-6007724",
            "filters": {"model": "Crown", "year_min": 2012},
        }
    )
    assert plan["intent"] == "grade_info"
    assert plan["grade_requested"] is True
    assert plan["chassis"] == "GRS210-6007724"
    assert plan["filters"]["model"] == "Crown"
    assert "grade_code" not in plan


def test_filters_reject_unknown_or_invalid_fields():
    with pytest.raises(QwenTextError) as unknown:
        QwenTextService._validate_filters({"sql": "drop table"})
    assert unknown.value.code == "AI_INVALID_FILTERS"

    with pytest.raises(QwenTextError) as invalid:
        QwenTextService._validate_filters({"year_min": "not-a-year"})
    assert invalid.value.code == "AI_INVALID_FILTERS"


def test_disabled_mode_does_not_consume_quota():
    service = _service(JACC_AI_ENABLED="false")
    called = False

    async def consume(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"accepted": True}

    service.consume_quota = consume
    with pytest.raises(QwenTextError) as error:
        asyncio.run(service.query(user_id="123", raw_query="Toyota Crown 2020"))
    assert error.value.code == "AI_DISABLED"
    assert called is False


def test_qwen_service_and_http_route_use_verified_session_and_atomic_quota():
    async def exercise():
        app = web.Application()
        state = {"quota_calls": 0}

        async def verify(request):
            payload = await request.json()
            if payload.get("token") != "valid-token":
                return web.json_response({"status": "error", "message": "invalid_token"})
            return web.json_response({"status": "ok", "userId": "123", "package": "WEB"})

        async def quota(request):
            state["quota_calls"] += 1
            payload = await request.json()
            assert payload["p_user_id"] == "123"
            return web.json_response(
                {
                    "accepted": True,
                    "ask_count": state["quota_calls"],
                    "remaining": 10 - state["quota_calls"],
                    "usage_date": payload["p_usage_date"],
                    "feature": "car_text",
                }
            )

        async def qwen(request):
            assert request.headers["Authorization"] == "Bearer qwen-test-key"
            payload = await request.json()
            assert payload["model"] == "qwen3.7-flash"
            return web.json_response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"make":"Toyota","model":"Crown","year_min":2020}'
                            }
                        }
                    ]
                }
            )

        app.router.add_post("/verify", verify)
        app.router.add_post("/rest/v1/rpc/jacc_consume_ai_quota", quota)
        app.router.add_post("/compatible-mode/v1/chat/completions", qwen)
        service = _service()
        http_service = QwenTextHttp(service)
        app.router.add_options("/api/ai/query", http_service.options)
        app.router.add_post("/api/ai/query", http_service.query)

        async with _server(app) as base:
            service.sheet_webhook = f"{base}/verify"
            service.supabase_url = base
            service.base_url = f"{base}/compatible-mode/v1"

            from aiohttp import ClientSession

            async with ClientSession() as client:
                response = await client.post(
                    f"{base}/api/ai/query",
                    headers={
                        "Origin": "https://kyawmintun08.github.io",
                        "Authorization": "Bearer valid-token",
                        "X-JACC-User-ID": "123",
                        "X-JACC-Device-ID": "device-a",
                        "X-JACC-App": "web",
                    },
                    json={"query": "Toyota Crown 2020"},
                )
                data = await response.json()
                assert response.status == 200
                assert data["status"] == "ok"
                assert data["filters"]["model"] == "Crown"
                assert data["remaining"] == 9
                assert state["quota_calls"] == 1

                bad = await client.post(
                    f"{base}/api/ai/query",
                    headers={
                        "Origin": "https://kyawmintun08.github.io",
                        "Authorization": "Bearer invalid-token",
                        "X-JACC-User-ID": "123",
                        "X-JACC-Device-ID": "device-a",
                        "X-JACC-App": "web",
                    },
                    json={"query": "Toyota Crown 2020"},
                )
                bad_data = await bad.json()
                assert bad.status == 401
                assert bad_data["code"] == "invalid_session"

                non_car = await client.post(
                    f"{base}/api/ai/query",
                    headers={
                        "Origin": "https://kyawmintun08.github.io",
                        "Authorization": "Bearer valid-token",
                        "X-JACC-User-ID": "123",
                        "X-JACC-Device-ID": "device-a",
                        "X-JACC-App": "web",
                    },
                    json={"query": "Write a poem about rain"},
                )
                non_car_data = await non_car.json()
                assert non_car.status == 400
                assert non_car_data["code"] == "CAR_TOPIC_ONLY"
                assert state["quota_calls"] == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, "AI_PROVIDER_BAD_REQUEST"),
        (401, "AI_PROVIDER_AUTH"),
        (403, "AI_PROVIDER_FORBIDDEN"),
        (404, "AI_PROVIDER_NOT_FOUND"),
        (408, "AI_PROVIDER_TIMEOUT"),
        (409, "AI_PROVIDER_CONFLICT"),
        (429, "AI_PROVIDER_QUOTA"),
        (500, "AI_PROVIDER_UNAVAILABLE"),
    ],
)
def test_provider_http_status_maps_to_safe_error_code(status_code, expected_code):
    async def exercise():
        app = web.Application()

        async def qwen(_request):
            return web.json_response(
                {"error": {"message": "provider detail must not reach the client"}},
                status=status_code,
            )

        app.router.add_post("/compatible-mode/v1/chat/completions", qwen)
        service = _service()
        async with _server(app) as base:
            service.base_url = f"{base}/compatible-mode/v1"
            with pytest.raises(QwenTextError) as error:
                await service._call_provider("Toyota Crown 2020")
            assert error.value.code == expected_code

    asyncio.run(exercise())
