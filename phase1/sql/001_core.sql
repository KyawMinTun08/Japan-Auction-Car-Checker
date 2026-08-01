-- JACC Phase 1 migration part: 001_core.sql
-- Run migrations in filename order.

begin;

-- JACC Phase 1: central request + sequential broker assignment
-- Target: Supabase PostgreSQL
-- Run in a fresh Supabase SQL editor.


create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- ENUMS
-- ---------------------------------------------------------------------------

do $$ begin
  create type public.jacc_app_role as enum ('customer', 'broker', 'lead_broker', 'admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_membership_plan as enum ('standard', 'premium');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_service_channel as enum ('telegram', 'app');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_service_type as enum ('auction', 'outside_car');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_broker_status as enum (
    'pending_review', 'probation', 'active', 'offline',
    'temporarily_suspended', 'banned', 'resigned'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_request_status as enum (
    'submitted', 'waiting_broker', 'offered', 'assigned', 'consulting',
    'searching', 'car_found', 'waiting_customer', 'waiting_payment',
    'payment_verifying', 'payment_confirmed', 'price_approval',
    'auction_pending', 'won', 'lost', 'negotiating',
    'inspection_pending', 'reserved', 'purchased', 'paused',
    'completed', 'cancelled', 'closed_inactive', 'disputed', 'reassigned'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_offer_status as enum ('pending', 'accepted', 'declined', 'expired', 'cancelled');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.jacc_assignment_status as enum ('active', 'completed', 'reassigned', 'cancelled');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- CORE TABLES
-- ---------------------------------------------------------------------------

create table if not exists public.jacc_profiles (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique references auth.users(id) on delete set null,
  role public.jacc_app_role not null default 'customer',
  display_name text not null,
  customer_code text unique,
  telegram_user_id bigint unique,
  account_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.jacc_memberships (
  user_id uuid primary key references public.jacc_profiles(id) on delete cascade,
  plan public.jacc_membership_plan not null,
  service_channel public.jacc_service_channel not null,
  package_raw text,
  status text not null default 'ACTIVE',
  starts_at timestamptz not null default now(),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_membership_channel_check check (
    (plan = 'premium' and service_channel = 'app') or
    (plan = 'standard' and service_channel = 'telegram')
  )
);

create table if not exists public.jacc_broker_profiles (
  user_id uuid primary key references public.jacc_profiles(id) on delete cascade,
  broker_code text not null unique,
  account_status public.jacc_broker_status not null default 'pending_review',
  accepting_requests boolean not null default false,
  can_auction boolean not null default false,
  can_outside_car boolean not null default false,
  probation_deals_required integer not null default 3 check (probation_deals_required >= 0),
  probation_deals_completed integer not null default 0 check (probation_deals_completed >= 0),
  rating numeric(3,2) not null default 0 check (rating >= 0 and rating <= 5),
  rating_count integer not null default 0 check (rating_count >= 0),
  deals_count integer not null default 0 check (deals_count >= 0),
  decline_count integer not null default 0 check (decline_count >= 0),
  complaint_count integer not null default 0 check (complaint_count >= 0),
  total_assigned_count integer not null default 0 check (total_assigned_count >= 0),
  last_assigned_at timestamptz,
  last_offer_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_broker_has_skill check (can_auction or can_outside_car)
);

create sequence if not exists public.jacc_request_code_seq;

create table if not exists public.jacc_service_requests (
  id uuid primary key default gen_random_uuid(),
  request_code text not null unique,
  customer_id uuid not null references public.jacc_profiles(id),
  service_type public.jacc_service_type not null,
  service_channel public.jacc_service_channel not null,
  status public.jacc_request_status not null default 'submitted',
  form_data jsonb not null default '{}'::jsonb,
  priority integer not null default 0,
  assigned_broker_id uuid references public.jacc_broker_profiles(user_id),
  last_meaningful_update_at timestamptz,
  broker_last_reply_at timestamptz,
  customer_last_reply_at timestamptz,
  auction_deadline_at timestamptz,
  paused_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jacc_request_priority_range check (priority between 0 and 1000)
);

create table if not exists public.jacc_request_offers (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.jacc_service_requests(id) on delete cascade,
  broker_id uuid not null references public.jacc_broker_profiles(user_id),
  sequence_no integer not null check (sequence_no > 0),
  status public.jacc_offer_status not null default 'pending',
  offered_at timestamptz not null default now(),
  expires_at timestamptz not null,
  responded_at timestamptz,
  decline_reason text,
  created_at timestamptz not null default now(),
  unique (request_id, broker_id),
  unique (request_id, sequence_no)
);

create table if not exists public.jacc_request_assignments (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.jacc_service_requests(id) on delete cascade,
  broker_id uuid not null references public.jacc_broker_profiles(user_id),
  service_type public.jacc_service_type not null,
  status public.jacc_assignment_status not null default 'active',
  assigned_at timestamptz not null default now(),
  ended_at timestamptz,
  ended_reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.jacc_request_updates (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.jacc_service_requests(id) on delete cascade,
  actor_id uuid not null references public.jacc_profiles(id),
  update_type text not null,
  content jsonb not null default '{}'::jsonb,
  meaningful boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.jacc_request_status_history (
  id bigint generated always as identity primary key,
  request_id uuid not null references public.jacc_service_requests(id) on delete cascade,
  old_status public.jacc_request_status,
  new_status public.jacc_request_status not null,
  changed_by uuid references public.jacc_profiles(id),
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.jacc_audit_logs (
  id bigint generated always as identity primary key,
  actor_id uuid references public.jacc_profiles(id),
  action text not null,
  entity_type text not null,
  entity_id text not null,
  old_data jsonb,
  new_data jsonb,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- INDEXES AND HARD BUSINESS CONSTRAINTS
-- ---------------------------------------------------------------------------

create index if not exists idx_jacc_requests_customer_created
  on public.jacc_service_requests(customer_id, created_at desc);

create index if not exists idx_jacc_requests_status_priority
  on public.jacc_service_requests(status, priority desc, created_at);

create index if not exists idx_jacc_offers_broker_status_expiry
  on public.jacc_request_offers(broker_id, status, expires_at);

create index if not exists idx_jacc_assignments_broker_status
  on public.jacc_request_assignments(broker_id, status, service_type);

create index if not exists idx_jacc_updates_request_created
  on public.jacc_request_updates(request_id, created_at desc);

-- Member တစ်ယောက် Active Request တစ်ခုသာထားနိုင်မည်။
create unique index if not exists uq_jacc_one_open_request_per_customer
  on public.jacc_service_requests(customer_id)
  where status not in ('completed', 'cancelled', 'closed_inactive');

-- Request တစ်ခုတွင် Pending Offer တစ်ခုသာရှိနိုင်မည်။
create unique index if not exists uq_jacc_one_pending_offer_per_request
  on public.jacc_request_offers(request_id)
  where status = 'pending';

-- Request တစ်ခုတွင် Active Assignment တစ်ခုသာရှိနိုင်မည်။
create unique index if not exists uq_jacc_one_active_assignment_per_request
  on public.jacc_request_assignments(request_id)
  where status = 'active';

-- Broker တစ်ယောက် Auction ၁ ခု + Outside ၁ ခုသာ Active ဖြစ်နိုင်မည်။
create unique index if not exists uq_jacc_one_active_service_per_broker
  on public.jacc_request_assignments(broker_id, service_type)
  where status = 'active';

-- ---------------------------------------------------------------------------
-- HELPERS
-- ---------------------------------------------------------------------------

create or replace function public.jacc_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_jacc_profiles_updated_at on public.jacc_profiles;
create trigger trg_jacc_profiles_updated_at
before update on public.jacc_profiles
for each row execute function public.jacc_touch_updated_at();

drop trigger if exists trg_jacc_memberships_updated_at on public.jacc_memberships;
create trigger trg_jacc_memberships_updated_at
before update on public.jacc_memberships
for each row execute function public.jacc_touch_updated_at();

drop trigger if exists trg_jacc_brokers_updated_at on public.jacc_broker_profiles;
create trigger trg_jacc_brokers_updated_at
before update on public.jacc_broker_profiles
for each row execute function public.jacc_touch_updated_at();

drop trigger if exists trg_jacc_requests_updated_at on public.jacc_service_requests;
create trigger trg_jacc_requests_updated_at
before update on public.jacc_service_requests
for each row execute function public.jacc_touch_updated_at();

create or replace function public.jacc_make_request_code(p_type public.jacc_service_type)
returns text
language sql
volatile
as $$
  select
    case when p_type = 'auction' then 'A' else 'R' end ||
    to_char(current_date, 'YYMMDD') || '-' ||
    lpad(nextval('public.jacc_request_code_seq')::text, 6, '0');
$$;

create or replace function public.jacc_current_profile_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select p.id
  from public.jacc_profiles p
  where p.auth_user_id = auth.uid()
  limit 1;
$$;

create or replace function public.jacc_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.jacc_profiles p
    where p.id = public.jacc_current_profile_id()
      and p.role in ('admin', 'lead_broker')
  );
$$;

commit;
