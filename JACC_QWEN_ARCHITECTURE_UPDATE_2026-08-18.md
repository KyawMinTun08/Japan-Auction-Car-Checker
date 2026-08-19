# JACC Qwen3.7-Flash Architecture Update

**Date:** 18 August 2026

## 1. Goal and non-negotiable compatibility rules

JACC will add Qwen3.7-Flash for **text-only car search and Burmese result explanation** while keeping the current Gemini 2.5 Flash flow for payment-slip/image reading unchanged. The existing Telegram membership flow, Premium web authorization, device-binding headers, Google Apps Script session verification, payment-slip OCR, Members columns A–I, and current JDM lookup route must remain backward-compatible.

The Qwen key will never be sent to browser JavaScript, Flutter WebView code, Google Apps Script responses, Telegram messages, GitHub files, or logs. The browser will call the existing authenticated Railway domain; only Railway will call QwenCloud.

## 2. Current system audit

The current Railway service is an `aiohttp` server mounted inside `legacy_bot.py`. It already exposes `/api/jdm/lookup`, `/api/jdm/explain`, and website payment endpoints. `jdm_lookup_service.py` verifies the Premium web session through `SHEET_WEBHOOK`, carries `X-JACC-User-ID`, `X-JACC-Device-ID`, and `X-JACC-App`, reads verified vehicle data from Supabase, and optionally calls Gemini for a Burmese explanation.

The payment-slip path is separate. `legacy_bot.py` calls `gemini_read_slip(file_bytes)` for payment-slip image extraction, and `website_payment_upload.py` receives the same Gemini reader callback. That path must not be replaced by Qwen because Qwen3.7-Flash is being added as a text-only provider for the new feature.

The frontend already has a public Railway base URL in `jdm-config.js` and uses the existing session token plus device headers for `/api/jdm/*`. The new text route should reuse this base URL and authorization pattern rather than create a second public backend URL.

## 3. Viable architecture options

| Approach | Tradeoffs | Cost | Setup complexity |
|---|---|---:|---|
| **A. Add a feature-flagged Qwen route to the existing Railway service** | Reuses the current Premium session verification, device context, CORS policy, Supabase connection, logging, and deployment. Gemini slip reading remains untouched. The new text route shares the bot service lifecycle, so a bad change could affect the existing process unless imports and failures are isolated. | Lowest incremental cost; no second service. | Medium. Add a small provider adapter, a new route, a persistent quota table/RPC, UI, and tests. |
| **B. Create a separate Railway AI service** | Strong isolation and independent scaling/provider fallback. The existing bot/payment service is less exposed to Qwen changes. It introduces a second public service, cross-service authentication, CORS, duplicated session verification or signed internal tokens, more secrets, more logs, and another deployment to maintain. | Higher operational cost and more moving parts; still incurs Qwen token cost. | High. Requires internal authentication, service URL management, monitoring, and duplicate deployment controls. |

For the current scale of approximately 20 web users and a limit of 10 text questions per user per day, **Approach A is the safer first release**. It is smaller, easier to test, and does not need a second production service. Approach B remains a future isolation option if AI traffic grows or provider failures must be independently contained.

## 4. Target request flow

```text
Website / PWA / Flutter text query
        |
        | Existing Premium token + user/device/app headers
        v
Railway /api/ai/query
        |
        | 1. CORS origin check
        | 2. verify Apps Script session and device context
        | 3. confirm Premium web access
        | 4. normalize and car-topic gate
        | 5. atomically consume one daily quota slot
        | 6. call Qwen3.7-Flash with strict text-only JSON output
        v
Structured car filters
        |
        | deterministic query against existing JACC/Supabase data
        v
Verified JACC car rows
        |
        | optional short Qwen Burmese summary using only verified rows
        v
Website response
```

The existing image/payment flow remains separate:

```text
Payment slip image → existing Gemini 2.5 Flash gemini_read_slip() → payment validation
```

The new Qwen path must never receive payment-slip images, payment fields, Members tokens, passwords, device hash secrets, or full AuthSessions data.

## 5. New endpoint contract

The first text endpoint should be `POST /api/ai/query` with the same authenticated CORS behavior as the existing JDM routes.

Request body:

```json
{
  "query": "Toyota Crown 2020 အောက်ဈေးနဲ့ Klang9 မှာရှာပါ"
}
```

Allowed request headers are the existing `Authorization`, `X-JACC-User-ID`, `X-JACC-Device-ID`, and `X-JACC-App`. The server must derive the effective user identity from the verified Apps Script session response and use the header only as a cross-check, not as an unauthenticated quota key.

The first model call should request a strict filter object, not free-form database instructions:

```json
{
  "make": "Toyota",
  "model": "Crown",
  "year_min": 2020,
  "year_max": null,
  "price_max": null,
  "location": "Klang9",
  "chassis_prefix": null,
  "body_type": null
}
```

The backend validates the object against a whitelist, performs the actual Supabase/JACC query itself, limits returned rows, and generates a short explanation from verified rows only. Qwen must not write SQL, browse arbitrary websites, invent auction grade/mileage/accident history, or decide whether a user should buy a vehicle.

## 6. Car-only guard

Before any provider call, deterministic validation checks the query length, invisible characters, and car-related vocabulary in Burmese and English. The allowed domain includes make/model, chassis, auction, grade, year, price, body, engine, transmission, mileage, location, gate, and JACC-specific vehicle terms. Clear non-car requests such as weather, politics, general chat, poem writing, or coding are rejected with `CAR_TOPIC_ONLY` and do not consume the AI quota.

The provider output is then validated again. Unknown fields, URLs, SQL fragments, tool instructions, and non-car intents are rejected. This is a boundary control, not a claim that a keyword filter alone is a complete safety system; the deterministic JACC search and verified-row-only response are the primary correctness controls.

## 7. Server-side quota design

The daily quota must not be stored in browser storage, Flutter local storage, cookies, or Members columns. A new Supabase table should be used, leaving Members columns A–I unchanged:

```text
jacc_ai_usage_daily
- user_id text not null
- usage_date date not null
- feature text not null default 'car_text'
- ask_count integer not null default 0
- last_request_at timestamptz
- last_request_hash text
- created_at timestamptz not null default now()
- updated_at timestamptz not null default now()
unique (user_id, usage_date, feature)
```

A database function/RPC should atomically create or increment the row and return `accepted`, `ask_count`, and `remaining`. The effective date should use `Asia/Yangon`. The 11th accepted request must be rejected even if two requests arrive concurrently. A counted request remains counted if Qwen later times out, preventing retry-based quota bypass. Rejected non-car requests may be logged separately and should not consume the 10-question car quota.

## 8. Environment contract

These are Railway-only variables. They do not belong in GitHub, the browser, or Apps Script:

```text
JACC_AI_PROVIDER=qwencloud
JACC_AI_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
JACC_AI_MODEL=qwen3.7-flash
JACC_AI_API_KEY=<sealed QwenCloud key>
JACC_AI_ENABLED=false
JACC_AI_TOPIC_ONLY=true
JACC_AI_DAILY_LIMIT=10
JACC_AI_MAX_INPUT_CHARS=1200
JACC_AI_MAX_OUTPUT_TOKENS=350
JACC_AI_TIMEOUT_SECONDS=30
JACC_AI_FREE_QUOTA_ONLY=true
```

`JACC_AI_ENABLED=false` is the safe initial state. It should become `true` only after the adapter, quota migration, route, frontend contract, and regression tests pass. Existing `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-2.5-flash` remain unchanged. The current Gemini reader is not renamed, redirected, or wrapped by Qwen.

## 9. Rollout sequence

First, prepare the Supabase migration/RPC and add the Qwen adapter behind the disabled feature flag. Next, run local unit tests for parsing, car-only rejection, quota concurrency, session failure, provider timeout, malformed JSON, and secret non-exposure. Then deploy with `JACC_AI_ENABLED=false` and verify the existing website login, payment-slip upload, Gemini slip reading, JDM lookup, and Telegram flows.

After QwenCloud free quota and `Free quota only` are confirmed, enable the route for an internal Premium test user. Test one valid car query, one non-car query, same-day 10/11 request behavior, a second device, a provider failure, and a date rollover. Only after those checks pass should the feature be exposed to the approximately 20 web users. No automatic Kimi/DeepSeek fallback should be enabled in the first release because it can create unexpected billing and makes test results less deterministic.

## 10. Rollback

Rollback is a feature flag, not a destructive data operation. Set `JACC_AI_ENABLED=false`, redeploy the Railway service, and keep the existing Gemini/JDM/payment routes active. The `jacc_ai_usage_daily` table is additive and does not alter Members or payment records. If the Qwen adapter import itself causes startup problems, revert the branch commit using the existing Git backup branch before touching production.

## References

[1]: https://www.qwencloud.com/pricing/api "QwenCloud API Pricing"

[2]: https://docs.qwencloud.com/resources/free-quota "QwenCloud Free Quota"

[3]: https://docs.qwencloud.com/developer-guides/getting-started/first-api-call "QwenCloud First API Call"
