# JACC Phase 2 Apps Script release integration

Status: staged only; do not deploy one component by itself.

## Current source evidence

The owner supplied the current `Code.gs` source on 1 August 2026. The file:

- uses the canonical A–J Members contract:
  `UserID, Username, StartDate, ExpireDate, Status, CancelCount, Password, Package, Token, DeviceID`;
- keeps `doGet(e)` as the public price-data endpoint;
- parses POST JSON under one outer `ScriptLock`;
- calls `handlePhase3PaymentAction_(data)` before the legacy action switch;
- already passes `(password, deviceId, app)` to `verifyLogin` and
  `(token, deviceId, app)` to `verifyToken`;
- still stores raw DeviceID values only for Flutter requests;
- calls `verifyToken(data.token)` without device data inside `getData`;
- includes a separate `activateMemberFromPayment()` hook and references
  `Payment.gs` / `Registration.gs` functions that were not included in the
  uploaded file.

The full source parses successfully as JavaScript. The Phase 2 transformer is
therefore based on exact reviewed anchors from this current source rather than
on the older browser MHTML snapshot.

The uploaded source is evidence only and is not committed to the public
repository.

## Add these five Apps Script files

Create five new Script files in the existing Apps Script project and paste the
corresponding repository contents:

1. `Phase2MembershipSecurity.gs`
   - source: `phase2/apps_script_membership_security_patch.gs`
2. `Phase2PaymentApproval.gs`
   - source: `phase2/apps_script_payment_approval_patch.gs`
3. `Phase2DeviceBinding.gs`
   - source: `phase2/apps_script_device_binding_patch.gs`
4. `Phase2Routes.gs`
   - source: `phase2/apps_script_release_routes.gs`
5. `Phase2TriggerGuard.gs`
   - source: `phase2/apps_script_trigger_guard.gs`

These files contain no production secret.

## Generate the reviewed Code.gs candidate

Run the guarded transformer against the newly exported current source:

```bash
python phase2/apply_apps_script_code_gs.py Current_Code.gs \
  --output Code_Phase2_Candidate.gs
```

The transformer refuses unknown drift and changes only five reviewed
integration points:

1. inserts `jaccPhase2PreflightAndRoute_(data)` after POST JSON parsing and
   before `handlePhase3PaymentAction_(data)`;
2. replaces the raw Flutter-only binding call in `verifyLogin`;
3. removes the early raw binding call in `verifyToken`;
4. enforces the hashed device binding only after package/status/expiry checks;
5. passes `deviceId` and `app` through `getData` and returns the authoritative
   token/device error instead of collapsing every failure to `invalid_token`.

Validation command:

```bash
python phase2/apply_apps_script_code_gs.py Code_Phase2_Candidate.gs --check
```

The current public `doGet(e)` price-data flow must remain unchanged.

## Legacy broadcast GET compatibility

One legacy Telegram broadcast handler calls:

```text
GET SHEET_WEBHOOK?action=getMembers
```

The current Apps Script `doGet(e)` does not route membership actions. Phase 2
therefore converts only that protected request inside Railway to authenticated
POST JSON before network access.

Benefits:

- no Apps Script doGet redesign;
- no server key in a URL or query log;
- current price-data clients remain unchanged;
- all protected membership actions pass through the same POST preflight.

## Exact current Code.gs integration behavior

### doPost order

The Phase 2 adapter must run before the existing Phase 3 payment router:

```javascript
var data = JSON.parse(e.postData.contents);
var payload = data;
var phase2 = jaccPhase2PreflightAndRoute_(data);
if (phase2.handled) return _json(phase2.response);
var phase3 = handlePhase3PaymentAction_(data);
```

The existing outer ScriptLock remains. Phase 2 payment/device helpers reuse an
already-held lock and acquire/release one only when called outside that router.

### verifyLogin

The existing function signature remains:

```javascript
verifyLogin(password, deviceId, app)
```

After password, package, status and expiry validation, the candidate calls:

```javascript
var deviceCheck = jaccEnforceDeviceBinding_(
  sheet,
  i + 1,
  {deviceId: deviceId, app: app},
  memberPackage
);
if (!deviceCheck.ok) return deviceCheck;
```

### verifyToken

The existing function signature remains:

```javascript
verifyToken(token, deviceId, app)
```

The raw historical binding call is removed from the start of the token path.
Hashed binding runs only after the token owner, package, status and expiry are
validated.

### getData

The current generic error conversion is replaced with:

```javascript
var tokenResult = verifyToken(data.token, data.deviceId, data.app);
if (tokenResult.status !== 'ok') return _json(tokenResult);
```

This allows the website to distinguish `device_mismatch`, `expired`,
`web_access_required` and `invalid_token`.

## Payment semantics in the staged patch

`approveMembershipPayment` does not call the legacy `saveMember()` function. It
writes one exact canonical A–J row to a ledger-owned target expiry.

Therefore:

- an active non-expired renewal extends from the current expiry;
- an expired/inactive membership starts a new period from today in
  `Asia/Bangkok`;
- a retry writes the same target expiry and cannot add a second period;
- WEB renewal preserves the current password unless Railway supplies a new one;
- CH → WEB requires Railway to supply the generated WEB password;
- token and DeviceID are preserved on renewal;
- Finance logging is deduplicated by the same idempotency key.

The existing `activateMemberFromPayment()` / `approvePayment()` path belongs to
the separate website registration/payment system. Its defining `Payment.gs`
and `Registration.gs` sources still need review before the full Apps Script
project can be declared release-ready.

## Monthly password reset trigger policy

The current Code.gs contains `monthlyPasswordReset()`, which changes every
active WEB member password and clears the token. That conflicts with the Phase 2
password-preserving renewal policy and can unexpectedly lock members out.

The additive `Phase2TriggerGuard.gs` file provides two manual editor functions:

1. Run `jaccPhase2TriggerHealth_()` and confirm whether an exact
   `monthlyPasswordReset` trigger exists.
2. When the result is unsafe, run
   `jaccDisableMonthlyPasswordResetTriggers_()` once.
3. Run `jaccPhase2TriggerHealth_()` again and require:
   - `safe: true`
   - `monthlyPasswordResetTriggerCount: 0`

The disable helper deletes only triggers whose handler is exactly
`monthlyPasswordReset`. It does not read or modify Members rows and leaves every
unrelated trigger untouched.

Do not delete the legacy function during the rollout. Removing only its trigger
keeps rollback simple while preventing unexpected password rotation.

## Secret setup

Generate one new random high-entropy value outside GitHub.

- Apps Script Script Property: `JACC_SERVER_KEY`
- Railway environment variable: `SHEET_SERVER_KEY`

The values must match exactly. Never place the value in Code.gs, GitHub,
website JavaScript, Flutter assets, Telegram messages, logs, URL query
parameters or Sheet cells.

## Atomic deployment order

1. Export/backup every current Apps Script file and the Members sheet.
2. Review the current `Payment.gs`, `Registration.gs`, and any file defining
   `handlePhase3PaymentAction_`.
3. Add the five Phase 2 `.gs` files.
4. Generate and review `Code_Phase2_Candidate.gs`.
5. Run `jaccPhase2TriggerHealth_()` and disable the exact legacy monthly reset
   trigger when present; require a safe follow-up result.
6. Set `JACC_SERVER_KEY` in Apps Script properties.
7. Confirm Telegram bot has ban/restrict permission in the channel.
8. Set matching `SHEET_SERVER_KEY` in Railway without deploying yet.
9. Import and run `phase2.install()` before legacy handler registration.
10. Deploy Apps Script, Railway, and the generated Phase 2 website in one
    maintenance window.
11. Run the live acceptance matrix before marking PR #12 Ready.

Enabling only Apps Script, Railway, or website by itself can break membership
operations. Treat the release as one coordinated change.

## Pre-release acceptance matrix

- Schema health returns `JACC_MEMBERS_V2_AJ` and no mismatch.
- Public price-data doGet still returns car data.
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
- Existing website registration/payment approval still behaves correctly.
- Trigger health reports `safe: true` and zero monthly reset triggers.

## Rollback boundary

If any acceptance test fails, roll back Railway and website to the previous
release and redeploy the previous Apps Script version. Do not delete member,
ledger, Finance, payment, registration or audit rows during rollback.
