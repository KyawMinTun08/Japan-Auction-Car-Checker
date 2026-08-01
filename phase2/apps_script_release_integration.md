# JACC Phase 2 Apps Script release integration

Status: staged only; do not deploy one component by itself.

## Evidence boundary

The uploaded `Tele Bot - Project editor - Apps Script` file is a browser MHTML
snapshot dated 14 July 2026. Its visible editor viewport exposes only the first
100 Code.gs lines and shows an older A–H member schema and an older public
`doGet` price-data flow. It is useful historical evidence, but it is not a safe
copy of the current deployed Apps Script source.

The live production `Members` Sheet was separately verified as the current A–J
schema:

`UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token, DeviceID`

Because the current deployed Code.gs body is not available as a complete source
file, this release uses additive `.gs` modules plus small reviewed insertion
points. Do not automatically replace the deployed Code.gs with the historical
MHTML snapshot.

## Add these four script files

Create four new Script files in the existing Apps Script project and paste the
corresponding repository contents:

1. `Phase2MembershipSecurity.gs`
   - source: `phase2/apps_script_membership_security_patch.gs`
2. `Phase2PaymentApproval.gs`
   - source: `phase2/apps_script_payment_approval_patch.gs`
3. `Phase2DeviceBinding.gs`
   - source: `phase2/apps_script_device_binding_patch.gs`
4. `Phase2Routes.gs`
   - source: `phase2/apps_script_release_routes.gs`

These files contain no production secret.

## Required Code.gs changes

### 1. doPost preflight and protected routes

Immediately after parsing `data`, before the existing legacy switch/cases:

```javascript
var data = JSON.parse(e.postData.contents);
var phase2 = jaccPhase2PreflightAndRoute_(data);
if (phase2.handled) return _json(phase2.response);
```

Leave all existing legacy cases below this insertion unchanged.

The existing outer ScriptLock may remain. The Phase 2 payment and device
functions detect an already-held lock and do not wait on the same lock again.

### 2. doGet membership preflight

Before routing any `e.parameter.action` membership request:

```javascript
var queryData = (e && e.parameter) ? e.parameter : {};
var membershipGuard = jaccMembershipPreflight_(queryData);
if (membershipGuard) return _json(membershipGuard);
```

Do not remove unrelated car/price-data behavior. This insertion protects the
legacy GET `getMembers` caller used by broadcast-photo mode.

### 3. verifyLogin must receive the request object

Change the route from a password-only call to the full request:

```javascript
case "verifyLogin":
  return _json(verifyLogin(data));
```

Inside `verifyLogin`, read the password from `data.password`. After password,
status, expiry, and package validation—but before token creation/return—call:

```javascript
var device = jaccEnforceDeviceBinding_(
  membersSheet,
  memberRowNumber,
  data,
  memberPackage
);
if (!device.ok) return device;
```

Use the authoritative Members sheet, exact 1-based row number, and package from
column H. Do not trust a package supplied by the browser.

### 4. verifyToken must receive the request object

Change the route to:

```javascript
case "verifyToken":
  return _json(verifyToken(data));
```

Inside `verifyToken`, read `data.token`. After locating and validating the token
owner, status, expiry, and package, run the same
`jaccEnforceDeviceBinding_(...)` call before returning success.

### 5. getData device enforcement

After locating the token owner and validating membership, but before returning
cars, run:

```javascript
var device = jaccEnforceDeviceBinding_(
  membersSheet,
  memberRowNumber,
  data,
  memberPackage
);
if (!device.ok) return device;
```

The client-supplied `userId` is diagnostic only. The token lookup must determine
the authoritative member row.

## Payment semantics in the staged patch

`approveMembershipPayment` no longer calls the legacy `saveMember()` function.
It writes one exact canonical A–J row to a ledger-owned target expiry.
Therefore:

- an active non-expired renewal extends from the current expiry;
- an expired/inactive membership starts a new period from today in
  `Asia/Bangkok`;
- a retry writes the same target expiry and cannot add a second period;
- WEB renewal preserves the current password unless Railway supplies a new one;
- CH → WEB requires Railway to supply the generated WEB password;
- token and DeviceID are preserved on renewal;
- Finance logging is deduplicated by the same idempotency key.

## Secret setup

Generate one new random high-entropy value outside GitHub.

- Apps Script Script Property: `JACC_SERVER_KEY`
- Railway environment variable: `SHEET_SERVER_KEY`

The values must match exactly. Never place the value in Code.gs, GitHub,
website JavaScript, Flutter assets, Telegram messages, logs, or Sheet cells.

## Atomic deployment order

1. Back up the current Apps Script project/version and Members sheet.
2. Add the four Phase 2 `.gs` files.
3. Make the five reviewed Code.gs insertion changes above.
4. Set `JACC_SERVER_KEY` in Apps Script properties.
5. Confirm Telegram bot has ban/restrict permission in the channel.
6. Set matching `SHEET_SERVER_KEY` in Railway without redeploying yet.
7. Deploy a new Apps Script version while keeping the existing Web App URL.
8. Deploy Railway with `phase2.install()` loaded before legacy handler
   registration.
9. Deploy the generated Phase 2 website in the same maintenance window.
10. Run the live acceptance matrix before marking PR #12 Ready.

Enabling only Apps Script, Railway, or website by itself can break membership
operations. Treat the release as one coordinated change.

## Pre-release acceptance matrix

- Schema health returns `JACC_MEMBERS_V2_AJ` and no mismatch.
- Standard/CH approval and renewal.
- New WEB approval.
- WEB renewal preserves password.
- CH → WEB upgrade creates one password.
- Expired member renewal.
- Previously kicked/banned member auto-unban and channel rejoin.
- Promo activation.
- Payment backend outage followed by retry.
- Duplicate admin approval tap does not extend twice.
- Same browser/PWA installation can log out and log in again.
- Second installation receives `device_mismatch`.
- Admin device reset allows one replacement installation to bind.
- Expired token/session is rejected at page startup.

## Rollback boundary

If any acceptance test fails, roll back Railway and website to the previous
release and redeploy the previous Apps Script version. Do not delete member,
ledger, Finance, or audit rows during rollback.
