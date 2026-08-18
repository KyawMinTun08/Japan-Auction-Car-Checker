begin;

-- JACC text-AI quota. This is additive and does not change Members A-I.
create table if not exists public.jacc_ai_usage_daily (
  user_id text not null,
  usage_date date not null,
  feature text not null default 'car_text',
  ask_count integer not null default 0 check (ask_count >= 0),
  last_request_at timestamptz,
  last_request_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, usage_date, feature)
);

create index if not exists idx_jacc_ai_usage_daily_date
  on public.jacc_ai_usage_daily(usage_date, feature);

-- Backend-only atomic quota consumption. The application passes Asia/Yangon's
-- current date; the function does not trust client-side counters.
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
  on conflict (user_id, usage_date, feature) do nothing;

  if found then
    return query select true, 1, clean_limit - 1, p_usage_date, trim(p_feature);
    return;
  end if;

  update public.jacc_ai_usage_daily as usage
     set ask_count = usage.ask_count + 1,
         last_request_at = now(),
         last_request_hash = left(p_request_hash, 128),
         updated_at = now()
   where usage.user_id = trim(p_user_id)
     and usage.usage_date = p_usage_date
     and usage.feature = trim(p_feature)
     and usage.ask_count < clean_limit
  returning usage.ask_count into current_count;

  if current_count is null then
    select usage.ask_count
      into current_count
      from public.jacc_ai_usage_daily as usage
     where usage.user_id = trim(p_user_id)
       and usage.usage_date = p_usage_date
       and usage.feature = trim(p_feature);
    return query select false, coalesce(current_count, clean_limit), 0, p_usage_date, trim(p_feature);
    return;
  end if;

  return query select true, current_count, clean_limit - current_count, p_usage_date, trim(p_feature);
end;
$$;

alter table public.jacc_ai_usage_daily enable row level security;
revoke all on table public.jacc_ai_usage_daily from anon, authenticated;
revoke all on function public.jacc_consume_ai_quota(text, date, text, integer, text) from public, anon, authenticated;
grant execute on function public.jacc_consume_ai_quota(text, date, text, integer, text) to service_role;

commit;
