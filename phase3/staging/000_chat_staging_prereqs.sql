-- Ephemeral staging prerequisites for validating Phase 3 chat migrations.
-- REVIEW/STAGING ONLY. This file must never be run against production.

create extension if not exists pgcrypto;

do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
do $$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_app_role as enum ('customer','broker','lead_broker','admin');
exception when duplicate_object then null; end $$;

create table if not exists public.jacc_profiles (
  id uuid primary key,
  role public.jacc_app_role not null,
  account_active boolean not null default true
);

create table if not exists public.jacc_memberships (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.jacc_profiles(id) on delete cascade,
  plan text not null,
  service_channel text not null,
  status text not null,
  starts_at timestamptz not null,
  expires_at timestamptz
);

create table if not exists public.jacc_broker_profiles (
  user_id uuid primary key references public.jacc_profiles(id) on delete cascade,
  account_status text not null
);

create table if not exists public.jacc_service_requests (
  id uuid primary key,
  customer_id uuid not null references public.jacc_profiles(id) on delete restrict,
  assigned_broker_id uuid references public.jacc_broker_profiles(user_id) on delete restrict
);

create or replace function public.jacc_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.jacc_current_profile_id()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

create or replace function public.jacc_is_admin()
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
      and p.role in ('admin','lead_broker')
  );
$$;

grant usage on schema public to anon, authenticated, service_role;
grant execute on function public.jacc_current_profile_id() to authenticated, service_role;
grant execute on function public.jacc_is_admin() to authenticated, service_role;
