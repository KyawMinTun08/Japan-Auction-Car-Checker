# JACC Phase 2 Apps Script release integration

Status: staged only. Do not deploy one component by itself.

## Current source evidence

The owner supplied the current `Code.gs` and `Payment.gs` sources on 1 August
2026.

Current `Code.gs`:

- uses the canonical A–J Members contract;
- keeps `doGet(e)` as the public price-data endpoint;
- parses POST JSON under one outer `ScriptLock`;
- calls `handlePhase3PaymentAction_(data)` before the legacy switch;
- still uses raw Flutter-only DeviceID binding;
- omits device data inside the protected `getData` path;
- contains `monthlyPasswordReset()`.

Current `Payment.gs`:

- stores payment rows in the 11-column payment sheet;
- writes `APPROVED` before calling `activateMemberFromPayment()`;
- blocks every retry after that status write, even when activation failed;
- sends the customer an approval message without checking activation success;
- exposes Telegram ID, slip URL, and admin note through public `checkPayment`;
- routes `approvePayment` and `rejectPayment` without a server-key requirement.

The owner-supplied production sources are evidence only and are not committed to
the public repository.

## Add these Apps Script files

Create these files in the existing Apps Script project:

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
6. `Phase2TriggerGuard.gs`
   - `phase2/apps_script_trigger_guard.gs`

None of these files contains the production server key.

## Generate the reviewed Code.gs candidate

```bash
python phase2/apply_apps_script_code_gs.py Current_Code.gs \
  --output Code_Phase2_Candidate.gs
python phase2/apply_apps_script_code_gs.py Code_Phase2_Candidate.gs --check
```

The guarded transformer changes only the reviewed integration points:

- runs Phase 2 preflight before `handlePhase3PaymentAction_`;
- replaces raw Flutter-only binding with hashed one-installation binding;
- moves token device enforcement after package/status/expiry checks;
- passes device data through `getData`;
- preserves authoritative token/device errors.

The public price-data `doGet(e)` remains unchanged.

## Generate the reviewed Payment.gs candidate

```bash
python phase2/apply_apps_script_payment_gs.py Current_Payment.gs \
  --output Payment_Phase2_Candidate.gs
python phase2/apply_apps_script_payment_gs.py \
  Payment_Phase2_Candidate.gs --check
```

The guarded transformer performs two changes:

1. `jaccReviewPayment_()` delegates to the Phase 2 website-payment adapter.
2. Public `checkPayment()` no longer returns Telegram ID, slip URL, or admin
   note.

It refuses unknown source drift and is idempotent.

## Website-payment approval semantics

The Phase 2 adapter uses the payment ID to derive a stable
`JACC-PAY-<32 hex>` idempotency key and calls the existing atomic
`jaccApproveMembershipPayment_()` ledger flow.

Approval order is now:

1. Validate payment and registration rows.
2. Run retry-safe membership activation.
3. Verify authoritative backend success.
4. Write payment and registration status `APPROVED`.
5. Send the customer approval message.

When activation fails:

- the payment remains `PENDING`;
- the failure is written to the admin-note cell;
- no approval message is sent;
- the admin can retry;
- the membership ledger prevents a partial write from extending twice.

A completed `APPROVED` payment returns an idempotent duplicate success rather
than applying another membership period.

The current website-payment contract still represents one month as 30 days,
matching the existing `activateMemberFromPayment()` default. Changing package
duration requires a separate schema/frontend change and is not inferred here.

WEB password rules:

- existing WEB renewal keeps its current password;
- new WEB or CH-to-WEB activation generates one password;
- the public approval response excludes the password.

## Protected payment review routes

`approvePayment` and `rejectPayment` are privileged server actions and require
the same server key as other membership administration routes.

`submitPayment` and the redacted `checkPayment` remain public for the customer
website flow.

The Railway scoped proxy adds `SHEET_SERVER_KEY` only to configured protected
Sheet requests. It never puts the key in URL parameters.

## Legacy broadcast compatibility

A historical Telegram handler sends `GET ?action=getMembers`. Railway converts
only this protected request to authenticated POST JSON before network access.
The Apps Script public price-data `doGet` contract is unchanged.

## Monthly password reset

The current Code.gs contains `monthlyPasswordReset()`, which changes every
active WEB password and clears tokens. Before rollout:

1. Run `jaccPhase2TriggerHealth_()` from the Apps Script editor.
2. Keep the trigger only after an explicit policy decision.
3. Otherwise run `jaccDisableMonthlyPasswordResetTriggers_()`.
4. Re-run the audit and confirm zero matching triggers.

The trigger guard touches only triggers whose handler is exactly
`monthlyPasswordReset`; it does not read or modify member rows.

## Secret setup

Generate one new high-entropy value outside GitHub.

- Apps Script Script Property: `JACC_SERVER_KEY`
- Railway environment variable: `SHEET_SERVER_KEY`

The values must match exactly. Never place the value in code, GitHub, website
JavaScript, Flutter assets, Telegram messages, logs, URLs, or Sheet cells.

## Remaining source review

Before declaring the Apps Script project release-ready, export and review:

- `Registration.gs`;
- every file defining `handlePhase3PaymentAction_`;
- any separate Telegram callback handler that calls `approvePayment` or
  `rejectPayment`.

The supplied `Payment.gs` defines submit/check/approve/reject functions but does
not define `handlePhase3PaymentAction_`.

## Atomic deployment order

1. Export/backup every Apps Script file and the Members sheet.
2. Review the remaining Registration/Phase 3 router files.
3. Add the six Phase 2 `.gs` modules.
4. Generate and review Code.gs and Payment.gs candidates.
5. Audit/disable the monthly password reset trigger as decided.
6. Set `JACC_SERVER_KEY` in Apps Script properties.
7. Confirm Telegram bot ban/unban permission.
8. Set matching `SHEET_SERVER_KEY` in Railway without deploying yet.
9. Import and run `phase2.install()` before legacy handler registration.
10. Deploy Apps Script, Railway, and Phase 2 website in one maintenance window.
11. Run the acceptance matrix before marking PR #12 Ready.

Deploying only one component can break membership operations.

## Acceptance matrix

- Schema health returns `JACC_MEMBERS_V2_AJ`.
- Public price-data `doGet` still returns cars.
- Standard approval and renewal.
- New WEB approval.
- WEB renewal preserves password.
- CH-to-WEB upgrade generates one password.
- Expired renewal.
- Previously kicked/banned member auto-rejoins.
- Promo activation.
- Website payment activation failure remains PENDING and retryable.
- Retry after partial member write does not extend twice.
- Duplicate website payment approval does not extend twice.
- Approval message is sent only after activation succeeds.
- Public `checkPayment` excludes Telegram ID, slip URL, and admin note.
- Unauthorized `approvePayment` and `rejectPayment` are rejected.
- Same installation can log out and log in again.
- Second installation receives `device_mismatch`.
- Admin device reset allows one replacement installation.
- Expired token/session is rejected at startup.
- Monthly password reset trigger state matches the chosen policy.

## Rollback boundary

On any failed acceptance test, roll back Railway and website to the previous
release and redeploy the previous Apps Script version. Do not delete member,
ledger, Finance, payment, registration, or audit rows during rollback.
