# JACC Phase 3 — In-app Broker–Customer Chat

Status: **staged only**. This folder is not imported by any production launcher and must not be deployed until Phase 2 membership/device sessions are accepted.

Tracks #17.

## Why this is separate from Phase 2

Phase 2 hardens membership, payment, Telegram channel access, device binding and website sessions. In-app chat adds a new persistent data surface and a new Railway API. Keeping it in a stacked Phase 3 branch prevents chat work from changing the coordinated Phase 2 release.

## Trust boundary

1. Web/PWA/Flutter reads the existing Phase 2 `v4` session from local storage.
2. Every chat request sends `token`, `userId`, `deviceId` and `app` to Railway over HTTPS.
3. Railway calls the Apps Script `verifyToken` route. A missing, expired, suspended or device-mismatched session fails closed.
4. Railway maps the verified numeric member ID to `jacc_profiles.telegram_user_id` and obtains the canonical Supabase profile UUID.
5. Railway calls service-role-only chat RPCs. The browser never receives Supabase service credentials and never writes chat tables directly.
6. Each RPC re-checks that the actor is the request customer, current assigned broker, or an admin for read/audit. Only the customer/current broker may send a participant message.

## Initial transport

The first release uses authenticated JSON endpoints plus bounded polling. This is deliberate: the current website uses Apps Script membership sessions rather than Supabase Auth JWTs, so exposing Supabase Realtime directly would create a second authentication model. Realtime transport can be added after the authorization contract is proven.

## Staged files

- `phase3/sql/001_app_chat.sql` — private chat tables, indexes and service-role-only RPCs.
- `phase3/app_chat/service.py` — Railway `aiohttp` route installer and Apps Script session verification.
- `phase3/app_chat/client.js` — browser/PWA/Flutter client using the Phase 2 v4 session.
- `phase3/app_chat/ui.js` and `ui.css` — responsive thread list, messages, unread display, send and close-chat interface.
- `phase3/app_chat/apply_app_chat_ui.py` — guarded transformer that adds the Chat navigation and panel to a generated Phase 2 app.
- `phase3/tests/test_app_chat_service.py` and `test_app_chat_ui.py` — fail-closed, input-boundary and integration tests.

## API contract

All endpoints use `POST` and JSON. Authentication is carried in the request body, never in the URL.

- `/api/v1/chat/threads` — list conversations available to the verified actor.
- `/api/v1/chat/open` — open or return the thread for a canonical request code.
- `/api/v1/chat/messages` — list messages with cursor pagination.
- `/api/v1/chat/send` — send one idempotent text message.
- `/api/v1/chat/read` — advance the caller's read cursor.
- `/api/v1/chat/close` — close the conversation with audit evidence.

The client supplies a random UUID `clientMessageId`. The database unique key `(thread_id, sender_id, client_message_id)` makes retries safe.

## Staged app build

Use the exact Railway HTTPS chat API base. Do not use an IP address, HTTP URL, credential-bearing URL or wildcard origin.

```bash
python phase3/app_chat/apply_app_chat_ui.py \
  index.html \
  --api-base https://YOUR-EXACT-RAILWAY-CHAT-HOST \
  --output build/staged/index-chat.html

python phase3/app_chat/apply_app_chat_ui.py \
  build/staged/index-chat.html \
  --api-base https://YOUR-EXACT-RAILWAY-CHAT-HOST \
  --check
```

The transformer fails closed if the current Phase 2 app anchors drift. It adds the exact API origin to Content Security Policy, keeps the root production `index.html` unchanged during staging and does not place Supabase credentials in browser files.

## Data retention and privacy

- Message bodies are stored in Supabase because chat history must survive Railway restarts and app refreshes.
- Normal logs contain request IDs, status codes and error classes only; they must not contain message bodies, session tokens, passwords, device IDs or service keys.
- Initial scope is text only. Attachments remain disabled until private object storage, MIME validation, malware handling and deletion rules are approved.
- Admin can read for audit and close with a reason, but cannot send a participant message as Customer or Broker.

## Release gates

1. Finish and accept the Phase 2 membership/device-session deployment.
2. Back up Supabase and review `phase3/sql/001_app_chat.sql`.
3. Apply the SQL migration in a controlled migration window.
4. Register the Railway chat routes behind an exact allowed-origin list.
5. Generate the staged app using the exact Railway HTTPS API base.
6. Pilot with one real Customer and one real assigned Broker.
7. Verify a third member, expired member and mismatched device all fail closed.
8. Restart Railway and confirm history/read state survives.
9. Keep Telegram proxy chat as fallback until the pilot is signed off.
10. Obtain explicit owner approval before production launcher import, website deployment or merge.

## Production non-goals for the first pilot

- No direct Supabase browser connection.
- No attachments, voice notes or video.
- No typing indicator or presence tracking.
- No admin impersonation.
- No automatic removal of Telegram proxy chat.
- No Phase 2 deployment or PR merge as a side effect of this branch.
