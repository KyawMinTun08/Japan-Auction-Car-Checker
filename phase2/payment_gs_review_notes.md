# Current Payment.gs review

Status: staged only. Production is unchanged.

## Confirmed risks in the owner-supplied current source

1. `approvePayment` and `rejectPayment` are reachable from the public `doPost`
   switch and therefore require the Phase 2 server-key preflight.
2. The legacy reviewer writes `APPROVED` before member activation. An activation
   error can leave a payment permanently approved while the member is inactive.
3. Once that premature status is written, another approval attempt returns
   `PAYMENT_ALREADY_REVIEWED`, so the failure cannot be repaired through the
   normal flow.
4. The legacy customer success message is sent without requiring authoritative
   member activation success.
5. Public `checkPayment` returns Telegram ID, private slip URL and admin note.

## Staged correction

- `apply_apps_script_payment_gs.py` redacts the public status response and makes
  `jaccReviewPayment_` delegate to `jaccReviewWebsitePayment_`.
- `apps_script_website_payment_patch.gs` derives one stable idempotency key from
  the payment ID and uses `jaccApproveMembershipPayment_`.
- Membership activation completes before Registration and Payment are finalized.
- An activation failure leaves Payment and Registration retryable as PENDING.
- Payment `APPROVED` is the final completion marker.
- Duplicate approval repairs Registration state without extending membership.
- Existing WEB renewal preserves its password; CH to WEB creates one password.
- Public approval results never include the WEB password.
- `approvePayment` and `rejectPayment` are included in the server-key protected
  Apps Script action list. Customer submit/check routes remain public and
  redacted.

## Remaining dependency

Review the complete `Phase3Payments.gs` source that defines
`handlePhase3PaymentAction_` and any Telegram callback routing. That router runs
before the legacy switch and must not bypass the server-key preflight or create
a second approval path.
