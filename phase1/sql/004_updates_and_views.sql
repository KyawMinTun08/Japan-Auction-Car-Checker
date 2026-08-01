-- JACC Phase 1 migration part: 004_updates_and_views.sql
-- Run migrations in filename order.

begin;

-- ---------------------------------------------------------------------------
-- MEANINGFUL UPDATE + 48 HOUR REASSIGNMENT
-- ---------------------------------------------------------------------------

create or replace function public.jacc_record_meaningful_update(
  p_request_id uuid,
  p_actor_id uuid,
  p_update_type text,
  p_content jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.jacc_request_updates(
    request_id, actor_id, update_type, content, meaningful
  ) values (
    p_request_id, p_actor_id, p_update_type, coalesce(p_content, '{}'::jsonb), true
  );

  update public.jacc_service_requests
  set
    last_meaningful_update_at = now(),
    broker_last_reply_at = case
      when assigned_broker_id = p_actor_id then now()
      else broker_last_reply_at
    end,
    customer_last_reply_at = case
      when customer_id = p_actor_id then now()
      else customer_last_reply_at
    end
  where id = p_request_id;
end;
$$;

-- Ends stale broker assignments after 48 hours without meaningful update.
-- Auction requests with a future deadline inside the next 48h are returned as urgent,
-- but still reassigned by this function so the customer is not left unattended.
create or replace function public.jacc_reassign_stale_requests()
returns table (
  request_id uuid,
  request_code text,
  old_broker_id uuid,
  urgent_auction boolean
)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with stale as (
    select
      r.id,
      r.request_code,
      a.id as assignment_id,
      a.broker_id,
      (
        r.service_type = 'auction'
        and r.auction_deadline_at is not null
        and r.auction_deadline_at <= now() + interval '48 hours'
      ) as urgent_auction
    from public.jacc_service_requests r
    join public.jacc_request_assignments a
      on a.request_id = r.id and a.status = 'active'
    where r.status not in (
      'waiting_customer', 'paused', 'completed', 'cancelled',
      'closed_inactive', 'disputed'
    )
      and coalesce(r.last_meaningful_update_at, a.assigned_at)
          <= now() - interval '48 hours'
    for update of r, a skip locked
  ), ended as (
    update public.jacc_request_assignments a
    set status = 'reassigned', ended_at = now(), ended_reason = '48_HOUR_NO_MEANINGFUL_UPDATE'
    where a.id in (select s.assignment_id from stale s)
    returning a.request_id, a.broker_id
  ), reset_requests as (
    update public.jacc_service_requests r
    set
      assigned_broker_id = null,
      status = 'reassigned',
      last_meaningful_update_at = null
    where r.id in (select e.request_id from ended e)
    returning r.id, r.request_code
  )
  select s.id, s.request_code, s.broker_id, s.urgent_auction
  from stale s;
end;
$$;

-- ---------------------------------------------------------------------------
-- VIEWS
-- ---------------------------------------------------------------------------

create or replace view public.jacc_broker_capacity as
select
  bp.user_id as broker_id,
  bp.broker_code,
  count(*) filter (where a.status = 'active' and a.service_type = 'auction') as active_auction,
  count(*) filter (where a.status = 'active' and a.service_type = 'outside_car') as active_outside_car,
  case when count(*) filter (where a.status = 'active' and a.service_type = 'auction') = 0
       then true else false end as auction_slot_available,
  case when count(*) filter (where a.status = 'active' and a.service_type = 'outside_car') = 0
       then true else false end as outside_car_slot_available
from public.jacc_broker_profiles bp
left join public.jacc_request_assignments a on a.broker_id = bp.user_id
 group by bp.user_id, bp.broker_code;

commit;
