-- JACC Phase 1 hotfix: allow bounded retries after broker offers expire.
-- Applied to production on 2026-08-02 after a live end-to-end verification.
-- Run after 008_fix_dispatch_offer_ambiguity.sql.

begin;

-- The old unique constraint allowed only one offer per request/broker pair,
-- which permanently blocked retrying the same broker after an expired offer.
alter table public.jacc_request_offers
  drop constraint if exists jacc_request_offers_request_id_broker_id_key;

create index if not exists idx_jacc_offers_request_broker_time
  on public.jacc_request_offers (
    request_id,
    broker_id,
    offered_at desc
  );

create or replace function public.jacc_dispatch_next_offer(
  p_request_id uuid
)
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
  select r.*
  into v_request
  from public.jacc_service_requests r
  where r.id = p_request_id
  for update;

  if not found then
    raise exception 'REQUEST_NOT_FOUND';
  end if;

  if v_request.status in (
    'completed',
    'cancelled',
    'closed_inactive',
    'disputed'
  ) then
    return;
  end if;

  if exists (
    select 1
    from public.jacc_request_assignments a
    where a.request_id = p_request_id
      and a.status = 'active'
  ) then
    return;
  end if;

  if exists (
    select 1
    from public.jacc_request_offers o
    where o.request_id = p_request_id
      and o.status = 'pending'
      and o.expires_at > now()
  ) then
    return;
  end if;

  update public.jacc_request_offers o
  set
    status = 'expired',
    responded_at = coalesce(o.responded_at, now())
  where o.request_id = p_request_id
    and o.status = 'pending'
    and o.expires_at <= now();

  select bp.*
  into v_broker
  from public.jacc_broker_profiles bp
  join public.jacc_profiles p
    on p.id = bp.user_id
  where p.account_active = true
    and bp.account_status in ('probation', 'active')
    and bp.accepting_requests = true
    and (
      (
        v_request.service_type = 'auction'
        and bp.can_auction = true
      )
      or
      (
        v_request.service_type = 'outside_car'
        and bp.can_outside_car = true
      )
    )
    and not exists (
      select 1
      from public.jacc_request_assignments a
      where a.broker_id = bp.user_id
        and a.service_type = v_request.service_type
        and a.status = 'active'
    )
    and (
      select count(*)
      from public.jacc_request_offers oc
      where oc.request_id = p_request_id
        and oc.broker_id = bp.user_id
    ) < 3
    and not exists (
      select 1
      from public.jacc_request_offers recent
      where recent.request_id = p_request_id
        and recent.broker_id = bp.user_id
        and recent.offered_at > now() - interval '30 minutes'
    )
  order by
    (
      select count(*)
      from public.jacc_request_offers oc
      where oc.request_id = p_request_id
        and oc.broker_id = bp.user_id
    ) asc,
    (
      select max(om.offered_at)
      from public.jacc_request_offers om
      where om.request_id = p_request_id
        and om.broker_id = bp.user_id
    ) nulls first,
    bp.last_assigned_at nulls first,
    bp.total_assigned_count asc,
    bp.last_offer_at nulls first,
    bp.user_id
  for update of bp skip locked
  limit 1;

  if not found then
    update public.jacc_service_requests r
    set status = 'waiting_broker'
    where r.id = p_request_id;

    return;
  end if;

  select coalesce(max(o.sequence_no), 0) + 1
  into v_sequence
  from public.jacc_request_offers o
  where o.request_id = p_request_id;

  insert into public.jacc_request_offers (
    request_id,
    broker_id,
    sequence_no,
    status,
    offered_at,
    expires_at
  )
  values (
    p_request_id,
    v_broker.user_id,
    v_sequence,
    'pending',
    now(),
    now() + interval '10 minutes'
  )
  returning *
  into v_offer;

  update public.jacc_broker_profiles bp
  set last_offer_at = now()
  where bp.user_id = v_broker.user_id;

  update public.jacc_service_requests r
  set status = 'offered'
  where r.id = p_request_id;

  insert into public.jacc_request_status_history (
    request_id,
    old_status,
    new_status,
    reason
  )
  values (
    p_request_id,
    v_request.status,
    'offered',
    'Sequential retry offer #' ||
    v_sequence ||
    ' sent to ' ||
    v_broker.broker_code
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

comment on function public.jacc_dispatch_next_offer(uuid) is
  'Sequential broker dispatch with 30-minute retry cooldown and maximum 3 offers per broker per request.';

commit;
