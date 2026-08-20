## Problem

The installed Android app uses Flutter WebView to load the live GitHub Pages URL with `?app=flutter&jacc_app=1`. The web startup fixes were deployed, but an existing WebView could continue requesting the old URL/cache path and still show the connection error.

## Fix

Add `build=2026.08.20.4` to the Flutter `websiteUrl`. Add a Flutter-only web-side redirect for old app URLs so existing installed apps request the new build query without clearing origin localStorage, saved login state, or the device installation ID. No `clearCache`, `clearFormData`, or app-data deletion is introduced.

## Preserved

The app continues to use the live GitHub Pages URL. Device bridge injection, `deviceId`, `app=flutter`, session verification, Apps Script, Members A–I, Gemini, AI quota, and existing website cache fallback remain unchanged.

## Validation

HTML structure, inline JavaScript, PWA/device-binding contracts, and the full Phase 1 suite pass: **117 passed**, one existing warning. The sandbox does not include the Flutter SDK, so `flutter analyze` could not run locally; the Flutter edit is a single constant URL change and the repository’s static assertions cover the expected URL/build marker.
