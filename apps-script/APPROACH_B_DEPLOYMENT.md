# JACC Approach B Deployment Runbook

## Scope

Approach B adds server-side device binding without changing Members columns A–I. The new executable file is `device-bindings.gs`; the old `device-security-patch.gs` is now a non-executable archive.

## Required Apps Script files

Copy `Code.gs` and `apps-script/device-bindings.gs` into the same Apps Script project. Do not copy the old J-column patch as executable code. The Apps Script project must contain only one definition of `resetMemberDevice`, `_normalizeDeviceId_`, or other device-binding helpers.

## Required Script Properties

Set the following properties before switching enforcement on:

| Property | Required value |
|---|---|
| `JACC_DEVICE_HASH_SECRET` | A new high-entropy random secret, at least 32 random bytes. It must not be placed in GitHub or sent to the browser. |
| `JACC_DEVICE_BINDING_MODE` | `log` for an observation period, then `enforce` after client and reset tests pass. |
| `JACC_SERVER_KEY` | Keep the existing value. Railway `SHEET_SERVER_KEY` must match it for the admin reset action. |

`JACC_DEVICE_HASH_SECRET` should not be changed after production bindings exist. If it is rotated, all existing device hashes become unusable and every member must bind again.

## Sheets created automatically

On first authenticated request, the backend creates these sheets if they do not exist:

`DeviceBindings` has `UserID`, `DeviceHash`, `ClientApp`, `BoundAt`, `LastSeenAt`, `Status`, `ResetCount`, and `ResetAt`.

`AuthSessions` has `SessionHash`, `UserID`, `DeviceHash`, `ClientApp`, `IssuedAt`, `ExpiresAt`, `Status`, `RevokedAt`, and `LastSeenAt`.

Do not add `DeviceID` to Members. Do not change the order or meaning of Members A–I.

## Activation order

First deploy `Code.gs` and `device-bindings.gs` as a new Apps Script version. Set the mode to `log`, publish the web app deployment to the existing URL, and test a controlled Premium account from Website, PWA, and Flutter. In `log` mode, missing or mismatched device state is recorded/updated without blocking, but the new sheets and session records are exercised.

Next confirm that the Website sends `deviceId` and `app`, that Flutter sends a `JACC-` installation ID, that payment/JDM requests carry the same device context, and that `/resetdevice UserID` returns `Device Reset Complete` only for an admin. After those checks, change `JACC_DEVICE_BINDING_MODE` to `enforce`, redeploy, and test the mismatch cases.

## Enforce-mode acceptance checks

A first successful Premium login creates one DeviceBindings row and one AuthSessions row. A same-installation logout/login succeeds. A different browser or phone using the same password returns `device_mismatch`. A different device using an old token returns `device_mismatch` or `invalid_token` and receives no car data. A missing device ID returns `device_required`. An admin reset marks the binding `RESET`, revokes the member's sessions, and permits the next device to bind. A non-admin reset request returns `unauthorized`.

## Rollback

If a production issue appears, change `JACC_DEVICE_BINDING_MODE` to `log` first. This keeps existing clients usable while preserving logs and session records. If the Apps Script deployment itself must be rolled back, restore the prior Apps Script version and keep the GitHub branch unmerged. Do not delete DeviceBindings or AuthSessions during rollback; they are needed for investigation.

## Security notes

The backend stores hashes rather than raw installation IDs or session tokens in the new sheets. IP addresses are not device keys. Device reset remains an authenticated server-key action exposed only through the admin Telegram command. The browser installation ID is a clearable browser/PWA installation identifier, not a guaranteed physical-device identity.
