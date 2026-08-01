-- JACC Phase 1 migration part: 006_reliability_and_recovery.sql
-- Run after 005_rls_and_permissions.sql.

begin;

-- ---------------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------------

do $$ begin
  create type public.jacc_outbox_status as enum (
    'queued', 'processing', 'sent', 'delivered', 'read',
    'failed', 'retrying', 'dead_letter', 'cancelled'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_backup_status as enum (
    'started', 'succeeded', 'failed', 'verified'
  );
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- SOFT-DELETE / RETENTION METADATA
-- ---------------------------------------------------------------------------

alter table public.jacc_profiles
  add column if not exists archived_at timestamptz,
  add column if not exists soft_deleted_at timestamptz;

alter table public.jacc_service_requests
  add column if not exists archived_at timestamptz,
  add column if not exists soft_deleted_at timestamptz,
  add column if not exists retention_until timestamptz;

-- ---------------------------------------------------------------------------
-- DATABASE-BACKED MESSAGE OUTBOX
-- ---------------------------------------------------------------------------

create table if not exists public.jacc_message_outbox (
  id uuid primary key default gen_random_uuid(),
  request_id uuid references public.jacc_service_requests(id) on delete set null,
  recipient_profile_id uuid references public.jacc_profiles(id) on delete set null,
  channel text not null check (channel in ('telegram', 'app', 'broker_dashboard', 'admin_dashboard')),
  message_type text not null default 'text',
  payload jsonb not null default '{}'::jsonb,
  dedupe_key text,
  status public.jacc_outbox_status not null default 'queued',
  priority integer not null default 0 check (priority between 0 and 1000),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 5 check (max_attempts between 1 and 20),
  available_at timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  last_error text,
  provider_message_id text,
  sent_at timestamptz,
  delivered_at timestamptz,
  read_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_jacc_outbox_dedupe_key
  on public.jacc_message_outbox(dedupe_key)
  where dedupe_key is not null;

create index if not exists idx_jacc_outbox_claim
  on public.jacc_message_outbox(status, available_at, priority desc, created_at)
  where status in ('queued', 'retrying', 'failed');

create index if not exists idx_jacc_outbox_request_created
  on public.jacc_message_outbox(request_id, created_at desc);

create table if not exists public.jacc_delivery_attempts (
  id bigint generated always as identity primary key,
  outbox_id uuid not null references public.jacc_message_outbox(id) on delete cascade,
  attempt_no integer not null check (attempt_no > 0),
  worker_id text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  success boolean,
  provider_status integer,
  provider_message_id text,
  error_message text,
  response_excerpt text,
  unique (outbox_id, attempt_no)
);

create index if not exists idx_jacc_delivery_attempts_outbox
  on public.jacc_delivery_attempts(outbox_id, attempt_no desc);

-- ---------------------------------------------------------------------------
-- BACKUP / RESTORE EVIDENCE
-- These tables record backup operations. Actual backups must be enabled in
-- Supabase and/or an external encrypted backup job.
-- ---------------------------------------------------------------------------

create table if not exists public.jacc_backup_runs (
  id uuid primary key default gen_random_uuid(),
  backup_type text not null check (backup_type in ('managed', 'database_export', 'storage_export', 'financial_export')),
  status public.jacc_backup_status not null default 'started',
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  storage_location text,
  checksum_sha256 text,
  size_bytes bigint check (size_bytes is null or size_bytes >= 0),
  retention_until timestamptz,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid references public.jacc_profiles(id)
);

create index if not exists idx_jacc_backup_runs_started
  on public.jacc_backup_runs(started_at desc);

create table if not exists public.jacc_restore_tests (
  id uuid primary key default gen_random_uuid(),
  backup_run_id uuid references public.jacc_backup_runs(id) on delete set null,
  status public.jacc_backup_status not null default 'started',
  environment text not null default 'test',
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  requests_checked integer not null default 0 check (requests_checked >= 0),
  messages_checked integer not null default 0 check (messages_checked >= 0),
  photos_checked integer not null default 0 check (photos_checked >= 0),
  audit_rows_checked integer not null default 0 check (audit_rows_checked >= 0),
  notes text,
  performed_by uuid references public.jacc_profiles(id)
);

create index if not exists idx_jacc_restore_tests_started
  on public.jacc_restore_tests(started_at desc);

-- ---------------------------------------------------------------------------
-- IMMUTABLE AUDIT LOGS
-- Audit rows are append-only. Corrections must be written as a new audit row.
-- ---------------------------------------------------------------------------

create or replace function public.jacc_reject_audit_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'JACC audit logs are immutable; append a correction instead';
end;
$$;

drop trigger if exists trg_jacc_audit_logs_immutable on public.jacc_audit_logs;
create trigger trg_jacc_audit_logs_immutable
before update or delete on public.jacc_audit_logs
for each row execute function public.jacc_reject_audit_mutation();

-- ---------------------------------------------------------------------------
-- OUTBOX RPC FUNCTIONS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_enqueue_message(
  p_channel text,
  p_message_type text,
  p_payload jsonb,
  p_request_id uuid default null,
  p_recipient_profile_id uuid default null,
  p_dedupe_key text default null,
  p_priority integer default 0,
  p_max_attempts integer default 5
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  if p_channel not in ('telegram', 'app', 'broker_dashboard', 'admin_dashboard') then
    raise exception 'Unsupported JACC delivery channel: %', p_channel;
  end if;

  insert into public.jacc_message_outbox (
    request_id, recipient_profile_id, channel, message_type, payload,
    dedupe_key, priority, max_attempts
  ) values (
    p_request_id, p_recipient_profile_id, p_channel,
    coalesce(nullif(trim(p_message_type), ''), 'text'),
    coalesce(p_payload, '{}'::jsonb), p_dedupe_key,
    greatest(0, least(1000, p_priority)),
    greatest(1, least(20, p_max_attempts))
  )
  on conflict (dedupe_key) where dedupe_key is not null
  do update set updated_at = public.jacc_message_outbox.updated_at
  returning id into v_id;

  return v_id;
end;
$$;

create or replace function public.jacc_claim_outbox_messages(
  p_worker_id text,
  p_limit integer default 20
)
returns setof public.jacc_message_outbox
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select o.id
    from public.jacc_message_outbox o
    where o.status in ('queued', 'retrying', 'failed')
      and o.available_at <= now()
      and o.attempt_count < o.max_attempts
      and o.archived_at is null
    order by o.priority desc, o.available_at, o.created_at
    for update skip locked
    limit greatest(1, least(100, p_limit))
  ), claimed as (
    update public.jacc_message_outbox o
    set status = 'processing',
        locked_at = now(),
        locked_by = p_worker_id,
        attempt_count = o.attempt_count + 1,
        updated_at = now()
    from candidates c
    where o.id = c.id
    returning o.*
  )
  select * from claimed;
end;
$$;

create or replace function public.jacc_mark_outbox_sent(
  p_outbox_id uuid,
  p_worker_id text,
  p_provider_message_id text default null,
  p_provider_status integer default null,
  p_response_excerpt text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_attempt integer;
begin
  update public.jacc_message_outbox
  set status = 'sent',
      provider_message_id = p_provider_message_id,
      sent_at = coalesce(sent_at, now()),
      locked_at = null,
      locked_by = null,
      last_error = null,
      updated_at = now()
  where id = p_outbox_id
    and status = 'processing'
    and locked_by = p_worker_id
  returning attempt_count into v_attempt;

  if v_attempt is null then
    raise exception 'Outbox item is not owned by worker';
  end if;

  insert into public.jacc_delivery_attempts (
    outbox_id, attempt_no, worker_id, finished_at, success,
    provider_status, provider_message_id, response_excerpt
  ) values (
    p_outbox_id, v_attempt, p_worker_id, now(), true,
    p_provider_status, p_provider_message_id, left(p_response_excerpt, 1000)
  )
  on conflict (outbox_id, attempt_no) do update
  set finished_at = excluded.finished_at,
      success = true,
      provider_status = excluded.provider_status,
      provider_message_id = excluded.provider_message_id,
      response_excerpt = excluded.response_excerpt;
end;
$$;

create or replace function public.jacc_mark_outbox_failed(
  p_outbox_id uuid,
  p_worker_id text,
  p_error_message text,
  p_provider_status integer default null,
  p_response_excerpt text default null
)
returns public.jacc_outbox_status
language plpgsql
security definer
set search_path = public
as $$
declare
  v_attempt integer;
  v_max integer;
  v_status public.jacc_outbox_status;
  v_next timestamptz;
begin
  select attempt_count, max_attempts
  into v_attempt, v_max
  from public.jacc_message_outbox
  where id = p_outbox_id
    and status = 'processing'
    and locked_by = p_worker_id
  for update;

  if v_attempt is null then
    raise exception 'Outbox item is not owned by worker';
  end if;

  if v_attempt >= v_max then
    v_status := 'dead_letter';
    v_next := now();
  else
    v_status := 'retrying';
    v_next := now() + case
      when v_attempt = 1 then interval '5 minutes'
      when v_attempt = 2 then interval '15 minutes'
      when v_attempt = 3 then interval '1 hour'
      else interval '6 hours'
    end;
  end if;

  update public.jacc_message_outbox
  set status = v_status,
      available_at = v_next,
      locked_at = null,
      locked_by = null,
      last_error = left(coalesce(p_error_message, 'Unknown delivery error'), 2000),
      updated_at = now()
  where id = p_outbox_id;

  insert into public.jacc_delivery_attempts (
    outbox_id, attempt_no, worker_id, finished_at, success,
    provider_status, error_message, response_excerpt
  ) values (
    p_outbox_id, v_attempt, p_worker_id, now(), false,
    p_provider_status, left(p_error_message, 2000), left(p_response_excerpt, 1000)
  )
  on conflict (outbox_id, attempt_no) do update
  set finished_at = excluded.finished_at,
      success = false,
      provider_status = excluded.provider_status,
      error_message = excluded.error_message,
      response_excerpt = excluded.response_excerpt;

  return v_status;
end;
$$;

create or replace function public.jacc_recover_stuck_outbox(
  p_stuck_after interval default interval '10 minutes'
)
returns table (outbox_id uuid, previous_worker text)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with recovered as (
    update public.jacc_message_outbox o
    set status = case when o.attempt_count >= o.max_attempts then 'dead_letter'::public.jacc_outbox_status else 'retrying'::public.jacc_outbox_status end,
        available_at = now(),
        locked_at = null,
        locked_by = null,
        last_error = coalesce(o.last_error, 'Recovered after worker interruption'),
        updated_at = now()
    where o.status = 'processing'
      and o.locked_at < now() - p_stuck_after
    returning o.id, o.locked_by
  )
  select recovered.id, recovered.locked_by from recovered;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS / PERMISSIONS
-- ---------------------------------------------------------------------------

alter table public.jacc_message_outbox enable row level security;
alter table public.jacc_delivery_attempts enable row level security;
alter table public.jacc_backup_runs enable row level security;
alter table public.jacc_restore_tests enable row level security;

revoke all on public.jacc_message_outbox from anon, authenticated;
revoke all on public.jacc_delivery_attempts from anon, authenticated;
revoke all on public.jacc_backup_runs from anon, authenticated;
revoke all on public.jacc_restore_tests from anon, authenticated;

revoke execute on function public.jacc_enqueue_message(text, text, jsonb, uuid, uuid, text, integer, integer) from public;
revoke execute on function public.jacc_claim_outbox_messages(text, integer) from public;
revoke execute on function public.jacc_mark_outbox_sent(uuid, text, text, integer, text) from public;
revoke execute on function public.jacc_mark_outbox_failed(uuid, text, text, integer, text) from public;
revoke execute on function public.jacc_recover_stuck_outbox(interval) from public;

grant execute on function public.jacc_enqueue_message(text, text, jsonb, uuid, uuid, text, integer, integer) to service_role;
grant execute on function public.jacc_claim_outbox_messages(text, integer) to service_role;
grant execute on function public.jacc_mark_outbox_sent(uuid, text, text, integer, text) to service_role;
grant execute on function public.jacc_mark_outbox_failed(uuid, text, text, integer, text) to service_role;
grant execute on function public.jacc_recover_stuck_outbox(interval) to service_role;

commit;
