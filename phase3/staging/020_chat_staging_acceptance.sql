-- Ephemeral acceptance matrix for Phase 3 chat schema/security.
-- Runs only in disposable CI PostgreSQL. No production/customer data.

\set ON_ERROR_STOP on

-- Stable synthetic identities.
insert into public.jacc_profiles (id, role, account_active) values
('11111111-1111-1111-1111-111111111111','customer',true),
('22222222-2222-2222-2222-222222222222','customer',true),
('33333333-3333-3333-3333-333333333333','broker',true),
('44444444-4444-4444-4444-444444444444','broker',true),
('55555555-5555-5555-5555-555555555555','admin',true),
('66666666-6666-6666-6666-666666666666','customer',true);

insert into public.jacc_memberships (user_id, plan, service_channel, status, starts_at, expires_at) values
('11111111-1111-1111-1111-111111111111','premium','app','ACTIVE',now() - interval '1 day',now() + interval '30 days'),
('22222222-2222-2222-2222-222222222222','premium','app','ACTIVE',now() - interval '40 days',now() - interval '1 day'),
('66666666-6666-6666-6666-666666666666','premium','app','ACTIVE',now() - interval '1 day',now() + interval '30 days');

insert into public.jacc_broker_profiles (user_id, account_status) values
('33333333-3333-3333-3333-333333333333','active'),
('44444444-4444-4444-4444-444444444444','suspended');

insert into public.jacc_service_requests (id, customer_id, assigned_broker_id) values
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','11111111-1111-1111-1111-111111111111','33333333-3333-3333-3333-333333333333'),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2','22222222-2222-2222-2222-222222222222',null),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3','66666666-6666-6666-6666-666666666666','44444444-4444-4444-4444-444444444444');

insert into public.jacc_conversations (conversation_id, request_id, customer_id, broker_id, status) values
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','11111111-1111-1111-1111-111111111111','33333333-3333-3333-3333-333333333333','active'),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2','22222222-2222-2222-2222-222222222222',null,'active'),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3','66666666-6666-6666-6666-666666666666','44444444-4444-4444-4444-444444444444','active');

insert into public.jacc_conversation_participants (id, conversation_id, profile_id, participant_role) values
('cccccccc-cccc-cccc-cccc-ccccccccccc1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','11111111-1111-1111-1111-111111111111','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc2','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','33333333-3333-3333-3333-333333333333','broker'),
('cccccccc-cccc-cccc-cccc-ccccccccccc3','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2','22222222-2222-2222-2222-222222222222','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc4','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','66666666-6666-6666-6666-666666666666','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc5','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','44444444-4444-4444-4444-444444444444','broker');

-- Structural gates: RLS on every chat table and anon has no table SELECT.
do $$
declare
  t text;
  enabled boolean;
begin
  foreach t in array array[
    'jacc_conversations','jacc_conversation_participants','jacc_messages',
    'jacc_message_attachments','jacc_message_read_receipts',
    'jacc_conversation_events','jacc_conversation_reports'
  ] loop
    select c.relrowsecurity into enabled
    from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname=t;
    if enabled is distinct from true then
      raise exception 'RLS_NOT_ENABLED:%', t;
    end if;
    if has_table_privilege('anon', format('public.%I',t), 'SELECT') then
      raise exception 'ANON_SELECT_GRANTED:%', t;
    end if;
  end loop;
end $$;

-- Active Premium/App customer: only own conversation, can send app text.
set role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 1 then raise exception 'ACTIVE_CUSTOMER_EXPECTED_1_GOT_%', n; end if;
end $$;

insert into public.jacc_messages (
  conversation_id, request_id, sender_id, sender_role, message_type,
  message_text, transport, client_message_id, status
) values (
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
  '11111111-1111-1111-1111-111111111111','customer','text',
  'staging hello','app','staging-customer-1','sent'
);

-- Browser client must not be able to forge Telegram transport.
do $$ declare failed boolean := false; begin
  begin
    insert into public.jacc_messages (
      conversation_id, request_id, sender_id, sender_role, message_type,
      message_text, transport, client_message_id, external_message_id, status
    ) values (
      'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
      '11111111-1111-1111-1111-111111111111','customer','text',
      'forged telegram','telegram','staging-forged-1','tg-should-not-pass','sent'
    );
  exception when others then
    failed := true;
  end;
  if not failed then raise exception 'FORGED_TELEGRAM_INSERT_WAS_ACCEPTED'; end if;
end $$;
reset role;

-- Expired customer: zero readable conversations.
set role authenticated;
select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 0 then raise exception 'EXPIRED_CUSTOMER_EXPECTED_0_GOT_%', n; end if;
end $$;
reset role;

-- Active broker: assigned conversation visible.
set role authenticated;
select set_config('request.jwt.claim.sub','33333333-3333-3333-3333-333333333333',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 1 then raise exception 'ACTIVE_BROKER_EXPECTED_1_GOT_%', n; end if;
end $$;
reset role;

-- Suspended broker: assignment is not enough; entitlement must deny.
set role authenticated;
select set_config('request.jwt.claim.sub','44444444-4444-4444-4444-444444444444',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 0 then raise exception 'SUSPENDED_BROKER_EXPECTED_0_GOT_%', n; end if;
end $$;
reset role;

-- Admin oversight: all three conversations visible without participant rows.
set role authenticated;
select set_config('request.jwt.claim.sub','55555555-5555-5555-5555-555555555555',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 3 then raise exception 'ADMIN_EXPECTED_3_GOT_%', n; end if;
end $$;
reset role;

-- Event audit log must remain append-only.
insert into public.jacc_conversation_events (conversation_id, request_id, actor_id, event_type)
values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
        '55555555-5555-5555-5555-555555555555','staging_test');
do $$ declare failed boolean := false; begin
  begin
    update public.jacc_conversation_events set event_type='mutated';
  exception when others then
    failed := true;
  end;
  if not failed then raise exception 'EVENT_APPEND_ONLY_GUARD_FAILED'; end if;
end $$;

-- Cross-conversation attachment metadata must be rejected.
insert into public.jacc_messages (
  id, conversation_id, request_id, sender_id, sender_role, message_type,
  message_text, transport, client_message_id, status
) values (
  'dddddddd-dddd-dddd-dddd-ddddddddddd1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','55555555-5555-5555-5555-555555555555',
  'admin','text','server fixture','system',null,'sent'
);
do $$ declare failed boolean := false; begin
  begin
    insert into public.jacc_message_attachments (
      message_id, conversation_id, attachment_url, mime_type, size_bytes
    ) values (
      'dddddddd-dddd-dddd-dddd-ddddddddddd1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3',
      'private/staging/test.jpg','image/jpeg',1024
    );
  exception when others then
    failed := true;
  end;
  if not failed then raise exception 'CROSS_CONVERSATION_ATTACHMENT_ACCEPTED'; end if;
end $$;

select 'JACC_CHAT_STAGING_ACCEPTANCE_PASS' as result;
