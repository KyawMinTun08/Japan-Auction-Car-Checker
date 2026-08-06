-- JACC Phase 3 migration: 011_chat_security.sql
-- REVIEW/STAGING ONLY. Run after 010_chat_architecture.sql.
-- Do not run against production until Phase 2 and Task 4 acceptance pass.

begin;

-- ---------------------------------------------------------------------------
-- ENTITLEMENT AND ACCESS HELPERS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_chat_profile_is_admin(p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_profiles p
    where p.id = p_profile_id
      and p.account_active
      and p.role in ('admin', 'lead_broker')
  );
$$;

create or replace function public.jacc_chat_customer_entitled(p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_profiles p
    join public.jacc_memberships m on m.user_id = p.id
    where p.id = p_profile_id
      and p.account_active
      and p.role = 'customer'
      and m.plan = 'premium'
      and m.service_channel = 'app'
      and upper(coalesce(m.status, '')) = 'ACTIVE'
      and m.starts_at <= now()
      and (m.expires_at is null or m.expires_at >= now())
  );
$$;

create or replace function public.jacc_chat_broker_entitled(p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_profiles p
    join public.jacc_broker_profiles b on b.user_id = p.id
    where p.id = p_profile_id
      and p.account_active
      and p.role in ('broker', 'lead_broker')
      and b.account_status in ('probation', 'active')
  );
$$;

create or replace function public.jacc_chat_profile_entitled(p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select
    public.jacc_chat_profile_is_admin(p_profile_id)
    or public.jacc_chat_customer_entitled(p_profile_id)
    or public.jacc_chat_broker_entitled(p_profile_id);
$$;

create or replace function public.jacc_chat_can_access_conversation(
  p_conversation_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select case
    when public.jacc_is_admin() then true
    else exists (
      select 1
      from public.jacc_conversation_participants cp
      where cp.conversation_id = p_conversation_id
        and cp.profile_id = public.jacc_current_profile_id()
        and cp.is_active
        and cp.left_at is null
        and public.jacc_chat_profile_entitled(cp.profile_id)
    )
  end;
$$;

create or replace function public.jacc_chat_can_send_to_conversation(
  p_conversation_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_conversations c
    where c.id = p_conversation_id
      and (
        (
          c.status in ('pending', 'active')
          and public.jacc_chat_can_access_conversation(c.id)
        )
        or (
          c.status = 'reported'
          and public.jacc_is_admin()
        )
      )
  );
$$;

create or replace function public.jacc_chat_sender_role_allowed(
  p_sender_role public.jacc_message_sender_role
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_profiles p
    where p.id = public.jacc_current_profile_id()
      and p.account_active
      and (
        (p.role = 'customer' and p_sender_role = 'customer')
        or (p.role = 'broker' and p_sender_role = 'broker')
        or (p.role = 'lead_broker' and p_sender_role in ('broker', 'admin'))
        or (p.role = 'admin' and p_sender_role = 'admin')
      )
  );
$$;

create or replace function public.jacc_chat_message_in_conversation(
  p_message_id uuid,
  p_conversation_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_messages m
    where m.id = p_message_id
      and m.conversation_id = p_conversation_id
  );
$$;

create or replace function public.jacc_chat_message_owned_by_current(
  p_message_id uuid,
  p_conversation_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_messages m
    where m.id = p_message_id
      and m.conversation_id = p_conversation_id
      and m.sender_id = public.jacc_current_profile_id()
      and m.transport = 'app'
  );
$$;

create or replace function public.jacc_chat_participant_owned_by_current(
  p_participant_id uuid,
  p_conversation_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.jacc_conversation_participants cp
    where cp.id = p_participant_id
      and cp.conversation_id = p_conversation_id
      and cp.profile_id = public.jacc_current_profile_id()
      and cp.is_active
      and cp.left_at is null
  );
$$;

create or replace function public.jacc_chat_report_target_valid(
  p_conversation_id uuid,
  p_reported_profile_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select p_reported_profile_id is null or exists (
    select 1
    from public.jacc_conversation_participants cp
    where cp.conversation_id = p_conversation_id
      and cp.profile_id = p_reported_profile_id
  );
$$;

-- ---------------------------------------------------------------------------
-- CROSS-TABLE INTEGRITY TRIGGERS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_chat_validate_participant()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_customer_id uuid;
  v_broker_id uuid;
  v_profile_role public.jacc_app_role;
begin
  select c.customer_id, c.broker_id
  into v_customer_id, v_broker_id
  from public.jacc_conversations c
  where c.id = new.conversation_id;

  if v_customer_id is null then
    raise exception 'CHAT_CONVERSATION_NOT_FOUND';
  end if;

  select p.role into v_profile_role
  from public.jacc_profiles p
  where p.id = new.profile_id;

  if new.participant_role = 'customer' and new.profile_id <> v_customer_id then
    raise exception 'CHAT_CUSTOMER_PARTICIPANT_MISMATCH';
  elsif new.participant_role = 'broker' and (
    v_broker_id is null or new.profile_id <> v_broker_id
  ) then
    raise exception 'CHAT_BROKER_PARTICIPANT_MISMATCH';
  elsif new.participant_role = 'admin' and v_profile_role not in ('admin', 'lead_broker') then
    raise exception 'CHAT_ADMIN_PARTICIPANT_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_participant
  on public.jacc_conversation_participants;
create trigger trg_jacc_chat_validate_participant
before insert or update of conversation_id, profile_id, participant_role
on public.jacc_conversation_participants
for each row execute function public.jacc_chat_validate_participant();

create or replace function public.jacc_chat_validate_message_security()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile_role public.jacc_app_role;
  v_is_participant boolean;
begin
  if new.reply_to_message_id is not null and not public.jacc_chat_message_in_conversation(
    new.reply_to_message_id,
    new.conversation_id
  ) then
    raise exception 'CHAT_REPLY_CONVERSATION_MISMATCH';
  end if;

  if new.transport = 'app' and new.external_message_id is not null then
    raise exception 'CHAT_APP_EXTERNAL_ID_FORBIDDEN';
  elsif new.transport = 'telegram' and new.external_message_id is null then
    raise exception 'CHAT_TELEGRAM_EXTERNAL_ID_REQUIRED';
  elsif new.transport = 'system' and (
    new.sender_role <> 'system' or new.sender_id is not null
  ) then
    raise exception 'CHAT_SYSTEM_SENDER_INVALID';
  end if;

  if new.sender_role = 'system' then
    if new.sender_id is not null then
      raise exception 'CHAT_SYSTEM_SENDER_INVALID';
    end if;
    return new;
  end if;

  if new.sender_id is null then
    raise exception 'CHAT_SENDER_REQUIRED';
  end if;

  select p.role into v_profile_role
  from public.jacc_profiles p
  where p.id = new.sender_id and p.account_active;

  if v_profile_role is null then
    raise exception 'CHAT_SENDER_INACTIVE';
  end if;

  if not (
    (v_profile_role = 'customer' and new.sender_role = 'customer')
    or (v_profile_role = 'broker' and new.sender_role = 'broker')
    or (v_profile_role = 'lead_broker' and new.sender_role in ('broker', 'admin'))
    or (v_profile_role = 'admin' and new.sender_role = 'admin')
  ) then
    raise exception 'CHAT_SENDER_ROLE_MISMATCH';
  end if;

  select exists (
    select 1
    from public.jacc_conversation_participants cp
    where cp.conversation_id = new.conversation_id
      and cp.profile_id = new.sender_id
      and cp.is_active
      and cp.left_at is null
  ) into v_is_participant;

  if not v_is_participant and v_profile_role not in ('admin', 'lead_broker') then
    raise exception 'CHAT_SENDER_NOT_PARTICIPANT';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_message_security
  on public.jacc_messages;
create trigger trg_jacc_chat_validate_message_security
before insert or update of conversation_id, sender_id, sender_role, transport,
  external_message_id, reply_to_message_id
on public.jacc_messages
for each row execute function public.jacc_chat_validate_message_security();

create or replace function public.jacc_chat_validate_attachment()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_conversation_id uuid;
begin
  select m.conversation_id into v_conversation_id
  from public.jacc_messages m
  where m.id = new.message_id;

  if v_conversation_id is null or v_conversation_id <> new.conversation_id then
    raise exception 'CHAT_ATTACHMENT_CONVERSATION_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_attachment
  on public.jacc_message_attachments;
create trigger trg_jacc_chat_validate_attachment
before insert or update of message_id, conversation_id
on public.jacc_message_attachments
for each row execute function public.jacc_chat_validate_attachment();

create or replace function public.jacc_chat_validate_receipt()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_message_conversation uuid;
  v_participant_conversation uuid;
begin
  select m.conversation_id into v_message_conversation
  from public.jacc_messages m
  where m.id = new.message_id;

  select cp.conversation_id into v_participant_conversation
  from public.jacc_conversation_participants cp
  where cp.id = new.participant_id;

  if v_message_conversation is null
     or v_participant_conversation is null
     or v_message_conversation <> new.conversation_id
     or v_participant_conversation <> new.conversation_id then
    raise exception 'CHAT_RECEIPT_CONVERSATION_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_receipt
  on public.jacc_message_read_receipts;
create trigger trg_jacc_chat_validate_receipt
before insert or update of message_id, conversation_id, participant_id
on public.jacc_message_read_receipts
for each row execute function public.jacc_chat_validate_receipt();

create or replace function public.jacc_chat_validate_report()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request_id uuid;
begin
  select c.request_id into v_request_id
  from public.jacc_conversations c
  where c.id = new.conversation_id;

  if v_request_id is null or v_request_id <> new.request_id then
    raise exception 'CHAT_REPORT_REQUEST_MISMATCH';
  end if;

  if new.message_id is not null and not public.jacc_chat_message_in_conversation(
    new.message_id,
    new.conversation_id
  ) then
    raise exception 'CHAT_REPORT_MESSAGE_MISMATCH';
  end if;

  if not public.jacc_chat_report_target_valid(
    new.conversation_id,
    new.reported_profile_id
  ) then
    raise exception 'CHAT_REPORT_TARGET_MISMATCH';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_jacc_chat_validate_report
  on public.jacc_conversation_reports;
create trigger trg_jacc_chat_validate_report
before insert or update of conversation_id, request_id, message_id, reported_profile_id
on public.jacc_conversation_reports
for each row execute function public.jacc_chat_validate_report();

create or replace function public.jacc_chat_reject_event_mutation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  raise exception 'CHAT_EVENT_LOG_IS_APPEND_ONLY';
end;
$$;

drop trigger if exists trg_jacc_chat_events_append_only
  on public.jacc_conversation_events;
create trigger trg_jacc_chat_events_append_only
before update or delete on public.jacc_conversation_events
for each row execute function public.jacc_chat_reject_event_mutation();

-- ---------------------------------------------------------------------------
-- PRIVILEGE BASELINE
-- ---------------------------------------------------------------------------

revoke all on table public.jacc_conversations from anon, authenticated;
revoke all on table public.jacc_conversation_participants from anon, authenticated;
revoke all on table public.jacc_messages from anon, authenticated;
revoke all on table public.jacc_message_attachments from anon, authenticated;
revoke all on table public.jacc_message_read_receipts from anon, authenticated;
revoke all on table public.jacc_conversation_events from anon, authenticated;
revoke all on table public.jacc_conversation_reports from anon, authenticated;

revoke all on sequence public.jacc_message_read_receipts_id_seq from anon, authenticated;

-- Client roles can only use the operations explicitly protected below.
grant select on table public.jacc_conversations to authenticated;
grant select on table public.jacc_conversation_participants to authenticated;
grant select, insert on table public.jacc_messages to authenticated;
grant select, insert on table public.jacc_message_attachments to authenticated;
grant select, insert on table public.jacc_message_read_receipts to authenticated;
grant update (delivered_at, read_at) on table public.jacc_message_read_receipts to authenticated;
grant select on table public.jacc_conversation_events to authenticated;
grant select, insert on table public.jacc_conversation_reports to authenticated;
grant usage, select on sequence public.jacc_message_read_receipts_id_seq to authenticated;

-- ---------------------------------------------------------------------------
-- ROW-LEVEL SECURITY POLICIES
-- ---------------------------------------------------------------------------

-- Conversations are created and changed only by trusted server operations.
drop policy if exists jacc_chat_conversations_select
  on public.jacc_conversations;
create policy jacc_chat_conversations_select
on public.jacc_conversations
for select
to authenticated
using (public.jacc_chat_can_access_conversation(id));

-- A customer/broker sees only their own participant record; admins may inspect all.
drop policy if exists jacc_chat_participants_select
  on public.jacc_conversation_participants;
create policy jacc_chat_participants_select
on public.jacc_conversation_participants
for select
to authenticated
using (
  public.jacc_is_admin()
  or (
    profile_id = public.jacc_current_profile_id()
    and public.jacc_chat_can_access_conversation(conversation_id)
  )
);

-- Message history is readable only by currently entitled participants/admins.
drop policy if exists jacc_chat_messages_select
  on public.jacc_messages;
create policy jacc_chat_messages_select
on public.jacc_messages
for select
to authenticated
using (public.jacc_chat_can_access_conversation(conversation_id));

-- App clients may create only their own app messages. Telegram/system relay remains server-only.
drop policy if exists jacc_chat_messages_insert_app
  on public.jacc_messages;
create policy jacc_chat_messages_insert_app
on public.jacc_messages
for insert
to authenticated
with check (
  public.jacc_chat_can_send_to_conversation(conversation_id)
  and sender_id = public.jacc_current_profile_id()
  and public.jacc_chat_sender_role_allowed(sender_role)
  and transport = 'app'
  and external_message_id is null
  and client_message_id is not null
  and status = 'sent'
  and failure_code is null
  and read_at is null
  and edited_at is null
  and deleted_at is null
  and attachment_url is null
  and (
    message_type in ('text', 'photo', 'voice', 'document')
    or (message_type = 'status' and public.jacc_is_admin())
  )
  and (
    reply_to_message_id is null
    or public.jacc_chat_message_in_conversation(
      reply_to_message_id,
      conversation_id
    )
  )
);

-- Attachment metadata is private and can be inserted only for the sender's own message.
drop policy if exists jacc_chat_attachments_select
  on public.jacc_message_attachments;
create policy jacc_chat_attachments_select
on public.jacc_message_attachments
for select
to authenticated
using (public.jacc_chat_can_access_conversation(conversation_id));

drop policy if exists jacc_chat_attachments_insert
  on public.jacc_message_attachments;
create policy jacc_chat_attachments_insert
on public.jacc_message_attachments
for insert
to authenticated
with check (
  status = 'pending'
  and attachment_url <> ''
  and attachment_url !~* '^https?://'
  and public.jacc_chat_can_send_to_conversation(conversation_id)
  and public.jacc_chat_message_owned_by_current(message_id, conversation_id)
);

-- Delivery/read receipts belong to the current participant only.
drop policy if exists jacc_chat_receipts_select
  on public.jacc_message_read_receipts;
create policy jacc_chat_receipts_select
on public.jacc_message_read_receipts
for select
to authenticated
using (
  public.jacc_is_admin()
  or public.jacc_chat_participant_owned_by_current(
    participant_id,
    conversation_id
  )
);

drop policy if exists jacc_chat_receipts_insert
  on public.jacc_message_read_receipts;
create policy jacc_chat_receipts_insert
on public.jacc_message_read_receipts
for insert
to authenticated
with check (
  public.jacc_chat_can_access_conversation(conversation_id)
  and public.jacc_chat_participant_owned_by_current(
    participant_id,
    conversation_id
  )
  and public.jacc_chat_message_in_conversation(message_id, conversation_id)
);

drop policy if exists jacc_chat_receipts_update
  on public.jacc_message_read_receipts;
create policy jacc_chat_receipts_update
on public.jacc_message_read_receipts
for update
to authenticated
using (
  public.jacc_chat_participant_owned_by_current(
    participant_id,
    conversation_id
  )
)
with check (
  public.jacc_chat_participant_owned_by_current(
    participant_id,
    conversation_id
  )
  and public.jacc_chat_message_in_conversation(message_id, conversation_id)
);

-- Conversation events are append-only and server-created; participants can read them.
drop policy if exists jacc_chat_events_select
  on public.jacc_conversation_events;
create policy jacc_chat_events_select
on public.jacc_conversation_events
for select
to authenticated
using (public.jacc_chat_can_access_conversation(conversation_id));

-- A participant can file a new report; only the reporter and admins can read it.
drop policy if exists jacc_chat_reports_select
  on public.jacc_conversation_reports;
create policy jacc_chat_reports_select
on public.jacc_conversation_reports
for select
to authenticated
using (
  public.jacc_is_admin()
  or reporter_id = public.jacc_current_profile_id()
);

drop policy if exists jacc_chat_reports_insert
  on public.jacc_conversation_reports;
create policy jacc_chat_reports_insert
on public.jacc_conversation_reports
for insert
to authenticated
with check (
  reporter_id = public.jacc_current_profile_id()
  and public.jacc_chat_can_access_conversation(conversation_id)
  and status = 'open'
  and reviewed_by is null
  and reviewed_at is null
  and resolution_note is null
  and public.jacc_chat_report_target_valid(
    conversation_id,
    reported_profile_id
  )
  and (
    message_id is null
    or public.jacc_chat_message_in_conversation(message_id, conversation_id)
  )
);

-- ---------------------------------------------------------------------------
-- FUNCTION EXECUTION BOUNDARY
-- ---------------------------------------------------------------------------

revoke all on function public.jacc_chat_profile_is_admin(uuid) from public;
revoke all on function public.jacc_chat_customer_entitled(uuid) from public;
revoke all on function public.jacc_chat_broker_entitled(uuid) from public;
revoke all on function public.jacc_chat_profile_entitled(uuid) from public;
revoke all on function public.jacc_chat_can_access_conversation(uuid) from public;
revoke all on function public.jacc_chat_can_send_to_conversation(uuid) from public;
revoke all on function public.jacc_chat_sender_role_allowed(public.jacc_message_sender_role) from public;
revoke all on function public.jacc_chat_message_in_conversation(uuid, uuid) from public;
revoke all on function public.jacc_chat_message_owned_by_current(uuid, uuid) from public;
revoke all on function public.jacc_chat_participant_owned_by_current(uuid, uuid) from public;
revoke all on function public.jacc_chat_report_target_valid(uuid, uuid) from public;

grant execute on function public.jacc_chat_profile_is_admin(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_customer_entitled(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_broker_entitled(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_profile_entitled(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_can_access_conversation(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_can_send_to_conversation(uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_sender_role_allowed(public.jacc_message_sender_role) to authenticated, service_role;
grant execute on function public.jacc_chat_message_in_conversation(uuid, uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_message_owned_by_current(uuid, uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_participant_owned_by_current(uuid, uuid) to authenticated, service_role;
grant execute on function public.jacc_chat_report_target_valid(uuid, uuid) to authenticated, service_role;

comment on function public.jacc_chat_customer_entitled(uuid) is
  'Requires active account plus active Premium/App membership within its validity window.';
comment on function public.jacc_chat_broker_entitled(uuid) is
  'Requires active account plus probation/active broker status; accepting_requests is not required for existing assignments.';
comment on policy jacc_chat_messages_insert_app on public.jacc_messages is
  'Prevents authenticated clients from forging Telegram/system messages or transport IDs.';

commit;
