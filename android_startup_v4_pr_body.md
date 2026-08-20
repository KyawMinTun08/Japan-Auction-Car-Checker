## Diagnosis

The Android app loads the live GitHub Pages URL through WebView. The remaining `Connection မအောင်မြင်ပါ` state indicated that the client was still serving an older PWA/startup page or did not expose enough recovery detail after the bounded Google Sheets request failed.

## Fix

Bump the startup app/service-worker version to `2026.08.20-startup-recovery-v4` so Android WebView receives the newest startup code. Keep the backward-compatible cache migration from PR #122. Add a safe error code line when the live-data request fails, while preserving the retry button and cached-data fallback. No Android bundle or Apps Script code is changed; the WebView continues loading the live GitHub Pages URL.

## Preserved

No Members A–I changes, Apps Script changes, device/session security changes, AI/Gemini provider changes, quota changes, car-data schema changes, or estimator changes.

## Validation

Python syntax, HTML structure, inline JavaScript, PWA/device-binding tests, and the full Phase 1 suite pass: **117 passed**, one existing warning.
