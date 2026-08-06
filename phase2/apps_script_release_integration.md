# JACC Phase 2 Apps Script release integration

Status: staged only. Do not deploy one component by itself.

## Reviewed current sources

The owner supplied current copies of:

- `Code.gs`
- `Payment.gs`
- `Registration.gs`
- `Phase3Payments.gs`

The production source copies are evidence only and are not committed to the
public repository.

### Current Code.gs

- Uses the canonical A–J Members contract.
- Keeps `doGet(e)` as public price data.
- Parses POST JSON under one outer ScriptLock.
- Calls `handlePhase3PaymentAction_(data)` before the legacy switch.
- Uses historical raw Flutter-only device binding.
- Omits device data inside `getData`.
- Contains `monthlyPasswordReset()`.

### Current Payment.gs

- Writes `APPROVED` before member activation.
- Prevents safe retry after partial failure.
- Sends customer success before requiring authoritative activation success.
- Exposes Telegram ID, slip URL, and admin note through public status.
- Leaves approve/reject routes unprotected.

### Current Registration.gs

- Reacquires ScriptLock under the outer router lock.
- Blocks renewal after a completed registration.
- Omits `WEB_PROMO` normalization.
- Exposes Telegram and package identifiers in public/conflict responses.

### Current Phase3Payments.gs

- Routes `approveWebPayment` / `rejectWebPayment` before the legacy switch
  without server authentication.
- Calls legacy `saveMember()` directly.
- Can rotate an existing WEB password during renewal.
- Treats only literal boolean `false` as a save failure although saveMember
  returns result objects.
- Returns the raw password in the approval response.
- Allows rejection to overwrite a completed approval.
- Allows status lookup without requiring the owning user ID.
- Returns the Drive slip URL from public submission.
- Uses timestamp-plus-four-digit payment IDs.
- Creates duplicate pending requests after admin-notification failures.
- Creates Telegram callback data that had no reviewed Railway handler.

## Add these seven Apps Script modules

1. `Phase2MembershipSecurity.gs`
   - `phase2/apps_script_membership_security_patch.gs`
2. `Phase2PaymentApproval.gs`
   - `phase2/apps_script_payment_approval_patch.gs`
3. `Phase2DeviceBinding.gs`
   - `phase2/apps_script_device_binding_patch.gs`
4. `Phase2Routes.gs`
   - `phase2/apps_script_release_routes.gs`
5. `Phase2WebsitePayment.gs`
   - `phase2/apps_script_website_payment_patch.gs`
6. `Phase2Phase3Payment.gs`
   - `phase2/apps_script_phase3_payment_patch.gs`
7. `Phase2TriggerGuard.gs`
   - `phase2/apps_script_trigger_guard.gs`

None contains a production secret.

## Generate reviewed candidates

### Code.gs

```bash
python phase2/apply_apps_script_code_gs.py Current_Code.gs \
  --output Code_Phase2_Candidate.gs
python phase2/apply_apps_script_code_gs.py Code_Phase2_Candidate.gs --check
```

Changes:

- Runs Phase 2 preflight before `handlePhase3PaymentAction_`.
- Replaces raw Flutter-only binding with hashed installation binding.
- Enforces token device binding after package/status/expiry validation.
- Passes device data through `getData` and preserves authoritative errors.
- Leaves public price-data `doGet` unchanged.

### Payment.gs

```bash
python phase2/apply_apps_script_payment_gs.py Current_Payment.gs \
  --output Payment_Phase2_Candidate.gs
python phase2/apply_apps_script_payment_gs.py \
  Payment_Phase2_Candidate.gs --check
```

Changes:

- Delegates `jaccReviewPayment_()` to the retry-safe website-payment adapter.
- Redacts Telegram ID, slip URL, and admin note from public `checkPayment`.

### Registration.gs

```bash
python phase2/apply_apps_script_registration_gs.py Current_Registration.gs \
  --output Registration_Phase2_Candidate.gs
python phase2/apply_apps_script_registration_gs.py \
  Registration_Phase2_Candidate.gs --check
```

Changes:

- Reuses the outer ScriptLock and releases only a lock acquired locally.
- Allows prior completed registrations during renewal.
- Continues blocking another open registration for the same Telegram user.
- Supports `WEB_PROMO` while storing canonical `WEB_PREMIUM`.
- Redacts public registration/conflict identifiers.

`repairRegistrationPackages` remains editor-only and must never be routed by
`doPost`.

### Phase3Payments.gs

```bash
python phase2/apply_apps_script_phase3_payments_gs.py \
  Current_Phase3Payments.gs \
  --output Phase3Payments_Phase2_Candidate.gs
python phase2/apply_apps_script_phase3_payments_gs.py \
  Phase3Payments_Phase2_Candidate.gs --check
```

The transformer replaces only these four reviewed functions with delegates:

- `submitWebPayment_`
- `getWebPaymentStatus_`
- `approveWebPayment_`
- `rejectWebPayment_`

It leaves the existing Sheet, Drive, Telegram, and router helpers intact,
refuses unknown source drift, and is idempotent.

The exact owner-supplied Phase3Payments source was transformed locally and the
candidate parsed successfully as JavaScript.

## Payment approval semantics

Both website payment systems now use the same atomic
`Membership_Approval_Ledger` flow.

Approval order:

1. Validate payment row and package/duration.
2. Derive a stable payment-specific idempotency key.
3. Run retry-safe membership activation.
4. Verify authoritative expiry/package/password from the Members row.
5. Write related registration state when applicable.
6. Write payment `APPROVED` as the final completion marker.
7. Send the customer success message.

Failure behavior:

- Payment remains `PENDING` when activation fails.
- Error detail is recorded for admin diagnosis.
- Approval buttons remain available for safe retry.
- Partial member writes recover through the same ledger key.
- Duplicate approval cannot extend membership twice.

WEB password rules:

- Existing WEB renewal preserves its current password.
- New WEB and CH-to-WEB activation generate one password.
- Customer delivery may include the password after authoritative success.
- Admin/API success responses never contain the raw password.

## Phase 3 public submission/status hardening

- Telegram user ID must be numeric.
- Package is canonical CH/WEB only.
- Months must be an integer from 1 to 12.
- Amount must be positive and bounded.
- Payment method is allow-listed.
- Slip MIME type is JPEG, PNG, or WebP.
- Estimated slip size is limited to 5 MB.
- Payment IDs are UUID-derived.
- One existing PENDING request per user is returned as a duplicate.
- Admin-notification failure is recorded without telling the customer to
  resubmit and create another row.
- Public submission does not return the private Drive slip URL.
- Public status requires payment ID plus matching user ID.
- Owner mismatch returns `PAYMENT_NOT_FOUND`.
- Public status excludes usernames, slip URL, admin ID/note, and password.
- Rejection is allowed only from PENDING and cannot overwrite APPROVED.

## Protected routes and Telegram callbacks

The following actions require the matching server key:

- `approveMembershipPayment`
- `approvePayment`
- `rejectPayment`
- `approveWebPayment`
- `rejectWebPayment`
- all other privileged membership administration actions already listed in the
  security preflight.

Customer submission/status actions remain public but validated and redacted.

Railway's Phase 2 callback wrapper now intercepts:

- `slip_ok_...`
- `webpay_approve_...`
- `webpay_reject_...`

The wrapper:

- verifies the Telegram admin before any backend request;
- calls Apps Script through `_post_privileged_sheet`;
- keeps buttons when backend/activation fails;
- removes buttons only after authoritative success;
- reports duplicate approval without extending again;
- never prints the raw WEB password in the admin chat.

Every unrelated callback delegates to the original handler.

## Legacy broadcast compatibility

One historical Telegram handler sends `GET ?action=getMembers`. Railway converts
only this protected request to authenticated POST JSON before network access.
The Apps Script public price-data `doGet` remains unchanged and the server key
never appears in URL parameters.

## Monthly password reset

The current Code.gs contains `monthlyPasswordReset()`, which changes active WEB
passwords and clears tokens. Before rollout:

1. Run `jaccPhase2TriggerHealth_()` in the Apps Script editor.
2. Keep the trigger only after an explicit owner policy decision.
3. Otherwise run `jaccDisableMonthlyPasswordResetTriggers_()`.
4. Re-run health and confirm zero matching triggers.

The helper touches only triggers whose handler is exactly
`monthlyPasswordReset`; it does not read or change Members rows.

## Secret setup

Generate one new high-entropy value outside GitHub.

- Apps Script Script Property: `JACC_SERVER_KEY`
- Railway environment variable: `SHEET_SERVER_KEY`

Values must match exactly. Never place the value in source code, GitHub,
website/Flutter assets, Telegram messages, logs, URLs, or Sheet cells.

## Atomic deployment order

1. Export/backup every current Apps Script file/version and Members sheet.
2. Generate and review all four candidate files.
3. Add the seven Phase 2 Apps Script modules.
4. Audit/disable the monthly password reset trigger as decided.
5. Set `JACC_SERVER_KEY` in Apps Script properties.
6. Confirm the Telegram bot has channel ban/unban permission.
7. Set matching `SHEET_SERVER_KEY` in Railway without deploying yet.
8. Import/run `phase2.install()` before legacy Telegram handler registration.
9. Deploy Apps Script, Railway, and generated website in one maintenance window.
10. Run the complete acceptance matrix.
11. Request explicit owner approval before Ready/Merge.

Deploying only one component can break membership operations.

## Acceptance matrix

- A–J schema health passes.
- Public price-data `doGet` still returns cars.
- Standard approval/renewal.
- New WEB approval.
- WEB renewal preserves password.
- CH-to-WEB generates one password.
- Expired renewal.
- Previously kicked/banned member auto-rejoins.
- Promo activation.
- Registration renewal after completed registration.
- Another open registration remains blocked.
- Public registration responses stay redacted.
- Payment/Phase 3 activation failure remains PENDING.
- Retry after partial write does not extend twice.
- Duplicate approval does not extend twice.
- Rejection cannot overwrite approval.
- Approval message occurs only after activation succeeds.
- Public payment status requires the owner and stays redacted.
- Oversized/invalid slip is rejected before Drive write.
- Duplicate pending submission returns the existing payment.
- Admin-notification failure does not create a duplicate row on retry.
- Unauthorized approve/reject actions are rejected.
- Telegram `webpay_approve_` and `webpay_reject_` buttons reach Railway wrapper.
- Backend failure keeps callback buttons.
- Same installation can log out/in again.
- Second installation receives `device_mismatch`.
- Admin reset allows a replacement installation.
- Expired token/session is rejected at startup.
- Monthly password reset trigger state matches policy.

## Rollback boundary

On any failed live acceptance test, roll back Railway and website to the previous
release and redeploy the previous Apps Script version. Do not delete member,
ledger, Finance, payment, registration, trigger-audit, or audit rows during
rollback.
