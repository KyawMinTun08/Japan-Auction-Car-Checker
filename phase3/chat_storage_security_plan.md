# Phase 3 — Private Chat Storage & Upload Security Plan

Status: REVIEW/STAGING ONLY

This task keeps all attachment controls disabled while the private Storage contract is designed and tested.

## Bucket contract
- Bucket: `jacc-chat-attachments`
- Private only; no public bucket and no public object URLs.
- Browser/client stores only private object paths in chat metadata.
- Maximum object size aligned to chat schema: 5 MB.
- Initial allowlist: `image/jpeg`, `image/png`, `image/webp`.
- Voice/document types remain disabled until an explicit later review expands the allowlist.

## Object path contract
Use a path bound to chat identity:

`<conversation_id>/<message_id>/<object_uuid>.<ext>`

The first path segment must match the message conversation. The second path segment must match the message id. Client-generated names outside that conversation/message pair must be denied.

## Authorization model
Read:
- active entitled conversation participant; or
- admin/lead-broker oversight.

Insert:
- authenticated sender owns the referenced app message;
- sender is entitled to send to that conversation;
- object path conversation/message matches the message row;
- bucket is exactly `jacc-chat-attachments`.

Update/delete:
- deny browser mutation by default in v1;
- trusted server/service role handles moderation, rejection and cleanup.

Anonymous access is always denied.

## Required negative tests
- expired customer upload denied
- suspended broker upload denied
- cross-conversation path denied
- cross-message path denied
- public URL metadata denied
- wrong bucket denied
- anonymous read/upload denied
- client cannot overwrite or delete another participant's object

## Release gate
1. Add review-only Storage policy migration.
2. Build a disposable `storage.objects`/bucket staging contract.
3. Run positive and negative RLS/upload tests.
4. Confirm production paths and services are untouched.
5. Keep `phase3/chat-preview.html` attachment controls disabled until all Storage tests pass.
6. Only a later task may wire photo upload into the client/UI.

No production Supabase Storage, database, Railway, Apps Script, Telegram proxy or website deployment is changed by this plan.
