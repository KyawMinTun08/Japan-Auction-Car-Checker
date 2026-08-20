## Root cause

The startup-recovery release intentionally bumped `APP_VERSION` to refresh the PWA. `readCarsCache()` required the stored cache `version` to equal the new app version, so previously valid car data became unusable. When the Google Sheets request then timed out or failed, the app had no fallback and displayed `Connection မအောင်မြင်ပါ`.

## Fix

Separate cache schema compatibility from frontend app versioning. The reader accepts the previous `2026.08.19-ai-console-v2` cache when it is fresh and non-empty, while new writes include the stable `schemaVersion: 'jacc-cars-v2'` marker. The existing 7-day freshness limit remains unchanged. The response-body timeout from PR #121 remains active.

## Preserved

No Apps Script changes, Members A–I changes, session/device security changes, AI provider changes, Gemini OCR/photo changes, quota changes, car-data schema changes, or cost-estimate changes.

## Validation

Python syntax, HTML structure, inline JavaScript, PWA/startup checks, and the full Phase 1 suite pass: **117 passed**, one existing warning.
