-- JACC Phase 1 migration part: 002_create_request.sql
-- Run migrations in filename order.

begin;

-- ---------------------------------------------------------------------------
-- CREATE REQUEST
-- ---------------------------------------------------------------------------

create or replace function public.jacc_create_my_request(
  p_service_type public.jacc_service_type,
  p_form_data jsonb
)
returns public.jacc_service_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  v_uid uuid := public.jacc_current_profile_id();
  v_membership public.jacc_memberships%rowtype;
  v_request public.jacc_service_requests%rowtype;
  v_priority integer;
begin
  if auth.uid() is null or v_uid is null then
    raise exception 'AUTH_PROFILE_REQUIRED';
  end if;

  select * into v_membership
  from public.jacc_memberships
  where user_id = v_uid
    and status = 'ACTIVE'
    and (expires_at is null or expires_at >= now());

  if not found then
    raise exception 'ACTIVE_MEMBERSHIP_REQUIRED';
  end if;

  if exists (
    select 1 from public.jacc_service_requests
    where customer_id = v_uid
      and status not in ('completed', 'cancelled', 'closed_inactive')
  ) then
    raise exception 'ACTIVE_REQUEST_ALREADY_EXISTS';
  end if;

  v_priority := case when v_membership.plan = 'premium' then 10 else 0 end;

  insert into public.jacc_service_requests (
    request_code, customer_id, service_type, service_channel,
    status, form_data, priority
  ) values (
    public.jacc_make_request_code(p_service_type),
    v_uid,
    p_service_type,
    v_membership.service_channel,
    'waiting_broker',
    coalesce(p_form_data, '{}'::jsonb),
    v_priority
  ) returning * into v_request;

  insert into public.jacc_request_status_history(
    request_id, old_status, new_status, changed_by, reason
  ) values (
    v_request.id, null, 'waiting_broker', v_uid, 'Customer submitted request'
  );

  return v_request;
end;
$$;

-- Telegram bridge/server version. The backend supplies the central profile id.
create or replace function public.jacc_create_request_for_customer(
  p_customer_id uuid,
  p_service_type public.jacc_service_type,
  p_form_data jsonb
)
returns public.jacc_service_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  v_membership public.jacc_memberships%rowtype;
  v_request public.jacc_service_requests%rowtype;
  v_priority integer;
begin
  select * into v_membership
  from public.jacc_memberships
  where user_id = p_customer_id
    and status = 'ACTIVE'
    and (expires_at is null or expires_at >= now());

  if not found then
    raise exception 'ACTIVE_MEMBERSHIP_REQUIRED';
  end if;

  if exists (
    select 1 from public.jacc_service_requests
    where customer_id = p_customer_id
      and status not in ('completed', 'cancelled', 'closed_inactive')
  ) then
    raise exception 'ACTIVE_REQUEST_ALREADY_EXISTS';
  end if;

  v_priority := case when v_membership.plan = 'premium' then 10 else 0 end;

  insert into public.jacc_service_requests (
    request_code, customer_id, service_type, service_channel,
    status, form_data, priority
  ) values (
    public.jacc_make_request_code(p_service_type),
    p_customer_id,
    p_service_type,
    v_membership.service_channel,
    'waiting_broker',
    coalesce(p_form_data, '{}'::jsonb),
    v_priority
  ) returning * into v_request;

  insert into public.jacc_request_status_history(
    request_id, old_status, new_status, changed_by, reason
  ) values (
    v_request.id, null, 'waiting_broker', p_customer_id,
    'Request submitted by Telegram/server bridge'
  );

  return v_request;
end;
$$;

commit;
