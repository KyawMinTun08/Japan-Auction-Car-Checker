-- Phase 3 disposable chat client E2E acceptance.
-- REVIEW/STAGING ONLY. Synthetic identities; no production/customer data.
\set ON_ERROR_STOP on

insert into public.jacc_profiles (id, role, account_active) values
('11111111-1111-1111-1111-111111111111','customer',true),
('22222222-2222-2222-2222-222222222222','customer',true),
('33333333-3333-3333-3333-333333333333','broker',true),
('44444444-4444-4444-4444-444444444444','broker',true),
('55555555-5555-5555-5555-555555555555','admin',true);

insert into public.jacc_memberships (user_id, plan, service_channel, status, starts_at, expires_at) values
('11111111-1111-1111-1111-111111111111','premium','app','ACTIVE',now()-interval '1 day',now()+interval '30 days'),
('22222222-2222-2222-2222-222222222222','premium','app','ACTIVE',now()-interval '40 days',now()-interval '1 day');

insert into public.jacc_broker_profiles (user_id, account_status) values
('33333333-3333-3333-3333-333333333333','active'),
('44444444-4444-4444-4444-444444444444','suspended');

insert into public.jacc_service_requests (id, customer_id, assigned_broker_id) values
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','11111111-1111-1111-1111-111111111111','33333333-3333-3333-3333-333333333333'),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2','22222222-2222-2222-2222-222222222222',null),
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3','11111111-1111-1111-1111-111111111111','44444444-4444-4444-4444-444444444444');

insert into public.jacc_conversations (conversation_id, request_id, customer_id, broker_id, status) values
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','11111111-1111-1111-1111-111111111111','33333333-3333-3333-3333-333333333333','active'),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2','22222222-2222-2222-2222-222222222222',null,'active'),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3','11111111-1111-1111-1111-111111111111','44444444-4444-4444-4444-444444444444','active');

insert into public.jacc_conversation_participants (id, conversation_id, profile_id, participant_role) values
('cccccccc-cccc-cccc-cccc-ccccccccccc1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','11111111-1111-1111-1111-111111111111','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc2','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','33333333-3333-3333-3333-333333333333','broker'),
('cccccccc-cccc-cccc-cccc-ccccccccccc3','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2','22222222-2222-2222-2222-222222222222','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc4','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','11111111-1111-1111-1111-111111111111','customer'),
('cccccccc-cccc-cccc-cccc-ccccccccccc5','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','44444444-4444-4444-4444-444444444444','broker');

-- Customer sends a browser/app message.
set role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false);
insert into public.jacc_messages (
  id, conversation_id, request_id, sender_id, sender_role, message_type,
  message_text, transport, client_message_id, status
) values (
  'dddddddd-dddd-dddd-dddd-ddddddddddd1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1','11111111-1111-1111-1111-111111111111',
  'customer','text','client e2e hello','app','client-e2e-1','sent'
);

-- Duplicate client_message_id must fail.
do $$ declare blocked boolean := false; begin
  begin
    insert into public.jacc_messages (
      conversation_id, request_id, sender_id, sender_role, message_type,
      message_text, transport, client_message_id, status
    ) values (
      'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1',
      '11111111-1111-1111-1111-111111111111','customer','text',
      'duplicate','app','client-e2e-1','sent'
    );
  exception when others then blocked := true; end;
  if not blocked then raise exception 'DUPLICATE_CLIENT_MESSAGE_ID_ACCEPTED'; end if;
end $$;
reset role;

-- Active broker reads the message and writes/updates own receipt.
set role authenticated;
select set_config('request.jwt.claim.sub','33333333-3333-3333-3333-333333333333',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_messages
   where id='dddddddd-dddd-dddd-dddd-ddddddddddd1';
  if n <> 1 then raise exception 'BROKER_MESSAGE_READ_FAILED'; end if;
end $$;
insert into public.jacc_message_read_receipts (
  message_id, conversation_id, participant_id, delivered_at
) values (
  'dddddddd-dddd-dddd-dddd-ddddddddddd1','bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1',
  'cccccccc-cccc-cccc-cccc-ccccccccccc2',now()
);
update public.jacc_message_read_receipts
   set read_at=now()
 where message_id='dddddddd-dddd-dddd-dddd-ddddddddddd1'
   and participant_id='cccccccc-cccc-cccc-cccc-ccccccccccc2';
do $$ declare n int; begin
  select count(*) into n from public.jacc_message_read_receipts
   where message_id='dddddddd-dddd-dddd-dddd-ddddddddddd1'
     and participant_id='cccccccc-cccc-cccc-cccc-ccccccccccc2'
     and read_at is not null;
  if n <> 1 then raise exception 'BROKER_READ_RECEIPT_FAILED'; end if;
end $$;
reset role;

-- Expired customer may not send.
set role authenticated;
select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',false);
do $$ declare blocked boolean := false; begin
  begin
    insert into public.jacc_messages (
      conversation_id, request_id, sender_id, sender_role, message_type,
      message_text, transport, client_message_id, status
    ) values (
      'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2',
      '22222222-2222-2222-2222-222222222222','customer','text',
      'expired should fail','app','expired-e2e-1','sent'
    );
  exception when others then blocked := true; end;
  if not blocked then raise exception 'EXPIRED_CUSTOMER_SEND_ACCEPTED'; end if;
end $$;
reset role;

-- Suspended broker may not send despite assignment.
set role authenticated;
select set_config('request.jwt.claim.sub','44444444-4444-4444-4444-444444444444',false);
do $$ declare blocked boolean := false; begin
  begin
    insert into public.jacc_messages (
      conversation_id, request_id, sender_id, sender_role, message_type,
      message_text, transport, client_message_id, status
    ) values (
      'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb3','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3',
      '44444444-4444-4444-4444-444444444444','broker','text',
      'suspended should fail','app','suspended-e2e-1','sent'
    );
  exception when others then blocked := true; end;
  if not blocked then raise exception 'SUSPENDED_BROKER_SEND_ACCEPTED'; end if;
end $$;
reset role;

-- Admin can inspect all conversations; anonymous cannot inspect any chat table.
set role authenticated;
select set_config('request.jwt.claim.sub','55555555-5555-5555-5555-555555555555',false);
do $$ declare n int; begin
  select count(*) into n from public.jacc_conversations;
  if n <> 3 then raise exception 'ADMIN_OVERSIGHT_FAILED'; end if;
end $$;
reset role;

set role anon;
do $$ declare blocked boolean := false; begin
  begin perform count(*) from public.jacc_messages; exception when insufficient_privilege then blocked := true; end;
  if not blocked then raise exception 'ANON_CHAT_READ_ACCEPTED'; end if;
end $$;
reset role;

select 'JACC_CHAT_CLIENT_E2E_PASS' as result;
