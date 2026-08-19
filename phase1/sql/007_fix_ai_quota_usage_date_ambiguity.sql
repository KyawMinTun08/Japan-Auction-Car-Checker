-- Fix: RETURNS TABLE exposes usage_date as an output variable, so the
-- column-list conflict target is ambiguous in PostgreSQL. Use the PK name.
create or replace function public.jacc_consume_ai_quota(
  p_user_id text,
  p_usage_date date,
  p_feature text,
  p_daily_limit integer,
  p_request_hash text
)
returns table (
  accepted boolean,
  ask_count integer,
  remaining integer,
  usage_date date,
  feature text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_count integer;
  clean_limit integer := greatest(1, least(coalesce(p_daily_limit, 10), 100));
begin
  if nullif(trim(coalesce(p_user_id, '')), '') is null
     or p_usage_date is null
     or nullif(trim(coalesce(p_feature, '')), '') is null then
    raise exception 'AI quota identity is required';
  end if;

  insert into public.jacc_ai_usage_daily (
    user_id, usage_date, feature, ask_count, last_request_at, last_request_hash
  )
  values (
    trim(p_user_id), p_usage_date, trim(p_feature), 1, now(), left(p_request_hash, 128)
  )
  on conflict on constraint jacc_ai_usage_daily_pkey do nothing;

  if found then
    return query select true, 1, clean_limit - 1, p_usage_date, trim(p_feature);
    return;
  end if;

  update public.jacc_ai_usage_daily as u
     set ask_count = u.ask_count + 1,
         last_request_at = now(),
         last_request_hash = left(p_request_hash, 128),
         updated_at = now()
   where u.user_id = trim(p_user_id)
     and u.usage_date = p_usage_date
     and u.feature = trim(p_feature)
     and u.ask_count < clean_limit
  returning u.ask_count into current_count;

  if current_count is null then
    select u.ask_count into current_count
      from public.jacc_ai_usage_daily as u
     where u.user_id = trim(p_user_id)
       and u.usage_date = p_usage_date
       and u.feature = trim(p_feature);
    return query select false, coalesce(current_count, clean_limit), 0, p_usage_date, trim(p_feature);
    return;
  end if;

  return query select true, current_count, clean_limit - current_count, p_usage_date, trim(p_feature);
end;
$$;

revoke all on function public.jacc_consume_ai_quota(text, date, text, integer, text) from public, anon, authenticated;
grant execute on function public.jacc_consume_ai_quota(text, date, text, integer, text) to service_role;
