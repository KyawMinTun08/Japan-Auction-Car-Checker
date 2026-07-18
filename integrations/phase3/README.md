# JACC Phase 3 — Website Payment Integration

Flow: Website → Apps Script → Google Drive + PaymentRequests Sheet → Telegram Admin → Approve/Reject → Members Sheet + customer Telegram message.

## Apps Script
1. Add `Phase3Payments.gs` to the existing Apps Script project.
2. In the current `doPost(e)`, after parsing the JSON body, add:

```javascript
var phase3 = handlePhase3PaymentAction_(body);
if (phase3) return jsonOutput(phase3);
```

3. Add Script Properties: `BOT_TOKEN`, `ADMIN_CHAT_ID`, `PAYMENT_DRIVE_FOLDER_ID`.
4. Deploy a new Web App version.

## Railway Telegram bot
Merge `phase3_bot_patch.py` into the current `bot.py`, call the helper near the top of `button_callback()`, and redeploy Railway.

## Website request
POST to the existing Apps Script Web App URL with action `submitWebPayment` and fields:

- `userId`
- `username`
- `package`
- `months`
- `amount`
- `method`
- `slipBase64`
- `mimeType`

The response returns `paymentId` and `PENDING`. Use `getWebPaymentStatus` to refresh status.
