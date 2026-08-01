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

### MCH-005 — WEB renewals rotated the password

The manual and payment approval paths generated a fresh WEB password instead of preserving the member's current password. This breaks saved logins and contradicts the intended renewal behavior.

Staged fix in the guard:
- WEB → WEB renewal preserves the existing password.
- CH → WEB generates a password only when none exists.
- CH membership does not create a WEB password.

The payment callback still needs to call the staged policy before production activation.

### MCH-006 — Payment state is removed before persistence succeeds

The `slip_ok_` callback uses `pending_payment.pop(member_id, {})` before calling `save_member_to_sheet()`.

Risk:
- A temporary Sheet failure destroys the in-memory payment context.
- Admin receives a manual-fix warning but cannot safely retry the same approval.

Required fix:
- Read without removing.
- Persist membership and payment log first.
- Remove the pending record only after the required write succeeds.
- Add an idempotency key so repeated approval taps cannot double-extend membership.

### MCH-007 — New purchase and renewal use the same approval logic

The selected `action` is stored in `pending_payment`, but the final approval path does not use it. The client also displays an expiry calculated from the current date; the real extension behavior depends on the deployed Apps Script `saveMember()` implementation, which is not visible in the historical snapshot.

Required fix:
- Define explicit `new`, `renew`, `upgrade`, and optional `downgrade` transitions.
- Extend from the later of today or the current expiry for renewals.
- Preserve the same member row and Telegram ID.
- Verify the final expiry returned by the backend instead of calculating a separate display-only date in the bot.

## High findings still pending

- Package aliases are inconsistent across code paths (`WEB`, `WEB-PROMO`, `WEB_PREMIUM`, `CH-PROMO`, `STANDARD`, `PROMO10D`).
- Current payment/admin approval summaries can expose website passwords in formatted Telegram messages and screenshots.
- Channel validation previously treated `PROMO10D` as a possible status although it is used as a package elsewhere.
- The 3-day expiry warning creates an HTTP client without a context manager.
- Username-only approval cannot reliably DM the member because no Telegram numeric ID is resolved.
- The website stores its session token in `localStorage`. `getData` sends the token back to the backend, but server-side expiry, revocation, and one-device enforcement cannot be confirmed without the deployed Apps Script source.

## Positive controls already present

- Single-use Telegram invite links.
- `/channel` replacement-link command for active members.
- Channel ID check and admin exemption in the join guard.
- Periodic removal of non-active members.
- Temporary Sheet failure does not trigger a mass kick.
- Website data loading sends the session token to the backend.

## Staged code

`phase2_membership_guard.py` contains tested replacements for:

- ID/status/package normalization
- Expiry-aware active checks
- Package lookup
- Channel membership validation
- Promo activation contract
- Admin approval persistence gate
- WEB password preservation policy

The module is deliberately not imported by the production launcher yet.

## Test coverage

- Numeric and `.0` Telegram ID normalization
- Package alias normalization
- Active/today, expired, invalid-date and non-active rows
- Customer access fail-closed policy
- Channel-removal fail-safe policy
- No invite or DM after failed Sheet save
- Canonical 10-day promo save payload
- WEB renewal preserves the existing password
- CH → WEB generates a password only when missing
- CH does not create a WEB password

## Required release sequence

1. Finish and merge Phase 1 PR #8.
2. Apply and verify Supabase migration 008 and final pilot.
3. Export/verify the deployed Apps Script membership schema and renewal behavior.
4. Retarget Phase 2 PR to `main`.
5. Fix payment-state idempotency and connect the guard module to the launcher.
6. Run live Standard, WEB, upgrade, renewal, expired, kicked and PROMO10D tests.
7. Only then mark the Phase 2 PR ready for review.
