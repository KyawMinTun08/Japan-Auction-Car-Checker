# JACC Membership and Telegram Channel Audit

Status: live A–J Sheet schema verified; Phase 2 membership, channel,
payment, website device binding, and Apps Script release integration are staged
but not connected to production.

## Evidence boundary

- The live production Google Sheet was read directly and uses A–J.
- The uploaded `Tele Bot - Project editor - Apps Script` file is a browser MHTML
  snapshot dated 14 July 2026. Its visible editor viewport exposes only the first
  100 Code.gs lines and shows an older A–H schema and older public doGet flow.
- That MHTML is historical evidence, not a safe complete copy of the current
  deployed Apps Script source.
- No Apps Script deployment was performed during this audit.

## Live production Members schema

`UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token, DeviceID`

The historical backup tab is A–I and must not be used as the current contract.

## Critical findings and staged fixes

### MCH-001 — False approval after Sheet save failure

Approval now stops before invite/customer success when persistence fails.

### MCH-002 — ACTIVE status trusted without expiry

Customer access requires ACTIVE plus a valid non-expired date in
Asia/Bangkok. Destructive channel removal remains fail-safe during Sheet outage.

### MCH-003 — Promo payload differed from paid membership payload

Promo activation uses the canonical authenticated member contract.

### MCH-004 — Schema history could shift member indexes

The exact A–J schema is checked before privileged actions. A discovered staged
typo was corrected: live `ExpireDate` canonicalizes to `EXPIREDATE`, not
`EXPIREDDATE`. The incorrect form would have blocked every privileged member
action with `member_schema_mismatch`.

### MCH-005 — WEB renewal could rotate or expose the password

WEB renewal preserves the existing password; CH → WEB creates one only when
needed. Admin success messages do not expose the raw password.

### MCH-006 — Payment state removed before persistence

The `slip_ok_` wrapper keeps pending state until backend success and delegates
all unrelated callbacks unchanged.

### MCH-007 — Duplicate approval could extend twice

Apps Script uses a persistent `Membership_Approval_Ledger`, an exact target
expiry, and idempotent Finance logging. The hardened write no longer depends on
unknown legacy `saveMember()` renewal semantics. It writes one canonical A–J
row to the ledger-owned target expiry, so retries cannot add another period.
Token and DeviceID are preserved on renewal.

### MCH-008 — Privileged Apps Script actions lacked server authentication

Protected actions use matching Apps Script `JACC_SERVER_KEY` and Railway
`SHEET_SERVER_KEY`. No key is committed. Both POST and GET membership callers
are covered; unrelated HTTP calls are unchanged.

### MCH-009 — One-device backend was not active in the website

The staged website uses a random installation ID, v4 server-verified sessions,
and sends app/device data on login, token restore, and getData. Apps Script
stores only `v2:<SHA-256>` in column J.

The device helper now reuses an already-held Apps Script ScriptLock. The former
nested `waitLock()` design could time out when called inside a doPost router
that already held the same non-reentrant lock.

### MCH-010 — Renewed kicked/banned members could not rejoin

Renewal/approval and `/channel` self-repair old Telegram kicked/banned state by
unbanning before issuing an invite. Existing channel members are never removed.

## Staged code

- `phase2_membership_guard.py`
- `phase2/legacy_sheet_auth.py`
- `phase2/channel_reactivation.py`
- `phase2/payment_approval.py`
- `phase2/payment_callback.py`
- `phase2/install.py`
- `phase2/website_device_binding.js`
- `phase2/apply_website_device_binding.py`
- generated Phase 2 `index.html`
- `phase2/apps_script_membership_security_patch.gs`
- `phase2/apps_script_payment_approval_patch.gs`
- `phase2/apps_script_device_binding_patch.gs`
- `phase2/apps_script_release_routes.gs`
- `phase2/apps_script_release_integration.md`

None is connected to the production launcher or deployed Apps Script yet.

## Coordinated release sequence

1. Keep PR #12 Draft.
2. Obtain/export the complete current deployed Apps Script source before editing.
3. Back up the Apps Script version and Members sheet.
4. Add the four additive Phase 2 `.gs` modules.
5. Apply the reviewed doPost/doGet/verifyLogin/verifyToken/getData insertion
   points documented in `apps_script_release_integration.md`.
6. Generate a new secret outside GitHub and set matching Apps Script/Railway
   values.
7. Confirm Telegram bot ban/unban permission.
8. Deploy Apps Script, Railway, and website atomically.
9. Run Standard, WEB, upgrade, renewal, expired, kicked, promo, channel,
   password, payment retry, duplicate tap, and device-binding acceptance tests.
10. Only then mark PR #12 Ready and request explicit owner approval before merge.

## Current release state

- Latest CI run #168 passed.
- PR #12 remains Draft and mergeable.
- Production behavior remains unchanged.
- No production secret is committed.
