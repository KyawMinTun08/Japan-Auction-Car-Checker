# JACC vehicle-specification answer research — 2026-08-20

## User-required response shape

The supplied screenshots show a conversational chassis/model answer, not a price table alone. Typical fields are model/series, full chassis and chassis prefix, engine code, engine size, engine type, drive layout (2WD/4WD and FF/FR where verified), gearbox, power, torque, fuel, fuel-tank capacity, seats, hybrid status, and a short explanation of code/configuration differences. The answer is Burmese/English mixed and uses bullet-style facts with source chips/links.

## Current JACC boundary

The current JACC AI adapter returns a validated filter plan (`intent`, `grade_requested`, `chassis`, `filters`) and the frontend matches that plan against locally loaded `allCars` records for historical price/location/date data. `jacc_ai_knowledge.py` currently contains model vocabulary, body types, and conservative rules, but it does not contain per-model engine/spec records. Existing Gemini payment-slip OCR and auction-photo analysis are separate handlers and must remain unchanged.

## Official Gemini API findings

Google’s official generateContent Google Search grounding guide states that Grounding with Google Search can provide real-time web content and citations. The REST request uses the existing `x-goog-api-key` header, a `contents` text part, and `tools: [{"google_search": {}}]`. The response may include `groundingMetadata` with `webSearchQueries`, `groundingChunks` containing source URI/title, and `groundingSupports` linking answer segments to source chunks. Gemini 2.5 Flash is listed as supporting Google Search grounding. For Gemini 2.5 and older, billing is per prompt when search grounding is used, rather than per search query as with Gemini 3.

Google’s structured-output guide confirms that generateContent can request JSON output using `responseMimeType: application/json` and a schema/validated structured response. The JACC adapter should continue server-side validation and should never expose raw provider output or secrets to the browser.

## Safe implementation direction

Use a distinct structured `vehicle_spec` intent in the same authenticated, car-topic-only route. Keep JACC historical price matching deterministic and local. For specification answers, either use a server-maintained verified spec record or Gemini Search grounding with a strict schema and source metadata. Missing fields must be represented as unavailable rather than inferred. The frontend can render a conversational vehicle-spec card with source links, the JACC price/history summary, existing chassis detail action, and the existing Telegram request bridge.

## Sources

1. https://ai.google.dev/gemini-api/docs/generate-content/google-search — Grounding with Google Search, REST syntax, grounding metadata, citations, supported models, and pricing behavior.
2. https://ai.google.dev/gemini-api/docs/generate-content/structured-output — Structured JSON output for generateContent.
3. https://ai.google.dev/gemini-api/docs/generate-content/url-context — URL context, source retrieval metadata, supported models, and limitations.

## Compatibility correction

A follow-up check of Google’s official documentation and API guidance shows that combining built-in Google Search grounding with structured JSON output is supported for Gemini 3, but Gemini 2.5 Search grounding does not support `responseMimeType: application/json` with tool use. Therefore the safe implementation for the existing `gemini-2.5-flash` Railway model must request a strict, line-oriented grounded text answer, parse only whitelisted field labels server-side, and display the escaped grounded text plus source links. It must not send JSON structured-output configuration together with the Google Search tool on Gemini 2.5.
