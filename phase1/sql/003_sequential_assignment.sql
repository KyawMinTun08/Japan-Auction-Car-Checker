-- JACC Phase 1 migration part: 003_sequential_assignment.sql
-- Run migrations in filename order.

begin;

-- ---------------------------------------------------------------------------
-- SEQUENTIAL FAIR ASSIGNMENT
-- ---------------------------------------------------------------------------

create or replace function public.jacc_dispatch_next_offer(p_request_id uuid)
returns table (
  offer_id uuid,
  request_id uuid,
  request_code text,
  broker_id uuid,
  broker_code text,
  broker_telegram_user_id bigint,
  service_type public.jacc_service_type,
  service_channel public.jacc_service_channel,
  expires_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.jacc_service_requests%rowtype;
  v_broker public.jacc_broker_profiles%rowtype;
  v_sequence integer;
  v_offer public.jacc_request_offers%rowtype;
begin
  select * into v_request
  from public.jacc_service_requests
  where id = p_request_id
  for update;

  if not found then
    raise exception 'REQUEST_NOT_FOUND';
  end if;

  if v_request.status in ('completed', 'cancelled', 'closed_inactive', 'disputed') then
    return;
  end if;

  if exists (
    select 1 from public.jacc_request_assignments
    where request_id = p_request_id and status = 'active'
  ) then
    return;
  end if;

  if exists (
    select 1 from public.jacc_request_offers
    where request_id = p_request_id
      and status = 'pending'
      and expires_at > now()
  ) then
    return;
  end if;

  update public.jacc_request_offers
  set status = 'expired', responded_at = now()
  where request_id = p_request_id
    and status = 'pending'
    and expires_at <= now();

  select bp.* into v_broker
  from public.jacc_broker_profiles bp
  join public.jacc_profiles p on p.id = bp.user_id
  where p.account_active = true
    and bp.account_status in ('probation', 'active')
    and bp.accepting_requests = true
    and (
      (v_request.service_type = 'auction' and bp.can_auction = true) or
      (v_request.service_type = 'outside_car' and bp.can_outside_car = true)
    )
    and not exists (
      select 1
      from public.jacc_request_assignments a
      where a.broker_id = bp.user_id
        and a.service_type = v_request.service_type
        and a.status = 'active'
    )
    and not exists (
      select 1
      from public.jacc_request_offers o
      where o.request_id = p_request_id
        and o.broker_id = bp.user_id
    )
  order by
    bp.last_assigned_at nulls first,
    bp.total_assigned_count asc,
    bp.last_offer_at nulls first,
    bp.user_id
  for update of bp skip locked
  limit 1;

  if not found then
    update public.jacc_service_requests
    set status = 'waiting_broker'
    where id = p_request_id;
    return;
  end if;

  select coalesce(max(sequence_no), 0) + 1
  into v_sequence
  from public.jacc_request_offers
  where request_id = p_request_id;

  insert into public.jacc_request_offers(
    request_id, broker_id, sequence_no, status, offered_at, expires_at
  ) values (
    p_request_id, v_broker.user_id, v_sequence, 'pending', now(), now() + interval '10 minutes'
  ) returning * into v_offer;

  update public.jacc_broker_profiles
  set last_offer_at = now()
  where user_id = v_broker.user_id;

  update public.jacc_service_requests
  set status = 'offered'
  where id = p_request_id;

  insert into public.jacc_request_status_history(
    request_id, old_status, new_status, reason
  ) values (
    p_request_id, v_request.status, 'offered',
    'Sequential offer #' || v_sequence || ' sent to ' || v_broker.broker_code
  );

  return query
  select
    v_offer.id,
    v_request.id,
    v_request.request_code,
    v_broker.user_id,
    v_broker.broker_code,
    p.telegram_user_id,
    v_request.service_type,
    v_request.service_channel,
    v_offer.expires_at
  from public.jacc_profiles p
  where p.id = v_broker.user_id;
end;
$$;

create or replace function public.jacc_accept_offer(
  p_offer_id uuid,
  p_broker_id uuid
)
returns public.jacc_request_assignments
language plpgsql
security definer
set search_path = public
as $$
declare
  v_offer public.jacc_request_offers%rowtype;
  v_request public.jacc_service_requests%rowtype;
  v_assignment public.jacc_request_assignments%rowtype;
begin
  select * into v_offer
  from public.jacc_request_offers
  where id = p_offer_id
  for update;

  if not found then
    raise exception 'OFFER_NOT_FOUND';
  end if;

  if v_offer.broker_id <> p_broker_id then
    raise exception 'OFFER_NOT_OWNED_BY_BROKER';
  end if;

  if v_offer.status <> 'pending' then
    raise exception 'OFFER_NOT_PENDING';
  end if;

  if v_offer.expires_at <= now() then
    update public.jacc_request_offers
    set status = 'expired', responded_at = now()
    where id = p_offer_id;
    raise exception 'OFFER_EXPIRED';
  end if;

  select * into v_request
  from public.jacc_service_requests
  where id = v_offer.request_id
  for update;

  if exists (
    select 1 from public.jacc_request_assignments
    where request_id = v_request.id and status = 'active'
  ) then
    raise exception 'REQUEST_ALREADY_ASSIGNED';
  end if;

  if exists (
    select 1 from public.jacc_request_assignments
    where broker_id = p_broker_id
      and service_type = v_request.service_type
      and status = 'active'
  ) then
    raise exception 'BROKER_SERVICE_CAPACITY_FULL';
  end if;

  update public.jacc_request_offers
  set status = 'accepted', responded_at = now()
  where id = p_offer_id;

  update public.jacc_request_offers
  set status = 'cancelled', responded_at = now()
  where request_id = v_request.id
    and id <> p_offer_id
    and status = 'pending';

  insert into public.jacc_request_assignments(
    request_id, broker_id, service_type, status
  ) values (
    v_request.id, p_broker_id, v_request.service_type, 'active'
  ) returning * into v_assignment;

  update public.jacc_service_requests
  set
    assigned_broker_id = p_broker_id,
    status = 'assigned',
    last_meaningful_update_at = now(),
    broker_last_reply_at = now()
  where id = v_request.id;

  update public.jacc_broker_profiles
  set
    total_assigned_count = total_assigned_count + 1,
    last_assigned_at = now()
  where user_id = p_broker_id;

  insert into public.jacc_request_status_history(
    request_id, old_status, new_status, changed_by, reason
  ) values (
    v_request.id, v_request.status, 'assigned', p_broker_id, 'Broker accepted offer'
  );

  return v_assignment;
end;
$$;

create or replace function public.jacc_decline_offer(
  p_offer_id uuid,
  p_broker_id uuid,
  p_reason text default null
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request_id uuid;
begin
  update public.jacc_request_offers
  set
    status = 'declined',
    responded_at = now(),
    decline_reason = nullif(trim(p_reason), '')
  where id = p_offer_id
    and broker_id = p_broker_id
    and status = 'pending'
    and expires_at > now()
  returning request_id into v_request_id;

  if v_request_id is null then
    raise exception 'VALID_PENDING_OFFER_NOT_FOUND';
  end if;

  update public.jacc_broker_profiles
  set decline_count = decline_count + 1
  where user_id = p_broker_id;

  update public.jacc_service_requests
  set status = 'waiting_broker'
  where id = v_request_id;

  return v_request_id;
end;
$$;

-- Worker calls this every 30-60 seconds, then dispatches each returned request.
create or replace function public.jacc_expire_pending_offers()
returns table (request_id uuid)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with expired as (
    update public.jacc_request_offers
    set status = 'expired', responded_at = now()
    where status = 'pending'
      and expires_at <= now()
    returning jacc_request_offers.request_id
  ), changed as (
    update public.jacc_service_requests r
    set status = 'waiting_broker'
    where r.id in (select distinct e.request_id from expired e)
      and not exists (
        select 1 from public.jacc_request_assignments a
        where a.request_id = r.id and a.status = 'active'
      )
    returning r.id
  )
  select changed.id from changed;
end;
$$;

commit;
