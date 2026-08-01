# JACC Membership and Telegram Channel Audit

Status: initial audit completed; fixes staged but not connected to production.

## Sources reviewed

- Current `legacy_bot.py` production-path code
- Current website login/package flow
- Uploaded bot snapshots
- Uploaded Apps Script editor snapshot dated 2026-07-14

The Apps Script upload is a historical browser snapshot with only the visible editor region. The deployed `Code.gs` must still be exported or checked directly before Phase 2 release.

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

`activate_promo10d()` sent `startDate`, `expireDate` and `status`, while the normal save contract sends `days`.

Staged fix: route promo through the canonical `save_member_to_sheet(..., days=10, package="PROMO10D")` contract.

### MCH-004 — Historical Apps Script schema differs from current documented schema

Historical snapshot:

`UserID, Username, StartDate, ExpireDate, Status, Password, Package, Token`

Current documented schema:

`UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token`

Risk: password/package/token columns can shift, causing Premium→Standard mismatches and wrong credentials.

Required before release:
- Verify the actual deployed Apps Script source.
- Add a schema/version health action.
- Refuse membership writes when the schema is not the expected version.

## High findings still pending

- Package aliases are inconsistent across code paths (`WEB`, `WEB-PROMO`, `WEB_PREMIUM`, `CH-PROMO`, `STANDARD`, `PROMO10D`).
- Current approval messages can expose website passwords in formatted Telegram messages and screenshots.
- Channel validation previously treated `PROMO10D` as a possible status although it is used as a package elsewhere.
- The 3-day expiry warning creates an HTTP client without a context manager.
- Renewal/upgrade password-preservation policy needs an explicit rule and tests.

## Positive controls already present

- Single-use Telegram invite links.
- `/channel` replacement-link command for active members.
- Channel ID check and admin exemption in the join guard.
- Periodic removal of non-active members.
- Temporary Sheet failure does not trigger a mass kick.

## Staged code

`phase2_membership_guard.py` contains tested replacements for:

- ID/status/package normalization
- Expiry-aware active checks
- Package lookup
- Channel membership validation
- Promo activation contract
- Admin approval persistence gate

The module is deliberately not imported by the production launcher yet.

## Test coverage

- Numeric and `.0` Telegram ID normalization
- Package alias normalization
- Active/today, expired, invalid-date and non-active rows
- Customer access fail-closed policy
- Channel-removal fail-safe policy
- No invite or DM after failed Sheet save
- Canonical 10-day promo save payload

## Required release sequence

1. Finish and merge Phase 1 PR #8.
2. Apply and verify Supabase migration 008 and final pilot.
3. Export/verify the deployed Apps Script membership schema.
4. Retarget Phase 2 PR to `main`.
5. Connect the guard module to the launcher.
6. Run live Standard, WEB, upgrade, renewal, expired, kicked and PROMO10D tests.
7. Only then mark the Phase 2 PR ready for review.
