# JACC Broker–Customer App Chat Architecture

Status: **architecture only / staging only**

This design keeps the current Telegram proxy chat running. The app database becomes the durable chat record only after a separate coordinated staging and production rollout.

## 1. Architecture boundary

```text
Customer App/PWA ─┐
                  ├─> authenticated server action/RPC ─> Supabase PostgreSQL
Broker App/PWA ───┘                                  ├─ conversations
                                                     ├─ messages
Railway Telegram relay <─ outbox/notification later ─┤─ receipts/events
                                                     └─ reports/attachments
```

The frontend must never decide `customer_id`, `broker_id`, membership validity, broker assignment or admin authority by itself. The server derives identity from the authenticated JACC profile and verifies the current request/assignment before a write.

## 2. Canonical tables

The repository uses the existing `jacc_` prefix.

| Requested concept | Canonical table | Purpose |
|---|---|---|
| conversations | `jacc_conversations` | One durable conversation per `jacc_service_requests` row |
| conversation_participants | `jacc_conversation_participants` | Customer, assigned broker and optional admin participation history |
| messages | `jacc_messages` | App/Telegram/system message record and dedupe identity |
| message_attachments | `jacc_message_attachments` | Private Storage object metadata for V1 photos |
| message_read_receipts | `jacc_message_read_receipts` | Per-participant delivery/read state |
| conversation_events | `jacc_conversation_events` | Append-only lifecycle and audit events |
| conversation_reports | `jacc_conversation_reports` | Customer/broker reports and admin resolution queue |

## 3. Required field mapping

- `conversation_id`: primary conversation reference used by every child table.
- `request_id`: links chat to the existing broker service request.
- `customer_id`: canonical JACC customer profile from the request.
- `broker_id`: currently assigned broker profile; nullable before assignment.
- `sender_role`: `customer`, `broker`, `admin` or `system`.
- `message_type`: V1 uses `text`, `photo`, `system`, `status`; `voice` and `document` are reserved for a later version.
- `message_text`: bounded text body; required for text/system/status messages.
- `attachment_url`: private Supabase Storage object path, never a public or signed URL.
- `created_at`: immutable server timestamp for ordering and audit.
- `read_at`: first-read summary on messages and canonical per-participant value in read receipts.
- `status`: separate constrained status types for conversations, messages, attachments and reports.
- `closed_by`: JACC profile that closed a conversation.

## 4. Core relationships

```text
jacc_service_requests (1)
    └── (1) jacc_conversations
            ├── (*) jacc_conversation_participants
            ├── (*) jacc_messages
            │       ├── (*) jacc_message_attachments
            │       └── (*) jacc_message_read_receipts
            ├── (*) jacc_conversation_events
            └── (*) jacc_conversation_reports
```

A request has one durable conversation. Broker reassignment does not destroy history: the previous broker participant becomes inactive, a new broker participant is added, `broker_id` is updated through a server transaction, and an event records the change.

## 5. Conversation lifecycle

```text
pending
  └─ broker assigned + participants created ─> active
active
  ├─ customer/broker close ─> closed
  ├─ report filed ─> reported
  └─ admin archive after retention workflow ─> archived
reported
  ├─ resolved and reopened ─> active
  └─ resolved and closed ─> closed
```

Closing a conversation sets `status`, `closed_at` and `closed_by` together. V1 does not hard-delete messages or audit events.

## 6. Message lifecycle

```text
client_message_id allocated by app
        ↓
server verifies identity, membership, assignment and conversation state
        ↓
message inserted once
        ↓
queued/sent → delivered → read
        └───────────────→ failed (retryable transport only)
```

`client_message_id` prevents duplicate app submissions. `transport + external_message_id` prevents duplicate Telegram relay messages. These fields are reserved now so Railway restarts cannot create duplicate history later.

## 7. Attachment contract for V1

- Photo only: JPEG, PNG or WebP.
- Maximum stored metadata size: 5 MB.
- Files belong in a private `jacc-chat-attachments` bucket.
- The database stores an object path in `attachment_url`; signed URLs are generated only when an authorized reader requests the file.
- Upload authorization, content inspection and Storage RLS belong to Task 5.

## 8. Inbox query model

Customer inbox filters `jacc_conversations.customer_id` plus active statuses.

Broker inbox filters `jacc_conversations.broker_id` plus active statuses.

Admin audit reads all conversations through an explicit admin policy/server role. Normal customer and broker clients never receive rows outside their own participant scope.

Indexes support:

- customer/broker inbox ordering by `last_message_at`;
- message history by `(conversation_id, created_at, id)`;
- unread receipt lookup by participant;
- open report queue;
- app and Telegram idempotency keys.

## 9. Event contract

`jacc_conversation_events` is append-only and records events such as:

- `conversation_created`
- `broker_assigned`
- `broker_reassigned`
- `message_sent`
- `message_delivery_failed`
- `conversation_closed`
- `conversation_reopened`
- `report_created`
- `report_resolved`

`event_data` contains sanitized identifiers and transition details only. It must not contain passwords, tokens, server keys, full signed URLs or payment secrets.

## 10. Rollout dependencies

This architecture cannot be activated by itself. Required later work:

1. Task 5: customer/broker/admin RLS, server-side membership enforcement, banned-broker and expired-member controls, attachment Storage policies.
2. Task 6: app inbox, send/read/close/rating/report features.
3. Task 7: Telegram relay/outbox integration and message-ID deduplication.
4. Task 8: App/PWA customer, broker and admin UI.
5. Task 9: cross-account isolation, restart, duplicate, close, unread and report acceptance tests.
6. Task 10: backup, migration rehearsal, coordinated deployment and rollback.

## 11. Current safety state

- Migration file is committed for review only.
- RLS is enabled with no browser policies, so isolated staging remains deny-by-default until Task 5.
- No Supabase migration has been run.
- No production service, branch, Apps Script deployment, Railway launcher or website has been changed.
- The existing Telegram proxy chat remains unchanged.
