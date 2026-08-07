# Phase 3 — Chat Attachment Client Integration

Status: REVIEW/STAGING ONLY

This task begins only after Issue #31 Storage RLS acceptance passed.

## Contract

- Bucket: `jacc-chat-attachments`
- Accepted MIME: `image/jpeg`, `image/png`, `image/webp`
- Client max size: 5 MiB (5,242,880 bytes)
- Object path: `<conversation_uuid>/<message_uuid>/<safe_object_name>.<ext>`
- Message must exist before upload so the Storage policy can verify sender ownership.
- Store private object path + MIME + size + dimensions/metadata only.
- Never store or expose a permanent public URL.

## Review-only client flow

1. User selects one image in chat preview.
2. Validate type and size locally.
3. Create an app-transport photo message with a stable `client_message_id`.
4. Derive path from server-returned conversation/message IDs.
5. Upload to the private bucket using the authenticated user session.
6. Insert attachment metadata referencing the same message/conversation.
7. Render using an authorized private/signed retrieval flow.
8. On failure, keep message/attachment state recoverable and retry-safe; never create a second logical message for the same `client_message_id`.

## Negative gates

- Reject >5 MiB before network upload.
- Reject non JPEG/PNG/WebP.
- Reject externally supplied conversation/message IDs not matching the active chat/message.
- No anonymous upload/read.
- Expired Premium/App customer blocked.
- Suspended broker blocked.
- No client UPDATE/DELETE of Storage objects.
- Production `index.html` attachment controls remain disabled.

## Acceptance

A disposable client+Storage E2E test must prove positive upload/read plus cross-message, cross-conversation, MIME, size, entitlement and retry/duplicate denials before any coordinated production rollout.
