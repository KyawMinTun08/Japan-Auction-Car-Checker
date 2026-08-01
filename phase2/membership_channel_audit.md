# JACC Membership and Telegram Channel Audit

Status: live schema verified; membership, payment, channel, and security fixes staged but not connected to production.

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

The legacy `slip_ok_` callback uses `pending_payment.pop(member_id, {})` before the Sheet save.

Risk:
- A temporary Sheet failure destroys the payment context.
- Admin cannot safely retry the same approval.
- A repeated button tap can extend the member more than once.

Staged fix in `phase2/payment_approval.py`:
- Read a copy without deleting the pending state.
- Build a stable, non-secret idempotency key from the transaction/reference number or immutable payment fields.
- Send one atomic `approveMembershipPayment` action.
- Keep the pending state on network error, backend rejection, or missing authoritative expiry.
- Remove the pending state only after backend `status: ok`.
- Do not remove a newer payment session that replaced an older in-flight request.

Persistent backend contract in `phase2/apps_script_payment_approval_patch.gs`:
- `Membership_Approval_Ledger` records idempotency key, state, target expiry, actual expiry, and package.
- A completed key returns success without calling `saveMember()` again.
- A PROCESSING key checks whether the target expiry was already applied before retrying.
- Finance rows include an idempotency key and are appended once.
- Script Lock plus the persistent ledger protects restarts and repeated admin taps.

The legacy callback is not wired to this helper yet, so production remains unchanged.

### MCH-007 — Bot displayed a guessed expiry instead of the backend expiry

The legacy approval path calculated `now + months * 30`, which is wrong for an active renewal that extends from the existing expiry.

Staged fix:
- `approveMembershipPayment` reads the final saved member row.
- The backend returns `expireDate`, normalized package, and authoritative password.
- The bot helper refuses to clear payment state or display success when `expireDate` is missing.
- Admin and customer messages must use the returned expiry, not a local calculation.

### MCH-008 — Privileged Apps Script membership actions lack server authentication

The reviewed `doPost()` routes privileged operations by action name. The reviewed source does not require a Railway-only credential for actions including:

- `saveMember`
- `approveMembershipPayment` after Phase 2 integration
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

### MCH-010 — Renewed members can remain Telegram-banned

A member can renew successfully in the Sheet and use the website while an old Telegram kick/ban still blocks every new channel invite.

Staged fix in `phase2/channel_reactivation.py`:
- Check the member's channel status after successful approval/renewal.
- Use `unban_chat_member(..., only_if_banned=True)` for old kicked/banned states.
- Never remove a member already inside the channel.
- Make `/channel` retry the repair before issuing a replacement link.
- Suppress a known-unusable invite and notify customer/admin when unban fails.

The bot must have Telegram channel permission to ban/unban members.

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

### `phase2/channel_reactivation.py`

Contains tested Telegram-side renewal repair for old kicked/banned members.

### `phase2/payment_approval.py`

Contains the retry-safe Railway approval contract and authoritative-expiry requirement.

### `phase2/apps_script_membership_security_patch.gs`

Contains a staged Apps Script preflight for:

- Railway-only server credential validation
- A–J schema/version validation
- Privileged action protection
- Safe `memberSchemaHealth` diagnostic

### `phase2/apps_script_payment_approval_patch.gs`

Contains the persistent payment idempotency ledger, partial-completion recovery, one-time Finance logging, and authoritative result response.

None of these files is connected to production yet.

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
- Old banned member is unbanned before renewal invite delivery
- Existing channel member is left untouched
- `/channel` self-repairs an old ban
- Payment state remains after backend/network failure
- Missing authoritative expiry remains retryable
- Successful and duplicate backend responses use the backend expiry
- A newer payment session is not removed by an older in-flight approval
- Persistent Apps Script ledger and one-time Finance log contracts
- PROCESSING recovery checks target expiry before another membership write

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Wire the legacy `slip_ok_` callback to `approve_pending_payment()` and use the returned expiry/package/password in all DMs and admin messages.
3. Add `SHEET_SERVER_KEY` support to every Railway privileged Sheet caller.
4. Generate a new random secret outside GitHub.
5. Set the same value in Apps Script Script Properties and Railway environment variables.
6. Insert the membership preflight and `approveMembershipPayment` route into `doPost()`.
7. Deploy both Apps Script patches in one new version without changing the public Web App URL.
8. Install membership and channel guards before Telegram handlers are registered.
9. Deploy Railway callers in the same maintenance window.
10. Confirm the bot has Telegram channel ban/unban permission.
11. Run schema health and live Standard, WEB, upgrade, renewal, expired, kicked, PROMO, channel, password, payment-retry, duplicate-tap, and device-binding tests.
12. Include a previously channel-banned account and confirm renewal restores channel entry without admin action.
13. Verify no customer data was exposed and no mass channel removal occurred.
14. Only then mark PR #12 ready for review and request explicit owner approval before merge.
