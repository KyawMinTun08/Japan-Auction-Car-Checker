# JACC Membership and Telegram Channel Audit

Status: initial code audit

Scope:
- Telegram membership approval, renewal, password and package handling
- Telegram channel invite, join guard and expiry removal
- Google Apps Script member schema compatibility
- Website login/package access contract

## Evidence reviewed

- Current production-path code in `legacy_bot.py` on `agent/jacc-phase1-foundation`
- Current website `index.html`
- Uploaded historical bot snapshots
- Uploaded Apps Script editor snapshot dated 2026-07-14

The Apps Script upload is a browser snapshot and exposes only the visible editor region. It is useful as historical evidence, but it must not be treated as proof of the current deployed Apps Script version.

## Critical findings

### MCH-001 — Approval continues when Sheet persistence fails

`approve_member()` calls `save_member_to_sheet()` but ignores its boolean result. It then creates an invite, sends the approval DM/password, and tells the admin that approval succeeded.

Impact:
- Customer receives a password and channel link but has no valid persisted membership.
- Website login or `/mypassword` can fail immediately after payment approval.
- Admin sees a false success message.

Required fix:
- Stop the flow when `save_member_to_sheet()` returns false.
- Do not generate/send an invite or password.
- Notify admin with a clear retry/manual-recovery message.
- Add a regression test.

### MCH-002 — Membership checks trust status but not expiry

`is_active_member()`, `get_member_package()` and `is_valid_member()` rely on the row status and do not independently reject a past `expireDate`.

Impact:
- A stale `ACTIVE` row can retain `/channel`, `/mypassword`, website-package and channel access.
- Expiry enforcement depends entirely on another process updating status on time.

Required fix:
- Normalize IDs and status.
- Parse `expireDate` in Bangkok time and require it to be today or later.
- Fail closed for customer access checks when Sheet data is malformed.
- Keep channel-removal operations fail-safe on temporary Sheet outages.

### MCH-003 — Promo activation payload is inconsistent with normal save contract

`activate_promo10d()` posts `startDate`, `expireDate` and `status`, while the normal `saveMember` caller posts `days`.

The uploaded Apps Script snapshot routes `saveMember` using `data.days`, which suggests the promo call can create incorrect or missing dates if the deployed script follows that contract.

Required fix:
- Use one canonical `saveMember` request schema.
- Route promo activation through `save_member_to_sheet(..., days=10, package="PROMO10D")` or explicitly version the Apps Script contract.
- Verify against the deployed Apps Script before release.

### MCH-004 — Historical Apps Script schema conflicts with current documented schema

The uploaded Apps Script snapshot shows:

`UserID, Username, StartDate, ExpireDate, Status, Password, Package, Token`

Current project documentation expects:

`UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token`

Impact if an old deployment is still active:
- Password, package and token read/write indexes shift by one column.
- Premium members can be saved as Standard or receive the wrong password/token.

Required fix:
- Fetch/export the actual deployed `Code.gs` source.
- Add a `schemaVersion`/`health` action that returns column names and indexes.
- Refuse membership writes when the schema is not version 2.

## High findings

### MCH-005 — Package normalization is inconsistent

Different paths recognize different values: `WEB`, `WEB-PROMO`, `CH`, `CH-PROMO`, `PROMO10D`, `STANDARD`.

Required fix:
- Add one canonical package normalizer.
- Store only `CH`, `WEB`, or `PROMO10D` in the source of truth.
- Treat marketing labels as display-only values.

### MCH-006 — Password is exposed in rich approval/admin messages

Current branch embeds the website password inside formatted Telegram messages. Copying can include formatting/extra characters, and screenshots expose credentials.

Required fix:
- Send the password as a separate plain-text message.
- Keep it out of admin success summaries unless explicitly requested.
- Rotate any password exposed publicly.

### MCH-007 — Channel guard accepts a status value that appears to be a package

`is_valid_member()` accepts status `PROMO10D`, while other code treats `PROMO10D` as a package and `ACTIVE` as the status.

Required fix:
- Require status `ACTIVE` plus an allowed package.
- Require a non-expired date.

### MCH-008 — Expiring warning creates an unclosed HTTP client

The 3-day warning uses `await (httpx.AsyncClient()).post(...)` without a context manager.

Required fix:
- Reuse a scoped client or `async with`.

## Channel flow observations

Positive controls already present:
- Single-use invite links (`member_limit=1`).
- `/channel` can issue a replacement link for active members.
- Join guard checks the channel ID and ignores admins.
- Sweep removes non-active rows still present in the channel.
- Sheet outages fail safe for removal (`is_valid_member()` returns true), avoiding mass accidental kicks.

Remaining concerns:
- Access checks and removal checks need separate policies: customer access should fail closed; destructive kick decisions should fail safe.
- Bot must be channel administrator with invite and ban permissions.
- Telegram cannot force-add a user; the correct flow is a controlled invite/join request.

## Proposed implementation order

1. Add shared normalization/parsing helpers and unit tests.
2. Fix approval persistence gate (MCH-001).
3. Fix expiry-aware access checks (MCH-002/MCH-007).
4. Canonicalize package and promo save contracts (MCH-003/MCH-005).
5. Send password as a standalone plain-text message (MCH-006).
6. Add Apps Script schema-health/version endpoint (MCH-004).
7. Run live acceptance tests for Standard, Premium, renewal, expired, kicked and promo users.

## Release acceptance matrix

| Scenario | Expected Telegram | Expected Website | Expected Channel |
|---|---|---|---|
| New CH | Active, no web password | Denied | Invite allowed |
| New WEB | Active, password available | Allowed | Invite allowed |
| CH → WEB upgrade | Same member, expiry extended, password created/preserved by policy | Allowed | Existing membership preserved |
| WEB renewal | Same password unless reset requested | Allowed | Existing membership preserved |
| Expired | Renewal prompt | Denied | Removed |
| Kicked | Denied | Denied | Removed |
| PROMO10D active | Promo rules | Defined explicitly | Allowed only before expiry |
| Sheet unavailable | Clear temporary error | Denied | No automatic mass kick |
