# JACC Phase 3 Chat Security — Task 5

Status: **review/staging only**. No Supabase migration has been run.

This task secures the Task 4 Broker–Customer chat schema. It does not activate app chat, replace the current Telegram proxy chat, or change production.

## Migration order

```text
phase1/sql/001...009
phase3/sql/010_chat_architecture.sql
phase3/sql/011_chat_security.sql
```

The Task 5 migration must never be run without Task 4 immediately beneath it.

## Identity and entitlement

All browser/PWA/Flutter access uses the authenticated user's `auth.uid()` through the existing `jacc_current_profile_id()` mapping.

### Customer

A customer can read or send chat data only when all conditions are true:

- `jacc_profiles.account_active = true`
- profile role is `customer`
- membership plan is `premium`
- service channel is `app`
- membership status is `ACTIVE`
- membership has started
- membership has not expired
- the customer has an active participant row for the conversation

Standard/Telegram members do not gain app-chat access.

### Broker

A broker can read or send chat data only when:

- the central profile is active
- role is `broker` or `lead_broker`
- broker status is `probation` or `active`
- the broker has an active participant row for the conversation

`accepting_requests` is intentionally not required for an already-assigned conversation. A broker may stop accepting new requests but must still be able to finish existing work.

### Admin and lead broker

Admins and lead brokers have explicit oversight access through the existing admin helper. This is not anonymous public access. Administrative writes still use trusted server operations or the narrow policies defined in the migration.

## RLS behavior

| Table | Authenticated read | Authenticated insert/update | Direct delete |
|---|---|---|---|
| `jacc_conversations` | entitled participant/admin | server only | server only |
| `jacc_conversation_participants` | own row/admin | server only | server only |
| `jacc_messages` | entitled participant/admin | own `app` messages only | no client policy |
| `jacc_message_attachments` | entitled participant/admin | own-message metadata only | no client policy |
| `jacc_message_read_receipts` | own receipt/admin | own receipt only; timestamps only | no client policy |
| `jacc_conversation_events` | entitled participant/admin | server only; append-only | blocked |
| `jacc_conversation_reports` | reporter/admin | new open report only | no client policy |

`anon` receives no chat-table privileges.

## Anti-forgery rules

Authenticated app clients cannot:

- insert `telegram` or `system` transport messages;
- provide a Telegram `external_message_id`;
- set another user's sender ID or incompatible sender role;
- insert delivery failure, read, edit or delete state on a new message;
- put a public or signed URL in the legacy message attachment field;
- attach metadata to another user's message;
- reply to a message from another conversation;
- create a read receipt for another participant;
- report a message or profile outside the conversation.

Telegram relay remains a later server-side task. The reserved external IDs are for deduplication only.

## Cross-table integrity

Task 5 adds database triggers that verify:

- customer/broker/admin participant roles match the conversation and profile;
- non-system senders are valid participants or authorized admins;
- reply targets stay inside the same conversation;
- attachment message and conversation IDs agree;
- receipt message, participant and conversation IDs agree;
- report request, message and target profile agree with the conversation;
- conversation events are append-only.

These checks also protect trusted server writes that bypass RLS.

## Attachment storage boundary

The database accepts only private Storage object paths for attachment metadata. The Task 4 V1 metadata contract remains JPEG/PNG/WebP and a 5 MB maximum.

Task 5 does **not** create a Supabase Storage bucket or `storage.objects` policies. Photo upload must remain disabled until a later isolated staging task creates the private bucket, validates path ownership, generates short-lived signed reads server-side, and tests cleanup/retry behavior.

## Deployment gate

Before any staging migration:

1. Phase 2 live acceptance must pass.
2. Task 4 and Task 5 Draft PRs must remain unmerged until reviewed.
3. Use an isolated Supabase staging project and anonymous test accounts.
4. Run migrations in order and verify RLS as customer, broker, admin, expired member, suspended broker and anonymous user.
5. Confirm existing Phase 1 request/assignment flows still pass.
6. Do not enable production Railway/website code from these branches.

## Rollback boundary

Before staging, take a schema-only backup. If validation fails, discard the isolated staging database or reverse only the Task 5 policies/functions/triggers. Never delete production requests, assignments, profiles, audit logs or customer records.

## Current production status

- No Supabase migration has been run.
- No production service, branch, website, Railway launcher or Apps Script project has changed.
- Existing Telegram proxy chat remains unchanged.
- No secret or customer row is stored in this branch.
