# JACC Membership and Telegram Channel Audit

Status: live schema verified; fixes and security rollout staged but not connected to production.

## Sources reviewed

- Current `legacy_bot.py` production-path code
- Current `index.html` website login/package flow
- Uploaded bot snapshots
- Uploaded `Code.gs` source with A–J member/device support
- Live production Google Sheet metadata and bounded `Members` ranges
- Historical `Members_Backup_20260716_pre_package_fix` tab

Important evidence boundary:
- The live Sheet structure was read directly.
- The Apps Script source was reviewed from the uploaded `Code.gs` snapshot.
- A new Apps Script deployment has not been performed during this audit.

## Live production evidence

### Members schema

The live `Members` tab currently uses ten columns:

`UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token, DeviceID`

This matches the uploaded `Code.gs` constants:

- A / index 0 — UserID
- B / index 1 — Username
- C / index 2 — StartDate
- D / index 3 — ExpireDate
- E / index 4 — Status
- F / index 5 — CancelCount
- G / index 6 — Password
- H / index 7 — Package
- I / index 8 — Token
- J / index 9 — DeviceID

The historical backup tab is an older A–I snapshot without DeviceID. It must not be used as the current production schema contract.

### Aggregate active-member state

At audit time, the live Sheet contained 15 ACTIVE rows:

- 5 normalized Standard/CH
- 10 normalized Web-capable rows, including one historical WEB-PROMO alias
- 1 populated token
- 0 populated DeviceID values

No member IDs, usernames, passwords, or tokens are recorded in this audit document.

## Critical findings

### MCH-001 — False approval after Sheet save failure

`approve_member()` ignored the boolean result from `save_member_to_sheet()`. It could send a password and channel invite and report success even though the membership was not persisted.

Staged fix: stop immediately, send no invite/DM, and tell the admin the customer is not approved yet.

### MCH-002 — ACTIVE status was trusted without checking expiry

`is_active_member()`, `get_member_package()` and `is_valid_member()` did not independently reject an expired `expireDate`.

Staged fix: require normalized `ACTIVE` plus a valid date that is today or later in `Asia/Bangkok`.

Policy:
- Customer access checks fail closed when membership cannot be proven.
- Destructive channel-kick checks fail safe during temporary Sheet outages.

### MCH-003 — Promo save payload differed from paid membership payload

`activate_promo10d()` sent a different payload from the paid membership path.

Staged fix: route promo through the canonical authenticated `saveMember` contract.

Note: the current Apps Script package normalizer maps names containing `WEB` or `PREMIUM` to WEB. Promo package naming must remain consistent with that backend rule.

### MCH-004 — Schema history could shift password/package/token indexes

The live A–J schema is now verified and matches the uploaded Code.gs constants. The older backup is A–I.

Remaining risk: future manual column insertion could silently shift fields.

Staged fix:
- Add `memberSchemaHealth` returning schema version `JACC_MEMBERS_V2_AJ`.
- Check exact A–J headers before privileged membership reads/writes.
- Refuse privileged operations when the schema does not match.

### MCH-005 — WEB renewals rotated the password in legacy bot paths

The legacy approval path generated a fresh WEB password before every save. The uploaded Apps Script already preserves the existing password for WEB → WEB renewal, but the bot could still display or DM the newly generated value rather than the authoritative preserved value.

Staged fix:
- WEB → WEB renewal fetches and preserves the existing password.
- CH → WEB generates a password only when none exists.
- CH membership does not create a WEB password.
- All privileged reads/writes use the authenticated server-to-server contract.

### MCH-006 — Payment state is removed before persistence succeeds

The `slip_ok_` callback uses `pending_payment.pop(member_id, {})` before calling the Sheet save.

Risk:
- A temporary Sheet failure destroys the in-memory payment context.
- Admin receives a manual-fix warning but cannot safely retry the same approval.

Required fix:
- Read without removing.
- Persist membership and payment log first.
- Remove the pending record only after the required write succeeds.
- Add an idempotency key so repeated approval taps cannot double-extend membership.

### MCH-007 — New purchase and renewal use the same approval logic

The selected `action` is stored in `pending_payment`, but the final approval path does not use it.

The uploaded `saveMember()` behavior is clear:
- Active renewal extends from the existing expiry.
- Expired renewal starts from approval time.
- Same-package WEB renewal preserves the existing password.

Required bot fix:
- Define explicit `new`, `renew`, `upgrade`, and optional `downgrade` transitions.
- Preserve the same row and Telegram ID.
- Display the backend-returned expiry instead of independently calculating it.

### MCH-008 — Privileged Apps Script membership actions lack server authentication

The reviewed `doPost()` routes privileged operations by action name. The reviewed source does not require a Railway-only credential for actions including:

- `saveMember`
- `getMembers`
- `getPassword`
- `resetPassword`
- `updateMemberId`
- `getBackupCSV`
- `updateStatus`
- `resetMemberDevice`

Because the web app endpoint is reachable from browser code, these actions must not rely on the URL being secret.

Staged fix:
- Apps Script Script Property: `JACC_SERVER_KEY`
- Railway environment variable: `SHEET_SERVER_KEY`
- Constant-time credential comparison before privileged actions
- Fail closed when the key is missing or invalid
- Keep `verifyLogin` and `verifyToken` public because they authenticate through member password/token

This must be deployed atomically. Enabling Apps Script protection before Railway sends the key would break membership checks and approvals.

### MCH-009 — One-device backend exists but the current frontend does not activate it

The uploaded `Code.gs` supports Flutter binding when both conditions are present:

- `app` equals `flutter`
- a non-empty `deviceId` is sent

The current repository `index.html` sends only the password during `verifyLogin` and does not reference `jacc_installation_id` or `deviceId`.

Live evidence: all active member DeviceID cells were blank at audit time.

Conclusion: one-device enforcement is not proven active in the current customer flow.

Required fix:
- Flutter/WebView exposes its secure installation ID.
- Website includes `{app: "flutter", deviceId: ...}` in both `verifyLogin` and `verifyToken` requests only inside the app.
- Browser access policy is decided explicitly: unrestricted browser, browser-session limit, or browser device binding.
- Admin reset is authenticated server-side and audited.

## High findings still pending

- Package aliases remain historically inconsistent across code paths, though the Apps Script normalizer reduces the impact.
- Current payment/admin summaries can expose website passwords in Telegram messages and screenshots.
- The 3-day expiry warning creates an HTTP client without a context manager.
- Username-only approval cannot reliably DM the member because no numeric Telegram ID is resolved.
- The unknown-action default branch in Apps Script appends car data; changing this requires a compatibility review of all legacy clients.
- The spreadsheet metadata timezone is `Etc/UTC` while business date formatting uses `Asia/Bangkok`; date parsing and trigger schedules need an explicit timezone test.

## Positive controls already present

- Live A–J schema now includes CancelCount and DeviceID.
- Uploaded Apps Script uses constants rather than hard-coded membership indexes.
- Uploaded `saveMember()` extends active expiry and preserves same-package WEB passwords.
- Uploaded login/token/password functions check normalized package, status, and expiry.
- Single-use Telegram invite links.
- `/channel` replacement-link command for active members.
- Channel ID check and admin exemption in the join guard.
- Periodic removal of non-active members.
- Temporary Sheet failure does not trigger a mass kick.
- Website data loading sends the session token to the backend.

## Staged code

### `phase2_membership_guard.py`

Contains tested replacements for:

- ID/status/package normalization
- Expiry-aware active checks
- Package lookup
- Channel membership validation
- Promo activation contract
- Admin approval persistence gate
- WEB password preservation policy
- Authenticated privileged Apps Script payloads
- Secure `saveMember` replacement

### `phase2/apps_script_membership_security_patch.gs`

Contains a staged Apps Script preflight for:

- Railway-only server credential validation
- A–J schema/version validation
- Privileged action protection
- Safe `memberSchemaHealth` diagnostic

Neither file is connected to production yet.

## Test coverage

- Numeric and `.0` Telegram ID normalization
- Package alias normalization
- Active/today, expired, invalid-date and non-active rows
- Customer access fail-closed policy
- Channel-removal fail-safe policy
- No invite or DM after failed Sheet save
- Canonical promo save payload
- WEB renewal preserves the existing password
- CH → WEB generates a password only when missing
- CH does not create a WEB password
- Privileged payload contains `serverKey`
- Missing `SHEET_SERVER_KEY` fails before any HTTP request
- `getMembers`, `getPassword`, and `saveMember` use the secure caller
- Apps Script patch contains no literal credential
- Privileged action list and A–J schema contract are covered by static tests

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Finish payment-state idempotency and authoritative-expiry handling.
3. Add `SHEET_SERVER_KEY` support to every Railway privileged Sheet caller.
4. Generate a new random secret outside GitHub.
5. Set the same value in Apps Script Script Properties and Railway environment variables.
6. Insert the Apps Script preflight into `doPost()`.
7. Deploy a new Apps Script version without changing the public Web App URL.
8. Deploy Railway callers in the same maintenance window.
9. Run schema health and live Standard, WEB, upgrade, renewal, expired, kicked, PROMO, channel, password, and device-binding tests.
10. Verify no customer data was exposed and no mass channel removal occurred.
11. Only then mark PR #12 ready for review and request explicit owner approval before merge.
