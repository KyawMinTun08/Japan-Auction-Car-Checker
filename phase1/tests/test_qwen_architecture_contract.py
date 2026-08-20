from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy_bot.py"
QWEN = ROOT / "qwen_text_service.py"
SQL = ROOT / "phase1" / "sql" / "006_ai_usage.sql"
INDEX = ROOT / "index.html"
JDM_CONFIG = ROOT / "jdm-config.js"


def test_gemini_payment_slip_flow_remains_unchanged_and_separate():
    source = LEGACY.read_text(encoding="utf-8")
    assert "async def gemini_read_slip(file_bytes: bytes)" in source
    assert "gemini_reader=gemini_read_slip" in source
    assert 'from qwen_text_service import build_qwen_text_http_service' in source
    assert 'web_app.router.add_post("/api/ai/query", qwen_http.query)' in source


def test_qwen_contract_is_server_side_and_feature_flagged():
    source = QWEN.read_text(encoding="utf-8")
    assert 'JACC_AI_ENABLED' in source
    assert 'JACC_AI_SPEC_ENABLED' in source
    assert 'GEMINI_API_KEY' in source
    assert '"x-goog-api-key": self.api_key' in source
    assert 'https://generativelanguage.googleapis.com/v1beta' in source
    assert 'gemini-2.5-flash' in source
    assert 'systemInstruction' in source
    assert 'responseMimeType' in source
    assert 'candidates' in source
    assert 'google_search' in source
    assert '_parse_vehicle_spec_text' in source
    assert 'JACC_AI_API_KEY' not in source
    assert 'CAR_TOPIC_ONLY' in source
    assert '_CHASSIS_QUERY_RE' in source
    assert '"hijet"' in source
    assert 'jacc_consume_ai_quota' in source
    assert 'JACC_AI_API_KEY' not in INDEX.read_text(encoding="utf-8")
    assert 'JACC_AI_API_KEY' not in JDM_CONFIG.read_text(encoding="utf-8")


def test_quota_migration_is_additive_and_does_not_change_members_columns():
    source = SQL.read_text(encoding="utf-8")
    assert "create table if not exists public.jacc_ai_usage_daily" in source
    assert "primary key (user_id, usage_date, feature)" in source
    assert "create or replace function public.jacc_consume_ai_quota" in source
    assert "alter table public.members" not in source.lower()
    assert "drop table public.members" not in source.lower()


def test_frontend_ai_search_uses_existing_authenticated_railway_contract():
    source = INDEX.read_text(encoding="utf-8")
    assert 'id="aiTextSearchCard"' in source
    assert 'Gemini · ကားအကြောင်းအရာအတွက်သာ' in source
    assert 'id="aiCarQueryInput"' in source
    assert 'id="homeAiQueryInput"' in source
    assert 'id="homeAiSearchResult"' in source
    assert 'askAiCarQuery' in source
    assert 'renderAiCarResults' in source
    assert "data.chassis||''" in source
    assert 'exactChassis' in source
    assert '<th>Chassis</th>' in source
    assert "Number(car.price).toLocaleString()" in source
    assert 'ai-price-results-mobile-fix' in source
    assert '#tab-dashboard .jacc-home-ai-result .table-wrap' in source
    assert 'grade_requested' in source
    assert 'vehicle_spec' in source
    assert 'ai-vehicle-spec-card' in source
    assert "base+'/api/ai/query'" in source
    assert "X-JACC-Device-ID" in source
    assert "X-JACC-App" in source
    assert "JACC_AI_API_KEY" not in source
