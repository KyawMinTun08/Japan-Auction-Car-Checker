# JACC Membership and Telegram Channel Audit

Status: live schema verified; fixes, channel reactivation, payment idempotency,
callback integration, and privileged caller authentication are staged but not
connected to production.

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

The historical backup tab is an older A–I snapshot without DeviceID. It must
not be used as the current production schema contract.

### Aggregate active-member state

At audit time, the live Sheet contained 15 ACTIVE rows:

- 5 Standard/CH rows
- 9 WEB rows
- 1 historical WEB-PROMO row, which the Apps Script normalizer treats as WEB
- 1 populated token
- 0 populated DeviceID values

No member IDs, usernames, passwords, or tokens are recorded in this audit
document.

## Critical findings and staged fixes

### MCH-001 — False approval after Sheet save failure

Legacy approval could report success even when membership was not persisted.
The staged flow stops immediately and sends no invite or customer success DM
when the backend write fails.

### MCH-002 — ACTIVE status was trusted without checking expiry

Staged checks require normalized `ACTIVE` plus a valid non-expired date in
`Asia/Bangkok`. Customer access fails closed. Destructive channel removal fails
safe during temporary Sheet outages.

### MCH-003 — Promo save payload differed from paid membership payload

Promo activation now uses the canonical authenticated `saveMember` contract.

### MCH-004 — Schema history could shift password/package/token indexes

The live A–J schema is verified. Staged `memberSchemaHealth` checks exact A–J
headers and rejects privileged operations on mismatch.

### MCH-005 — WEB renewals could rotate or display the wrong password

WEB renewal preserves the existing password. CH → WEB generates a password
only when none exists. Admin success messages do not reveal the raw website
password.

### MCH-006 — Payment state was removed before persistence succeeded

`phase2/payment_callback.py` intercepts only `slip_ok_`; unrelated callbacks are
delegated unchanged. Payment state remains until authoritative backend success
and is cleared only for the completed idempotency key.

### MCH-007 — Duplicate approval could extend membership twice

The staged Apps Script `approveMembershipPayment` action uses Script Lock and a
persistent `Membership_Approval_Ledger`. Completed keys deduplicate retries and
PROCESSING rows recover using the target expiry.

### MCH-008 — Privileged Apps Script membership actions lacked server auth

Protected actions are:

- `saveMember`
- `approveMembershipPayment`
- `getMembers`
- `getPassword`
- `resetPassword`
- `updateMemberId`
- `getBackupCSV`
- `updateStatus`
- `resetMemberDevice`

Railway uses `SHEET_SERVER_KEY`; Apps Script uses Script Property
`JACC_SERVER_KEY`. No key value is committed.

The legacy bot contains POST JSON callers and a GET query-parameter
`getMembers` caller used by broadcast-photo mode. The staged
`phase2/legacy_sheet_auth.py` replaces only the `legacy_bot.httpx` global with a
scoped proxy. For the configured Sheet webhook and a protected action it:

- injects the Railway-owned key into JSON, query parameters, or form data;
- overwrites untrusted caller-provided key input;
- does not mutate the caller's original payload;
- leaves unrelated URLs and non-membership actions unchanged; and
- fails before network access when the key is missing.

Apps Script must run `jaccMembershipPreflight_` in both `doPost(e)` and
`doGet(e)`. `verifyLogin` and `verifyToken` remain public because browser/app
clients authenticate with member credentials and must never receive the server
key.

### MCH-009 — One-device backend exists but the current frontend does not activate it

The uploaded `Code.gs` supports device binding, but the current website does not
send `deviceId`/`app`. Live DeviceID cells were blank. Client installation-ID
integration and an explicit browser policy remain required.

### MCH-010 — Expired/kicked members could not rejoin after renewal

Staged channel reactivation detects old `kicked`/`banned` state, calls
`unban_chat_member(..., only_if_banned=True)`, never removes an existing member,
and makes `/channel` retry the repair before issuing an invite.

## Staged code

- `phase2_membership_guard.py` — normalization, expiry checks, canonical secure callers and password policy
- `phase2/legacy_sheet_auth.py` — scoped authentication for remaining direct legacy Sheet calls
- `phase2/channel_reactivation.py` — renewed-member auto-unban and `/channel` self-repair
- `phase2/payment_approval.py` — retry-safe/idempotent payment contract
- `phase2/payment_callback.py` — actual `slip_ok_` Telegram integration
- `phase2/install.py` — ordered membership → Sheet auth → channel → payment installation
- `phase2/apps_script_membership_security_patch.gs` — POST/GET server-key and schema preflight
- `phase2/apps_script_payment_approval_patch.gs` — atomic approval ledger and authoritative response

None of these files is connected to the production launcher yet.

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Generate a new random secret outside GitHub.
3. Set the same value in Apps Script Script Properties and Railway environment variables.
4. Insert Apps Script membership preflight into both POST and GET routes.
5. Insert the Apps Script payment approval route/functions.
6. Deploy a new Apps Script version without changing the public Web App URL.
7. Import and run `phase2.install()` before `legacy_bot.main()` registers handlers.
8. Confirm Telegram bot ban/unban permission.
9. Deploy Railway in the same maintenance window.
10. Run live Standard, WEB, upgrade, renewal, expired, kicked, promo, channel, password, payment-retry, duplicate-tap and device-binding tests.
11. Verify a previously kicked/banned account can renew and rejoin without admin action.
12. Only then mark PR #12 Ready and request explicit owner approval before merge.

## Current release state

- PR #12 remains Draft.
- Production launcher does not import Phase 2.
- Apps Script patches are not deployed.
- No server key is committed.
- Production behavior remains unchanged.
