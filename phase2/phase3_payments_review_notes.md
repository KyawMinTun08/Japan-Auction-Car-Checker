# Current Phase3Payments.gs review

Status: staged only. Production is unchanged.

## Confirmed risks in the owner-supplied source

1. `approveWebPayment` and `rejectWebPayment` run through the Phase 3 router
   before the legacy switch and had no server-key requirement.
2. The approval path called legacy `saveMember()` directly instead of the
   retry-safe membership ledger.
3. It generated a new WEB password before knowing whether the member already
   had one, risking password rotation during renewal.
4. It treated only the literal boolean `false` as a save failure even though
   `saveMember()` returns result objects.
5. It returned the raw WEB password in the approval API response.
6. Rejection could overwrite a previously approved payment because it did not
   require `PENDING` status.
7. Public payment status allowed a missing `userId`, exposing status metadata to
   anyone who knew or guessed a payment ID.
8. Payment IDs used a timestamp plus four random digits, making enumeration
   easier than a UUID-based identifier.
9. Public submission returned the private Drive slip URL and allowed duplicate
   pending submissions for the same user.
10. Admin-notification failure happened after the payment row and slip were
    created, but the request threw an error that could encourage a duplicate
    resubmission.
11. Telegram buttons used `webpay_approve_...` / `webpay_reject_...`, but the
    reviewed Railway bot files had no handler for those callback prefixes.

## Staged correction

- `apply_apps_script_phase3_payments_gs.py` replaces only the four reviewed
  Phase 3 entry functions with delegates and refuses unknown source drift.
- `apps_script_phase3_payment_patch.gs` owns validated submission, owner-bound
  status lookup, and retry-safe approval/rejection.
- Admin approve/reject actions are included in both the Apps Script preflight
  and Railway scoped server-key proxy.
- Payment IDs are UUID-derived.
- Package, month count, amount, payment method, MIME type, and slip size are
  bounded before the Drive write.
- One existing `PENDING` request per Telegram user is returned as an idempotent
  duplicate instead of creating another row/slip.
- Public submission and status responses exclude slip URLs, Telegram usernames,
  admin IDs/notes, and passwords.
- Status lookup requires both payment ID and matching Telegram user ID; a
  mismatch returns the same `PAYMENT_NOT_FOUND` response.
- Approval derives one stable ledger key from the Phase 3 payment ID and calls
  `jaccApproveMembershipPayment_()`.
- Existing WEB renewal preserves the current password. New WEB and CH-to-WEB
  activations generate one password.
- Membership activation must succeed before the payment row is marked
  `APPROVED` or the customer success message is sent.
- Activation failure leaves the payment `PENDING`, records the error, and keeps
  the approval button retryable.
- Rejection is allowed only from `PENDING`; it cannot overwrite `APPROVED`.
- Public/admin API responses never return the raw WEB password.
- The existing Phase 2 Telegram callback wrapper now handles
  `webpay_approve_...` and `webpay_reject_...`, verifies the admin, calls the
  authenticated Apps Script action, keeps buttons on failure, and removes them
  only after authoritative success.

## Evidence

- The exact current source was successfully transformed locally.
- The generated candidate parses successfully as JavaScript.
- Phase 1/Phase 2 CI run #250 passed all callback, security, transformer,
  payment-retry, device-binding, channel, and recovery tests.

## Remaining live checks

- Confirm the admin callback messages are received by the same Railway bot that
  has the Phase 2 wrapper installed.
- Confirm `SHEET_SERVER_KEY` and `JACC_SERVER_KEY` match during the atomic
  rollout.
- Test submit, status, approve, reject, duplicate approve, activation failure,
  admin-notification failure, and customer-DM failure with synthetic rows.
- Keep PR #12 Draft until the complete atomic acceptance matrix passes and the
  owner gives explicit merge approval.
