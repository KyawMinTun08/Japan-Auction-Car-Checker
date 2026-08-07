-- JACC Phase 3 migration: 012_chat_storage_security.sql
-- REVIEW/STAGING ONLY. Run after 010_chat_architecture.sql and 011_chat_security.sql.
-- Do not run against production until isolated Storage acceptance passes.

begin;

-- ---------------------------------------------------------------------------
-- PRIVATE BUCKET CONTRACT
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'jacc-chat-attachments',
  'jacc-chat-attachments',
  false,
  5242880,
  array['image/jpeg','image/png','image/webp']::text[]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- ---------------------------------------------------------------------------
-- STORAGE PATH / METADATA HELPERS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_chat_storage_path_valid(p_name text)
returns boolean
language sql
immutable
as $$
  select coalesce(p_name, '') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/[A-Za-z0-9_-]{8,128}\.(jpg|jpeg|png|webp)$';
$$;

create or replace function public.jacc_chat_storage_conversation_id(p_name text)
returns uuid
language sql
immutable
as $$
  select case
    when public.jacc_chat_storage_path_valid(p_name)
      then split_part(p_name, '/', 1)::uuid
    else null
  end;
$$;

create or replace function public.jacc_chat_storage_message_id(p_name text)
returns uuid
language sql
immutable
as $$
  select case
    when public.jacc_chat_storage_path_valid(p_name)
      then split_part(p_name, '/', 2)::uuid
    else null
  end;
$$;

create or replace function public.jacc_chat_storage_metadata_valid(p_metadata jsonb)
returns boolean
language sql
immutable
as $$
  select
    lower(coalesce(p_metadata->>'mimetype','')) in ('image/jpeg','image/png','image/webp')
    and coalesce(p_metadata->>'size','') ~ '^[0-9]+$'
    and (p_metadata->>'size')::bigint between 1 and 5242880;
$$;

create or replace function public.jacc_chat_storage_read_allowed(p_name text)
returns boolean
language sql
stable
security definer
set search_path = public, storage
as $$
  select
    public.jacc_chat_storage_path_valid(p_name)
    and public.jacc_chat_can_access_conversation(
      public.jacc_chat_storage_conversation_id(p_name)
    );
$$;

create or replace function public.jacc_chat_storage_insert_allowed(
  p_name text,
  p_metadata jsonb
)
returns boolean
language sql
stable
security definer
set search_path = public, storage
as $$
  select
    public.jacc_chat_storage_path_valid(p_name)
    and public.jacc_chat_storage_metadata_valid(p_metadata)
    and public.jacc_chat_can_send_to_conversation(
      public.jacc_chat_storage_conversation_id(p_name)
    )
    and public.jacc_chat_message_owned_by_current(
      public.jacc_chat_storage_message_id(p_name),
      public.jacc_chat_storage_conversation_id(p_name)
    );
$$;

-- ---------------------------------------------------------------------------
-- LEAST-PRIVILEGE STORAGE RLS
-- ---------------------------------------------------------------------------

alter table storage.objects enable row level security;

revoke all on table storage.objects from anon, authenticated;
grant select, insert on table storage.objects to authenticated;

drop policy if exists jacc_chat_storage_select on storage.objects;
create policy jacc_chat_storage_select
on storage.objects
for select
to authenticated
using (
  bucket_id = 'jacc-chat-attachments'
  and public.jacc_chat_storage_read_allowed(name)
);

drop policy if exists jacc_chat_storage_insert on storage.objects;
create policy jacc_chat_storage_insert
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'jacc-chat-attachments'
  and public.jacc_chat_storage_insert_allowed(name, metadata)
);

-- No UPDATE or DELETE policy is created for authenticated clients.
-- Moderation/rejection/cleanup remains service-role only in v1.

commit;
