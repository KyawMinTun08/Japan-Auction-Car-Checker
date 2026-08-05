-- JACC Phase 3 migration: private in-app Broker–Customer chat
-- STAGED ONLY. Apply after Phase 2 membership/device-session acceptance.
-- The browser must never receive the Supabase service-role key.

begin;

create extension if not exists pgcrypto;

do $$ begin
  create type public.jacc_chat_status as enum ('open', 'closed', 'disputed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_chat_source as enum ('app', 'telegram', 'system');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_chat_message_type as enum ('text', 'system');
exception when duplicate_object then null; end $$;

create table if not exists public.jacc_chat_threads (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null unique
    references public.jacc_service_requests(id) on delete cascade,
  customer_id uuid not null
    references public.jacc_profiles(id),
  broker_id uuid not null
    references public.jacc_profiles(id),
  status public.jacc_chat_status not null default 'open',
  last_message_id uuid,
  last_message_at timestamptz,
  closed_by uuid references public.jacc_profiles(id),
  closed_reason text,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_chat_participants_differ check (customer_id <> broker_id),
  constraint jacc_chat_close_reason_length check (
    closed_reason is null or char_length(closed_reason) <= 500
  )
);

create table if not exists public.jacc_chat_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null
    references public.jacc_chat_threads(id) on delete cascade,
  sender_id uuid not null
    references public.jacc_profiles(id),
  sender_role text not null
    check (sender_role in ('customer', 'broker', 'system')),
  source public.jacc_chat_source not null default 'app',
  message_type public.jacc_chat_message_type not null default 'text',
  body text not null,
  client_message_id uuid not null,
  created_at timestamptz not null default now(),
  edited_at timestamptz,
  deleted_at timestamptz,
  constraint jacc_chat_message_body_length check (
    char_length(body) between 1 and 4000
  ),
  unique (thread_id, sender_id, client_message_id)
);

alter table public.jacc_chat_threads
  drop constraint if exists jacc_chat_threads_last_message_id_fkey;
alter table public.jacc_chat_threads
  add constraint jacc_chat_threads_last_message_id_fkey
  foreign key (last_message_id)
  references public.jacc_chat_messages(id)
  on delete set null;

create table if not exists public.jacc_chat_read_receipts (
  thread_id uuid not null
    references public.jacc_chat_threads(id) on delete cascade,
  profile_id uuid not null
    references public.jacc_profiles(id) on delete cascade,
  last_read_message_id uuid
    references public.jacc_chat_messages(id) on delete set null,
  last_read_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (thread_id, profile_id)
);

create index if not exists idx_jacc_chat_threads_customer_activity
  on public.jacc_chat_threads(customer_id, last_message_at desc nulls last);

create index if not exists idx_jacc_chat_threads_broker_activity
  on public.jacc_chat_threads(broker_id, last_message_at desc nulls last);

create index if not exists idx_jacc_chat_messages_thread_created
  on public.jacc_chat_messages(thread_id, created_at desc, id desc)
  where deleted_at is null;

create index if not exists idx_jacc_chat_receipts_profile
  on public.jacc_chat_read_receipts(profile_id, updated_at desc);

alter table public.jacc_chat_threads enable row level security;
alter table public.jacc_chat_messages enable row level security;
alter table public.jacc_chat_read_receipts enable row level security;

-- Initial release is Railway/service-role only. No browser policies are created.
revoke all on table public.jacc_chat_threads from public, anon, authenticated;
revoke all on table public.jacc_chat_messages from public, anon, authenticated;
revoke all on table public.jacc_chat_read_receipts from public, anon, authenticated;

grant select, insert, update, delete on table public.jacc_chat_threads to service_role;
grant select, insert, update, delete on table public.jacc_chat_messages to service_role;
grant select, insert, update, delete on table public.jacc_chat_read_receipts to service_role;

create or replace function public.jacc_chat_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_threads_updated_at
  on public.jacc_chat_threads;
create trigger trg_jacc_chat_threads_updated_at
before update on public.jacc_chat_threads
for each row execute function public.jacc_chat_touch_updated_at();

drop trigger if exists trg_jacc_chat_receipts_updated_at
  on public.jacc_chat_read_receipts;
create trigger trg_jacc_chat_receipts_updated_at
before update on public.jacc_chat_read_receipts
for each row execute function public.jacc_chat_touch_updated_at();

create or replace function public.jacc_chat_actor_is_admin(p_actor_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_profiles p
    where p.id = p_actor_id
      and p.account_active
      and p.role in ('admin', 'lead_broker')
  );
$$;

create or replace function public.jacc_chat_can_access(
  p_thread_id uuid,
  p_actor_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_chat_threads t
    join public.jacc_profiles p on p.id = p_actor_id
    where t.id = p_thread_id
      and p.account_active
      and (
        t.customer_id = p_actor_id
        or t.broker_id = p_actor_id
        or p.role in ('admin', 'lead_broker')
      )
  );
$$;

create or replace function public.jacc_chat_open_by_request_code(
  p_request_code text,
  p_actor_id uuid
)
returns table (
  thread_id uuid,
  request_id uuid,
  request_code text,
  customer_id uuid,
  broker_id uuid,
  status public.jacc_chat_status,
  last_message_at timestamptz,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.jacc_service_requests%rowtype;
  v_actor public.jacc_profiles%rowtype;
begin
  select * into v_actor
  from public.jacc_profiles
  where id = p_actor_id;

  if not found or not v_actor.account_active then
    raise exception 'CHAT_ACTOR_NOT_ACTIVE';
  end if;

  select * into v_request
  from public.jacc_service_requests
  where upper(request_code) = upper(trim(p_request_code))
  limit 1;

  if not found then
    raise exception 'CHAT_REQUEST_NOT_FOUND';
  end if;

  if v_request.assigned_broker_id is null then
    raise exception 'CHAT_REQUEST_HAS_NO_ASSIGNED_BROKER';
  end if;

  if p_actor_id <> v_request.customer_id
     and p_actor_id <> v_request.assigned_broker_id
     and v_actor.role not in ('admin', 'lead_broker') then
    raise exception 'CHAT_ACCESS_DENIED';
  end if;

  insert into public.jacc_chat_threads (
    request_id,
    customer_id,
    broker_id
  ) values (
    v_request.id,
    v_request.customer_id,
    v_request.assigned_broker_id
  )
  on conflict (request_id) do update
  set customer_id = excluded.customer_id,
      broker_id = excluded.broker_id,
      updated_at = now();

  return query
  select
    t.id,
    t.request_id,
    v_request.request_code,
    t.customer_id,
    t.broker_id,
    t.status,
    t.last_message_at,
    t.created_at
  from public.jacc_chat_threads t
  where t.request_id = v_request.id;
end;
$$;

create or replace function public.jacc_chat_list_threads(
  p_actor_id uuid,
  p_limit integer default 50
)
returns table (
  thread_id uuid,
  request_id uuid,
  request_code text,
  status public.jacc_chat_status,
  counterpart_name text,
  last_message_at timestamptz,
  unread_count bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_limit integer := greatest(1, least(coalesce(p_limit, 50), 100));
  v_actor public.jacc_profiles%rowtype;
begin
  select * into v_actor
  from public.jacc_profiles
  where id = p_actor_id;

  if not found or not v_actor.account_active then
    raise exception 'CHAT_ACTOR_NOT_ACTIVE';
  end if;

  return query
  select
    t.id,
    t.request_id,
    r.request_code,
    t.status,
    case
      when p_actor_id = t.customer_id then bp.display_name
      when p_actor_id = t.broker_id then cp.display_name
      else cp.display_name || ' ↔ ' || bp.display_name
    end as counterpart_name,
    t.last_message_at,
    (
      select count(*)
      from public.jacc_chat_messages m
      left join public.jacc_chat_read_receipts rr
        on rr.thread_id = t.id
       and rr.profile_id = p_actor_id
      where m.thread_id = t.id
        and m.deleted_at is null
        and m.sender_id <> p_actor_id
        and m.created_at > coalesce(rr.last_read_at, '-infinity'::timestamptz)
    ) as unread_count
  from public.jacc_chat_threads t
  join public.jacc_service_requests r on r.id = t.request_id
  join public.jacc_profiles cp on cp.id = t.customer_id
  join public.jacc_profiles bp on bp.id = t.broker_id
  where t.customer_id = p_actor_id
     or t.broker_id = p_actor_id
     or v_actor.role in ('admin', 'lead_broker')
  order by t.last_message_at desc nulls last, t.created_at desc
  limit v_limit;
end;
$$;

create or replace function public.jacc_chat_list_messages(
  p_thread_id uuid,
  p_actor_id uuid,
  p_before timestamptz default null,
  p_limit integer default 50
)
returns table (
  message_id uuid,
  sender_id uuid,
  sender_role text,
  source public.jacc_chat_source,
  message_type public.jacc_chat_message_type,
  body text,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_limit integer := greatest(1, least(coalesce(p_limit, 50), 100));
begin
  if not public.jacc_chat_can_access(p_thread_id, p_actor_id) then
    raise exception 'CHAT_ACCESS_DENIED';
  end if;

  return query
  select
    m.id,
    m.sender_id,
    m.sender_role,
    m.source,
    m.message_type,
    m.body,
    m.created_at
  from public.jacc_chat_messages m
  where m.thread_id = p_thread_id
    and m.deleted_at is null
    and (p_before is null or m.created_at < p_before)
  order by m.created_at desc, m.id desc
  limit v_limit;
end;
$$;

create or replace function public.jacc_chat_send_text(
  p_thread_id uuid,
  p_actor_id uuid,
  p_client_message_id uuid,
  p_body text,
  p_source public.jacc_chat_source default 'app'
)
returns table (
  message_id uuid,
  sender_id uuid,
  sender_role text,
  source public.jacc_chat_source,
  message_type public.jacc_chat_message_type,
  body text,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_thread public.jacc_chat_threads%rowtype;
  v_body text := trim(coalesce(p_body, ''));
  v_role text;
  v_message public.jacc_chat_messages%rowtype;
  v_inserted boolean := false;
begin
  select * into v_thread
  from public.jacc_chat_threads
  where id = p_thread_id
  for update;

  if not found then
    raise exception 'CHAT_THREAD_NOT_FOUND';
  end if;

  if v_thread.status <> 'open' then
    raise exception 'CHAT_THREAD_CLOSED';
  end if;

  if p_actor_id = v_thread.customer_id then
    v_role := 'customer';
  elsif p_actor_id = v_thread.broker_id then
    v_role := 'broker';
  else
    raise exception 'CHAT_SEND_DENIED';
  end if;

  if char_length(v_body) < 1 or char_length(v_body) > 4000 then
    raise exception 'CHAT_MESSAGE_LENGTH_INVALID';
  end if;

  insert into public.jacc_chat_messages (
    thread_id,
    sender_id,
    sender_role,
    source,
    message_type,
    body,
    client_message_id
  ) values (
    p_thread_id,
    p_actor_id,
    v_role,
    p_source,
    'text',
    v_body,
    p_client_message_id
  )
  on conflict (thread_id, sender_id, client_message_id) do nothing
  returning * into v_message;

  if found then
    v_inserted := true;
  else
    select * into v_message
    from public.jacc_chat_messages
    where thread_id = p_thread_id
      and sender_id = p_actor_id
      and client_message_id = p_client_message_id;
  end if;

  if v_inserted then
    update public.jacc_chat_threads
    set last_message_id = v_message.id,
        last_message_at = v_message.created_at,
        updated_at = now()
    where id = p_thread_id;

    update public.jacc_service_requests
    set customer_last_reply_at = case
          when v_role = 'customer' then now()
          else customer_last_reply_at
        end,
        broker_last_reply_at = case
          when v_role = 'broker' then now()
          else broker_last_reply_at
        end,
        last_meaningful_update_at = now(),
        updated_at = now()
    where id = v_thread.request_id;

    insert into public.jacc_request_updates (
      request_id,
      actor_id,
      update_type,
      content,
      meaningful
    ) values (
      v_thread.request_id,
      p_actor_id,
      'app_chat_message',
      jsonb_build_object(
        'threadId', p_thread_id,
        'messageId', v_message.id,
        'source', p_source,
        'senderRole', v_role
      ),
      true
    );
  end if;

  return query
  select
    v_message.id,
    v_message.sender_id,
    v_message.sender_role,
    v_message.source,
    v_message.message_type,
    v_message.body,
    v_message.created_at;
end;
$$;

create or replace function public.jacc_chat_mark_read(
  p_thread_id uuid,
  p_actor_id uuid,
  p_last_read_message_id uuid default null
)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  v_read_at timestamptz := now();
  v_unread bigint;
begin
  if not public.jacc_chat_can_access(p_thread_id, p_actor_id) then
    raise exception 'CHAT_ACCESS_DENIED';
  end if;

  if p_last_read_message_id is not null then
    select created_at into v_read_at
    from public.jacc_chat_messages
    where id = p_last_read_message_id
      and thread_id = p_thread_id
      and deleted_at is null;

    if not found then
      raise exception 'CHAT_MESSAGE_NOT_FOUND';
    end if;
  end if;

  insert into public.jacc_chat_read_receipts (
    thread_id,
    profile_id,
    last_read_message_id,
    last_read_at
  ) values (
    p_thread_id,
    p_actor_id,
    p_last_read_message_id,
    v_read_at
  )
  on conflict (thread_id, profile_id) do update
  set last_read_message_id = excluded.last_read_message_id,
      last_read_at = greatest(
        public.jacc_chat_read_receipts.last_read_at,
        excluded.last_read_at
      ),
      updated_at = now();

  select count(*) into v_unread
  from public.jacc_chat_messages m
  where m.thread_id = p_thread_id
    and m.deleted_at is null
    and m.sender_id <> p_actor_id
    and m.created_at > v_read_at;

  return v_unread;
end;
$$;

create or replace function public.jacc_chat_close(
  p_thread_id uuid,
  p_actor_id uuid,
  p_reason text default null
)
returns public.jacc_chat_status
language plpgsql
security definer
set search_path = public
as $$
declare
  v_thread public.jacc_chat_threads%rowtype;
  v_reason text := nullif(trim(coalesce(p_reason, '')), '');
  v_was_open boolean;
begin
  if not public.jacc_chat_can_access(p_thread_id, p_actor_id) then
    raise exception 'CHAT_ACCESS_DENIED';
  end if;

  if v_reason is not null and char_length(v_reason) > 500 then
    raise exception 'CHAT_CLOSE_REASON_TOO_LONG';
  end if;

  select * into v_thread
  from public.jacc_chat_threads
  where id = p_thread_id
  for update;

  if not found then
    raise exception 'CHAT_THREAD_NOT_FOUND';
  end if;

  v_was_open := v_thread.status = 'open';

  update public.jacc_chat_threads
  set status = 'closed',
      closed_by = coalesce(closed_by, p_actor_id),
      closed_reason = coalesce(closed_reason, v_reason),
      closed_at = coalesce(closed_at, now()),
      updated_at = now()
  where id = p_thread_id;

  if v_was_open then
    update public.jacc_service_requests
    set last_meaningful_update_at = now(),
        updated_at = now()
    where id = v_thread.request_id;

    insert into public.jacc_request_updates (
      request_id,
      actor_id,
      update_type,
      content,
      meaningful
    ) values (
      v_thread.request_id,
      p_actor_id,
      'app_chat_closed',
      jsonb_build_object(
        'threadId', p_thread_id,
        'reasonProvided', v_reason is not null
      ),
      true
    );

    insert into public.jacc_audit_logs (
      actor_id,
      action,
      entity_type,
      entity_id,
      new_data
    ) values (
      p_actor_id,
      'APP_CHAT_CLOSED',
      'jacc_chat_thread',
      p_thread_id::text,
      jsonb_build_object(
        'requestId', v_thread.request_id,
        'reasonProvided', v_reason is not null
      )
    );
  end if;

  return 'closed'::public.jacc_chat_status;
end;
$$;

revoke all on function public.jacc_chat_actor_is_admin(uuid) from public, anon, authenticated;
revoke all on function public.jacc_chat_can_access(uuid, uuid) from public, anon, authenticated;
revoke all on function public.jacc_chat_open_by_request_code(text, uuid) from public, anon, authenticated;
revoke all on function public.jacc_chat_list_threads(uuid, integer) from public, anon, authenticated;
revoke all on function public.jacc_chat_list_messages(uuid, uuid, timestamptz, integer) from public, anon, authenticated;
revoke all on function public.jacc_chat_send_text(uuid, uuid, uuid, text, public.jacc_chat_source) from public, anon, authenticated;
revoke all on function public.jacc_chat_mark_read(uuid, uuid, uuid) from public, anon, authenticated;
revoke all on function public.jacc_chat_close(uuid, uuid, text) from public, anon, authenticated;

grant execute on function public.jacc_chat_actor_is_admin(uuid) to service_role;
grant execute on function public.jacc_chat_can_access(uuid, uuid) to service_role;
grant execute on function public.jacc_chat_open_by_request_code(text, uuid) to service_role;
grant execute on function public.jacc_chat_list_threads(uuid, integer) to service_role;
grant execute on function public.jacc_chat_list_messages(uuid, uuid, timestamptz, integer) to service_role;
grant execute on function public.jacc_chat_send_text(uuid, uuid, uuid, text, public.jacc_chat_source) to service_role;
grant execute on function public.jacc_chat_mark_read(uuid, uuid, uuid) to service_role;
grant execute on function public.jacc_chat_close(uuid, uuid, text) to service_role;

commit;
