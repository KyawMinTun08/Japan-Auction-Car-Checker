-- JACC Phase 3 migration: 010_chat_architecture.sql
-- REVIEW/STAGING ONLY. Do not run against production until Phase 2 acceptance passes.
-- This migration creates the database contract only. Task 5 adds the RLS policies.

begin;

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- CHAT TYPES
-- ---------------------------------------------------------------------------

do $$ begin
  create type public.jacc_conversation_status as enum (
    'pending', 'active', 'closed', 'reported', 'archived'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_participant_role as enum (
    'customer', 'broker', 'admin'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_message_sender_role as enum (
    'customer', 'broker', 'admin', 'system'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_message_type as enum (
    'text', 'photo', 'system', 'status', 'voice', 'document'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_message_status as enum (
    'queued', 'sent', 'delivered', 'read', 'failed', 'deleted'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_message_transport as enum (
    'app', 'telegram', 'system'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_attachment_status as enum (
    'pending', 'ready', 'rejected', 'deleted'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_report_status as enum (
    'open', 'reviewing', 'resolved', 'dismissed'
  );
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- CORE CHAT TABLES
-- ---------------------------------------------------------------------------

create table if not exists public.jacc_conversations (
  conversation_id uuid primary key default gen_random_uuid(),
  request_id uuid not null unique
    references public.jacc_service_requests(id) on delete restrict,
  customer_id uuid not null
    references public.jacc_profiles(id) on delete restrict,
  broker_id uuid
    references public.jacc_broker_profiles(user_id) on delete restrict,
  status public.jacc_conversation_status not null default 'pending',
  last_message_id uuid,
  last_message_at timestamptz,
  closed_at timestamptz,
  closed_by uuid references public.jacc_profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_conversation_close_state_check check (
    (status in ('closed', 'archived') and closed_at is not null) or
    (status not in ('closed', 'archived') and closed_at is null)
  )
);

create table if not exists public.jacc_conversation_participants (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete cascade,
  profile_id uuid not null
    references public.jacc_profiles(id) on delete restrict,
  participant_role public.jacc_participant_role not null,
  anonymous_label text,
  joined_at timestamptz not null default now(),
  left_at timestamptz,
  is_active boolean not null default true,
  last_read_message_id uuid,
  last_read_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (conversation_id, profile_id),
  constraint jacc_participant_active_state_check check (
    (is_active and left_at is null) or
    (not is_active and left_at is not null)
  ),
  constraint jacc_participant_label_check check (
    anonymous_label is null or char_length(anonymous_label) between 2 and 80
  )
);

create table if not exists public.jacc_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete cascade,
  request_id uuid not null
    references public.jacc_service_requests(id) on delete restrict,
  sender_id uuid references public.jacc_profiles(id) on delete set null,
  sender_role public.jacc_message_sender_role not null,
  message_type public.jacc_message_type not null default 'text',
  message_text text,
  attachment_url text,
  reply_to_message_id uuid references public.jacc_messages(id) on delete set null,
  transport public.jacc_message_transport not null default 'app',
  external_message_id text,
  client_message_id text,
  status public.jacc_message_status not null default 'sent',
  failure_code text,
  read_at timestamptz,
  edited_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  constraint jacc_message_text_length_check check (
    message_text is null or char_length(message_text) between 1 and 4000
  ),
  constraint jacc_message_attachment_path_check check (
    attachment_url is null or
    (attachment_url <> '' and attachment_url !~* '^https?://')
  ),
  constraint jacc_message_payload_check check (
    (message_type in ('text', 'system', 'status') and message_text is not null) or
    (message_type in ('photo', 'voice', 'document'))
  ),
  constraint jacc_message_sender_check check (
    (sender_role = 'system' and sender_id is null) or
    (sender_role <> 'system' and sender_id is not null)
  ),
  constraint jacc_message_deleted_state_check check (
    (status = 'deleted' and deleted_at is not null) or
    (status <> 'deleted')
  )
);

alter table public.jacc_conversations
  drop constraint if exists jacc_conversations_last_message_fk;
alter table public.jacc_conversations
  add constraint jacc_conversations_last_message_fk
  foreign key (last_message_id)
  references public.jacc_messages(id)
  on delete set null;

alter table public.jacc_conversation_participants
  drop constraint if exists jacc_participants_last_read_message_fk;
alter table public.jacc_conversation_participants
  add constraint jacc_participants_last_read_message_fk
  foreign key (last_read_message_id)
  references public.jacc_messages(id)
  on delete set null;

create table if not exists public.jacc_message_attachments (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null
    references public.jacc_messages(id) on delete cascade,
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete cascade,
  attachment_url text not null,
  storage_bucket text not null default 'jacc-chat-attachments',
  mime_type text not null,
  file_name text,
  size_bytes bigint not null,
  width integer,
  height integer,
  sha256 text,
  status public.jacc_attachment_status not null default 'pending',
  created_at timestamptz not null default now(),
  constraint jacc_attachment_path_check check (
    attachment_url <> '' and attachment_url !~* '^https?://'
  ),
  constraint jacc_attachment_v1_mime_check check (
    mime_type in ('image/jpeg', 'image/png', 'image/webp')
  ),
  constraint jacc_attachment_v1_size_check check (
    size_bytes > 0 and size_bytes <= 5242880
  ),
  constraint jacc_attachment_dimensions_check check (
    (width is null and height is null) or
    (width > 0 and height > 0)
  ),
  unique (storage_bucket, attachment_url)
);

create table if not exists public.jacc_message_read_receipts (
  id bigint generated always as identity primary key,
  message_id uuid not null
    references public.jacc_messages(id) on delete cascade,
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete cascade,
  participant_id uuid not null
    references public.jacc_conversation_participants(id) on delete cascade,
  delivered_at timestamptz,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique (message_id, participant_id),
  constraint jacc_receipt_time_order_check check (
    read_at is null or delivered_at is null or read_at >= delivered_at
  )
);

create table if not exists public.jacc_conversation_events (
  id bigint generated always as identity primary key,
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete cascade,
  request_id uuid not null
    references public.jacc_service_requests(id) on delete restrict,
  actor_id uuid references public.jacc_profiles(id) on delete set null,
  event_type text not null,
  event_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint jacc_conversation_event_type_check check (
    char_length(event_type) between 2 and 80
  )
);

create table if not exists public.jacc_conversation_reports (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null
    references public.jacc_conversations(conversation_id) on delete restrict,
  request_id uuid not null
    references public.jacc_service_requests(id) on delete restrict,
  reporter_id uuid not null
    references public.jacc_profiles(id) on delete restrict,
  reported_profile_id uuid
    references public.jacc_profiles(id) on delete set null,
  message_id uuid references public.jacc_messages(id) on delete set null,
  reason_code text not null,
  details text,
  status public.jacc_report_status not null default 'open',
  reviewed_by uuid references public.jacc_profiles(id) on delete set null,
  reviewed_at timestamptz,
  resolution_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_report_reason_check check (
    char_length(reason_code) between 2 and 80
  ),
  constraint jacc_report_details_check check (
    details is null or char_length(details) <= 2000
  ),
  constraint jacc_report_review_state_check check (
    (status in ('resolved', 'dismissed') and reviewed_at is not null and reviewed_by is not null) or
    (status in ('open', 'reviewing'))
  )
);

-- ---------------------------------------------------------------------------
-- BUSINESS-INTEGRITY HELPERS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_chat_validate_conversation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_customer_id uuid;
  v_broker_id uuid;
begin
  select r.customer_id, r.assigned_broker_id
  into v_customer_id, v_broker_id
  from public.jacc_service_requests r
  where r.id = new.request_id;

  if v_customer_id is null then
    raise exception 'CHAT_REQUEST_NOT_FOUND';
  end if;

  if new.customer_id <> v_customer_id then
    raise exception 'CHAT_CUSTOMER_REQUEST_MISMATCH';
  end if;

  if new.broker_id is not null and new.broker_id is distinct from v_broker_id then
    raise exception 'CHAT_BROKER_ASSIGNMENT_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_conversation
  on public.jacc_conversations;
create trigger trg_jacc_chat_validate_conversation
before insert or update of request_id, customer_id, broker_id
on public.jacc_conversations
for each row execute function public.jacc_chat_validate_conversation();

create or replace function public.jacc_chat_validate_message_request()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request_id uuid;
begin
  select c.request_id
  into v_request_id
  from public.jacc_conversations c
  where c.conversation_id = new.conversation_id;

  if v_request_id is null or new.request_id <> v_request_id then
    raise exception 'CHAT_MESSAGE_REQUEST_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_message_request
  on public.jacc_messages;
create trigger trg_jacc_chat_validate_message_request
before insert or update of conversation_id, request_id
on public.jacc_messages
for each row execute function public.jacc_chat_validate_message_request();

drop trigger if exists trg_jacc_conversations_updated_at
  on public.jacc_conversations;
create trigger trg_jacc_conversations_updated_at
before update on public.jacc_conversations
for each row execute function public.jacc_touch_updated_at();

drop trigger if exists trg_jacc_participants_updated_at
  on public.jacc_conversation_participants;
create trigger trg_jacc_participants_updated_at
before update on public.jacc_conversation_participants
for each row execute function public.jacc_touch_updated_at();

drop trigger if exists trg_jacc_reports_updated_at
  on public.jacc_conversation_reports;
create trigger trg_jacc_reports_updated_at
before update on public.jacc_conversation_reports
for each row execute function public.jacc_touch_updated_at();

-- ---------------------------------------------------------------------------
-- INDEXES AND IDEMPOTENCY
-- ---------------------------------------------------------------------------

create index if not exists idx_jacc_conversations_customer_status
  on public.jacc_conversations(customer_id, status, last_message_at desc nulls last);

create index if not exists idx_jacc_conversations_broker_status
  on public.jacc_conversations(broker_id, status, last_message_at desc nulls last)
  where broker_id is not null;

create unique index if not exists uq_jacc_active_participant_role
  on public.jacc_conversation_participants(conversation_id, participant_role)
  where is_active and participant_role in ('customer', 'broker');

create index if not exists idx_jacc_participants_profile_active
  on public.jacc_conversation_participants(profile_id, is_active, conversation_id);

create index if not exists idx_jacc_messages_conversation_created
  on public.jacc_messages(conversation_id, created_at desc, id desc);

create index if not exists idx_jacc_messages_unread
  on public.jacc_messages(conversation_id, created_at desc)
  where status in ('sent', 'delivered');

create unique index if not exists uq_jacc_message_client_id
  on public.jacc_messages(conversation_id, client_message_id)
  where client_message_id is not null;

create unique index if not exists uq_jacc_message_external_id
  on public.jacc_messages(transport, external_message_id)
  where external_message_id is not null;

create index if not exists idx_jacc_attachments_message
  on public.jacc_message_attachments(message_id, created_at);

create index if not exists idx_jacc_receipts_participant_unread
  on public.jacc_message_read_receipts(participant_id, read_at, message_id);

create index if not exists idx_jacc_conversation_events_audit
  on public.jacc_conversation_events(conversation_id, created_at desc, id desc);

create index if not exists idx_jacc_conversation_reports_queue
  on public.jacc_conversation_reports(status, created_at)
  where status in ('open', 'reviewing');

-- ---------------------------------------------------------------------------
-- DENY-BY-DEFAULT BOUNDARY
-- ---------------------------------------------------------------------------
-- Task 5 will add explicit customer, broker and admin policies. Enabling RLS
-- now prevents accidental browser access if this migration is reviewed in an
-- isolated staging project before those policies exist.

alter table public.jacc_conversations enable row level security;
alter table public.jacc_conversation_participants enable row level security;
alter table public.jacc_messages enable row level security;
alter table public.jacc_message_attachments enable row level security;
alter table public.jacc_message_read_receipts enable row level security;
alter table public.jacc_conversation_events enable row level security;
alter table public.jacc_conversation_reports enable row level security;

comment on table public.jacc_conversations is
  'One durable broker-customer conversation per JACC service request.';
comment on column public.jacc_message_attachments.attachment_url is
  'Private Supabase Storage object path only; never store a public or signed URL.';
comment on column public.jacc_messages.external_message_id is
  'Telegram or other transport message ID used for idempotent relay/deduplication.';
comment on table public.jacc_conversation_events is
  'Append-only conversation audit timeline; mutation policies are added in Task 5.';

commit;
