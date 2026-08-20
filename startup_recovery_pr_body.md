## Problem

The JACC mobile app could remain on `Google Sheets ထဲမှ Data ဆွဲနေသည် / Live data update လုပ်နေသည်` when Apps Script returned response headers but stalled while the response body was being read. The existing timeout covered only the initial `fetch()` promise; `res.json()` ran outside that timeout.

## Fix

Add `fetchJsonWithTimeout()` for the startup car-data request. It bounds both the network request and response-body text read, aborts on timeout, and routes the existing `init()` catch block to the retry/error state or cached-data fallback. Bump the PWA cache to `jacc-2026.08.20-startup-recovery-v3` so mobile clients receive the updated startup code.

## Preserved

No Apps Script changes, Members A–I changes, device/session contract changes, AI provider changes, Gemini OCR/photo changes, JACC car-data schema changes, quota changes, or cost-estimate changes.

## Validation

Python syntax, HTML structure, inline JavaScript, startup reliability, PWA cache, device binding, and the full Phase 1 suite pass: **117 passed**, one existing warning.
