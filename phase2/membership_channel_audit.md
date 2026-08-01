# JACC Membership and Telegram Channel Audit

Status: live schema verified; fixes, channel reactivation, payment idempotency, and callback integration are staged but not connected to production.

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

- 5 Standard/CH rows
- 9 WEB rows
- 1 historical WEB-PROMO row, which the Apps Script normalizer treats as WEB
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

### MCH-006 — Payment state was removed before persistence succeeded

The legacy `slip_ok_` callback used `pending_payment.pop(member_id, {})` before calling the Sheet save.

Staged fix now includes the actual Telegram callback integration:
- `phase2/payment_callback.py` intercepts only `slip_ok_`.
- Every unrelated callback is delegated unchanged to the legacy handler.
- Payment state is copied, not removed, before the backend request.
- State is kept on network failure, backend rejection, invalid response, or missing authoritative expiry.
- State is cleared only after the same idempotency key completes.
- A newer payment session cannot be deleted by an older in-flight approval.
- Admin summaries use the backend expiry and do not expose the raw website password.

### MCH-007 — New purchase and renewal used the same approval logic

The selected `action` is stored in `pending_payment`, but the legacy final approval path did not use it.

Staged fix:
- The callback forwards the explicit membership action to `approveMembershipPayment`.
- Active renewal extends from the existing expiry.
- Expired renewal starts from approval time.
- Same-package WEB renewal preserves the existing password.
- Admin/customer messages use the backend-returned package, password and expiry.

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
- staged `approveMembershipPayment`

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
- Browser access policy is decided explicitly.
- Admin reset is authenticated server-side and audited.

### MCH-010 — Expired/kicked members could not rejoin after renewal

Telegram keeps an old ban/kick state even after the Sheet membership is renewed. A new invite does not override that state.

Staged fix:
- Detect `kicked` / `banned`.
- Call `unban_chat_member(..., only_if_banned=True)` before invite delivery.
- Never remove a user already inside the channel.
- Make `/channel` self-heal the old ban.
- Do not send a known-unusable invite when unban fails.
- Notify the customer and admin when bot permissions prevent the repair.

## Payment idempotency design

The staged Apps Script action `approveMembershipPayment` uses:

- Script Lock around approval processing
- `Membership_Approval_Ledger`
- a stable transaction/reference fingerprint
- COMPLETED-key deduplication
- PROCESSING recovery using target expiry
- one-time Finance logging by idempotency key
- backend-returned authoritative expiry/package/password

Repeated admin taps, retry after a timeout, or Railway restart must not extend the same payment twice.

## High findings still pending

- Package aliases remain historically inconsistent across code paths, though the normalizer reduces the impact.
- The 3-day expiry warning creates an HTTP client without a context manager.
- Username-only approval cannot reliably DM the member because no numeric Telegram ID is resolved.
- The unknown-action default branch in Apps Script appends car data; changing this requires a compatibility review.
- Spreadsheet metadata timezone is `Etc/UTC` while business formatting uses `Asia/Bangkok`; trigger schedules need an explicit timezone test.

## Staged code

- `phase2_membership_guard.py` — membership normalization, expiry checks, secure Sheet callers and password policy
- `phase2/channel_reactivation.py` — renewed-member auto-unban and `/channel` self-repair
- `phase2/payment_approval.py` — retry-safe/idempotent payment contract
- `phase2/payment_callback.py` — actual `slip_ok_` Telegram integration
- `phase2/install.py` — ordered membership → channel → payment installation
- `phase2/apps_script_membership_security_patch.gs` — server-key/schema preflight
- `phase2/apps_script_payment_approval_patch.gs` — atomic approval ledger and authoritative response

None of these files is connected to the production launcher yet.

## Test coverage

- Numeric and `.0` Telegram ID normalization
- Package alias normalization
- Active/today, expired, invalid-date and non-active rows
- Customer access fail-closed policy
- Channel-removal fail-safe policy
- No invite or DM after failed Sheet save
- WEB renewal password preservation
- Privileged server-key payloads
- Old-ban renewal reactivation and `/channel` self-repair
- Payment retry state preservation
- Duplicate tap deduplication
- Partial PROCESSING recovery
- Backend authoritative expiry only
- Non-payment callback delegation unchanged
- No raw password in admin success summary
- Ordered runtime installation

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Add `SHEET_SERVER_KEY` support to every remaining privileged Railway caller.
3. Generate a new random secret outside GitHub.
4. Set the same value in Apps Script Script Properties and Railway environment variables.
5. Insert the Apps Script membership preflight and payment approval route/functions.
6. Deploy a new Apps Script version without changing the public Web App URL.
7. Import and run `phase2.install()` before `legacy_bot.main()` registers handlers.
8. Confirm Telegram bot ban/unban permission.
9. Deploy Railway callers in the same maintenance window.
10. Run live Standard, WEB, upgrade, renewal, expired, kicked, PROMO, channel, password, payment retry, duplicate tap and device-binding tests.
11. Verify a previously kicked/banned account can renew and rejoin without admin action.
12. Only then mark PR #12 ready and request explicit owner approval before merge.
