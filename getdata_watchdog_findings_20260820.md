# JACC getData watchdog findings — 2026-08-20

## Phone evidence
- Screenshot reports `Error code: DATA_WATCHDOG_TIMEOUT`.
- Screenshot reports `Stage: WATCHDOG_TIMEOUT`.
- This means the frontend startup watchdog fired before the authenticated getData request completed; it is not a login-screen error.

## Production endpoint measurements from the live JACC page
- Public GET route to the Apps Script endpoint returned HTTP 200 with approximately 1,235,075 bytes in about 8.0 seconds. This route is currently unauthenticated in `Code.gs` and must not be used as an authenticated frontend workaround.
- Secure POST `getData` with an intentionally invalid token returned HTTP 200 with `{"status":"error","msg":"invalid_token"}` in approximately 13.3 seconds.
- The secure POST path uses a global `LockService.getScriptLock()` in `doPost`, with `waitLock(30000)`, before dispatching any action.
- Secure `getData` verifies the token/device/session and then reads the complete Sheet1 range and serializes all cars. The response is approximately 1.23 MB in production.

## Source review
- `Code.gs` case `getData` begins at line 707 and reads all `Sheet1` rows after `verifyToken`.
- `verifyToken` performs Members, DeviceBindings, and AuthSessions reads/updates.
- Members columns A–I remain unchanged.

## Safety conclusion
- The public GET route must not be used to bypass token/device binding.
- The evidence supports reducing the global lock scope for authenticated read-only `getData`; this requires an Apps Script change and deployment, subject to confirmation because the project instruction protects Apps Script changes.
