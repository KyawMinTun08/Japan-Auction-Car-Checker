# JACC Membership and Telegram Channel Audit

Status: live schema verified; fixes, channel reactivation, payment idempotency,
callback integration, privileged caller authentication, and one-installation
device binding are staged but not connected to production.

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

### MCH-009 — One-device backend existed but the current frontend did not activate it

The current production website sends neither `deviceId` nor `app`, trusts a
local `v3` session without server revalidation, and has blank live DeviceID
cells.

The staged Phase 2 policy is now explicit:

- WEB access is bound to one browser, installed PWA, or Flutter installation.
- The client creates a cryptographically random 24-byte installation ID and
  keeps it in `localStorage` under `jacc_installation_id`.
- `verifyLogin`, `verifyToken`, and protected `getData` requests send
  `{app, deviceId}`.
- Session format moves from `v3` to `v4` so old locally trusted sessions cannot
  bypass the new server check.
- Every page startup revalidates the stored token and device before showing the
  application.
- Apps Script stores only `v2:<SHA-256>` in Members!J, never the raw ID.
- The first successful Phase 2 login binds an existing member whose DeviceID is
  blank.
- A second installation receives `device_mismatch`.
- Logout preserves the installation ID; clearing browser/PWA data or changing
  phones requires an authenticated admin reset.
- `resetMemberDevice` remains protected by `JACC_SERVER_KEY`.
- IP address is not used as a device key because the policy is installation
  binding, not network-location binding.

`phase2/apply_website_device_binding.py` deterministically transforms the
current large single-file `index.html` and refuses to operate if the expected
login/session contract has drifted. CI applies that transformation to the
current website source and verifies idempotence. The generated `index.html`
diff still must be reviewed and committed before production deployment.

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
- `phase2/website_device_binding.js` — stable client installation ID and startup token/device verification
- `phase2/apps_script_device_binding_patch.gs` — hashed Members!J binding and protected reset
- `phase2/apply_website_device_binding.py` — guarded, idempotent `index.html` integration

None of these files is connected to the production launcher or deployed Apps
Script yet. The repository `index.html` has not yet been replaced by the
generated Phase 2 version.

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Run `python phase2/apply_website_device_binding.py index.html`, review the
   generated website diff, and commit it to the Phase 2 branch.
3. Generate a new random secret outside GitHub.
4. Set the same value in Apps Script Script Properties and Railway environment variables.
5. Insert Apps Script membership preflight into both POST and GET routes.
6. Insert Apps Script payment approval and hashed device-binding route/functions.
7. Deploy a new Apps Script version without changing the public Web App URL.
8. Import and run `phase2.install()` before `legacy_bot.main()` registers handlers.
9. Confirm Telegram bot ban/unban permission.
10. Deploy Railway and the website in the same maintenance window.
11. Run live Standard, WEB, upgrade, renewal, expired, kicked, promo, channel,
    password, payment-retry, duplicate-tap and device-binding tests.
12. Verify the same device can log out/log in, a second device is rejected, an
    admin reset permits a replacement device, and an old kicked/banned account
    can renew and rejoin without admin channel action.
13. Only then mark PR #12 Ready and request explicit owner approval before merge.

## Current release state

- PR #12 remains Draft.
- Production launcher does not import Phase 2.
- Apps Script patches are not deployed.
- Generated Phase 2 `index.html` is not committed or deployed yet.
- No server key is committed.
- Production behavior remains unchanged.
