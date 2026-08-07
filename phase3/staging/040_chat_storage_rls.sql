-- Disposable acceptance for 012_chat_storage_security.sql.
-- Synthetic identities only. Never run against production.

\set ON_ERROR_STOP on

-- Synthetic principals.
insert into public.jacc_profiles (id, role, account_active) values
('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','customer',true),
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','broker',true),
('cccccccc-cccc-4ccc-8ccc-cccccccccccc','admin',true),
('dddddddd-dddd-4ddd-8ddd-dddddddddddd','customer',true),
('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','broker',true),
('99999999-9999-4999-8999-999999999999','customer',true);

insert into public.jacc_memberships (user_id,plan,service_channel,status,starts_at,expires_at) values
('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','premium','app','ACTIVE',now()-interval '1 day',now()+interval '30 days'),
('dddddddd-dddd-4ddd-8ddd-dddddddddddd','premium','app','ACTIVE',now()-interval '60 days',now()-interval '1 day'),
('99999999-9999-4999-8999-999999999999','premium','app','ACTIVE',now()-interval '1 day',now()+interval '30 days');

insert into public.jacc_broker_profiles (user_id,account_status) values
('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','active'),
('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','suspended');

insert into public.jacc_service_requests (id,customer_id,assigned_broker_id) values
('f1111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),
('f2222222-2222-4222-8222-222222222222','99999999-9999-4999-8999-999999999999','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'),
('f3333333-3333-4333-8333-333333333333','dddddddd-dddd-4ddd-8ddd-dddddddddddd','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');

insert into public.jacc_conversations (conversation_id,request_id,customer_id,broker_id,status) values
('11111111-1111-4111-8111-111111111111','f1111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','active'),
('44444444-4444-4444-8444-444444444444','f2222222-2222-4222-8222-222222222222','99999999-9999-4999-8999-999999999999','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','active'),
('77777777-7777-4777-8777-777777777777','f3333333-3333-4333-8333-333333333333','dddddddd-dddd-4ddd-8ddd-dddddddddddd','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','active');

insert into public.jacc_conversation_participants (conversation_id,profile_id,participant_role) values
('11111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','customer'),
('11111111-1111-4111-8111-111111111111','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','broker'),
('44444444-4444-4444-8444-444444444444','99999999-9999-4999-8999-999999999999','customer'),
('44444444-4444-4444-8444-444444444444','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','broker'),
('77777777-7777-4777-8777-777777777777','dddddddd-dddd-4ddd-8ddd-dddddddddddd','customer'),
('77777777-7777-4777-8777-777777777777','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','broker');

insert into public.jacc_messages
(id,conversation_id,request_id,sender_id,sender_role,message_type,message_text,transport,client_message_id,status)
values
('22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111','f1111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','customer','photo',null,'app','storage-customer-1','sent'),
('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','f1111111-1111-4111-8111-111111111111','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','broker','photo',null,'app','storage-broker-1','sent'),
('55555555-5555-4555-8555-555555555555','44444444-4444-4444-8444-444444444444','f2222222-2222-4222-8222-222222222222','99999999-9999-4999-8999-999999999999','customer','photo',null,'app','storage-other-1','sent'),
('66666666-6666-4666-8666-666666666666','44444444-4444-4444-8444-444444444444','f2222222-2222-4222-8222-222222222222','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','broker','photo',null,'app','storage-suspended-1','sent'),
('88888888-8888-4888-8888-888888888888','77777777-7777-4777-8777-777777777777','f3333333-3333-4333-8333-333333333333','dddddddd-dddd-4ddd-8ddd-dddddddddddd','customer','photo',null,'app','storage-expired-1','sent');

-- Bucket contract must be private and bounded.
do $$
begin
  if not exists (
    select 1 from storage.buckets
    where id='jacc-chat-attachments'
      and public=false
      and file_size_limit=5242880
      and allowed_mime_types @> array['image/jpeg','image/png','image/webp']::text[]
  ) then raise exception 'STORAGE_BUCKET_CONTRACT_FAILED'; end if;

  if (select count(*) from pg_policies where schemaname='storage' and tablename='objects' and policyname like 'jacc_chat_storage_%') <> 2 then
    raise exception 'STORAGE_POLICY_COUNT_FAILED';
  end if;

  if has_table_privilege('anon','storage.objects','SELECT') or has_table_privilege('anon','storage.objects','INSERT') then
    raise exception 'ANON_STORAGE_PRIVILEGE_FAILED';
  end if;

  if has_table_privilege('authenticated','storage.objects','UPDATE') or has_table_privilege('authenticated','storage.objects','DELETE') then
    raise exception 'AUTH_STORAGE_MUTATION_PRIVILEGE_FAILED';
  end if;
end $$;

-- Seed an object in the expired member's own conversation as service-side data,
-- so read denial proves entitlement enforcement rather than non-participation.
insert into storage.objects (bucket_id,name,metadata)
values (
  'jacc-chat-attachments',
  '77777777-7777-4777-8777-777777777777/88888888-8888-4888-8888-888888888888/expired_seed_01.jpg',
  '{"mimetype":"image/jpeg","size":"512"}'::jsonb
);

set role authenticated;
select set_config('request.jwt.claim.sub','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',false);

-- Positive upload: active Premium/App customer owns the app message.
insert into storage.objects (bucket_id,name,metadata)
values (
  'jacc-chat-attachments',
  '11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222/photo_object_0001.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);

do $$ begin
  if (select count(*) from storage.objects where bucket_id='jacc-chat-attachments') <> 1 then
    raise exception 'CUSTOMER_STORAGE_READ_FAILED';
  end if;
end $$;

select set_config('request.jwt.claim.sub','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',false);
do $$ begin
  if (select count(*) from storage.objects where bucket_id='jacc-chat-attachments') <> 2 then
    raise exception 'BROKER_STORAGE_READ_FAILED';
  end if;
end $$;

insert into storage.objects (bucket_id,name,metadata)
values (
  'jacc-chat-attachments',
  '11111111-1111-4111-8111-111111111111/33333333-3333-4333-8333-333333333333/broker_object_01.webp',
  '{"mimetype":"image/webp","size":"2048"}'::jsonb
);

create or replace function pg_temp.expect_storage_insert_denied(p_bucket text,p_name text,p_metadata jsonb)
returns void language plpgsql as $$
begin
  begin
    insert into storage.objects(bucket_id,name,metadata) values(p_bucket,p_name,p_metadata);
    raise exception 'EXPECTED_STORAGE_INSERT_DENIAL_NOT_RAISED';
  exception
    when insufficient_privilege then null;
  end;
end $$;

select set_config('request.jwt.claim.sub','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',false);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '11111111-1111-4111-8111-111111111111/33333333-3333-4333-8333-333333333333/cross_message_01.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '44444444-4444-4444-8444-444444444444/55555555-5555-4555-8555-555555555555/cross_conversation_01.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);
select pg_temp.expect_storage_insert_denied(
  'public-bucket',
  '11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222/wrong_bucket_01.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments','https://example.com/public.jpg','{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222/wrong_mime_01.jpg',
  '{"mimetype":"application/pdf","size":"1024"}'::jsonb
);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '11111111-1111-4111-8111-111111111111/22222222-2222-4222-8222-222222222222/too_large_0001.jpg',
  '{"mimetype":"image/jpeg","size":"5242881"}'::jsonb
);

-- Expired customer is the actual participant and message owner, but entitlement expiry must deny both read and upload.
select set_config('request.jwt.claim.sub','dddddddd-dddd-4ddd-8ddd-dddddddddddd',false);
do $$ begin
  if exists(
    select 1 from storage.objects
    where bucket_id='jacc-chat-attachments'
      and name like '77777777-7777-4777-8777-777777777777/%'
  ) then
    raise exception 'EXPIRED_CUSTOMER_STORAGE_READ_FAILED';
  end if;
end $$;
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '77777777-7777-4777-8777-777777777777/88888888-8888-4888-8888-888888888888/expired_user_01.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);

select set_config('request.jwt.claim.sub','eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',false);
select pg_temp.expect_storage_insert_denied(
  'jacc-chat-attachments',
  '44444444-4444-4444-8444-444444444444/66666666-6666-4666-8666-666666666666/suspended_0001.jpg',
  '{"mimetype":"image/jpeg","size":"1024"}'::jsonb
);

select set_config('request.jwt.claim.sub','cccccccc-cccc-4ccc-8ccc-cccccccccccc',false);
do $$ begin
  if (select count(*) from storage.objects where bucket_id='jacc-chat-attachments') <> 3 then
    raise exception 'ADMIN_STORAGE_READ_FAILED';
  end if;
end $$;

reset role;
select 'JACC_CHAT_STORAGE_RLS_PASS' as result;
