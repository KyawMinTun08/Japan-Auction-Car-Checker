-- JACC JDM vehicle data foundation
-- Scope: factory model/grade and future auction-history/provider cache data.
-- Existing membership, request, and Google Sheets flows are intentionally untouched.

create table if not exists public.jacc_data_sources (
  id uuid primary key default gen_random_uuid(),
  source_key text not null unique,
  display_name text not null,
  source_type text not null check (source_type in ('open_dataset', 'manual', 'provider_api', 'official_catalog')),
  source_url text,
  license_name text,
  commercial_use_allowed boolean not null default false,
  automation_allowed boolean not null default false,
  attribution_required boolean not null default false,
  status text not null default 'active' check (status in ('active', 'paused', 'retired')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.jacc_vehicle_makes (
  id uuid primary key default gen_random_uuid(),
  make_key text not null unique,
  display_name text not null,
  country_code text default 'JP',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.jacc_vehicle_models (
  id uuid primary key default gen_random_uuid(),
  make_id uuid not null references public.jacc_vehicle_makes(id),
  canonical_name text not null,
  aliases text[] not null default '{}',
  body_type text,
  vehicle_category text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (make_id, canonical_name)
);

create table if not exists public.jacc_chassis_codes (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.jacc_vehicle_models(id),
  chassis_prefix text not null,
  chassis_prefix_normalized text not null,
  engine_code text,
  transmission text,
  body_type text,
  production_from_year smallint,
  production_to_year smallint,
  production_from_month smallint check (production_from_month between 1 and 12),
  production_to_month smallint check (production_to_month between 1 and 12),
  source_id uuid references public.jacc_data_sources(id),
  source_record_key text,
  confidence text not null default 'manual' check (confidence in ('official', 'verified', 'manual', 'inferred')),
  verified boolean not null default false,
  notes text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (chassis_prefix_normalized, model_id)
);

create table if not exists public.jacc_factory_grades (
  id uuid primary key default gen_random_uuid(),
  chassis_code_id uuid references public.jacc_chassis_codes(id) on delete set null,
  model_id uuid not null references public.jacc_vehicle_models(id),
  grade_code text not null,
  grade_name text,
  trim_level text,
  equipment jsonb not null default '{}'::jsonb,
  production_from_year smallint,
  production_to_year smallint,
  source_id uuid references public.jacc_data_sources(id),
  source_record_key text,
  confidence text not null default 'manual' check (confidence in ('official', 'verified', 'manual', 'inferred')),
  verified boolean not null default false,
  notes text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (model_id, chassis_code_id, grade_code, source_id)
);

create table if not exists public.jacc_auction_history (
  id uuid primary key default gen_random_uuid(),
  chassis_number_hash text not null,
  chassis_prefix text,
  model_id uuid references public.jacc_vehicle_models(id) on delete set null,
  auction_condition_grade text,
  auction_date date,
  auction_house text,
  lot_number text,
  mileage_km integer check (mileage_km is null or mileage_km >= 0),
  final_price numeric(14,2),
  currency_code text,
  accident_repair_status text,
  auction_sheet_url text,
  photo_urls jsonb not null default '[]'::jsonb,
  raw_payload jsonb not null default '{}'::jsonb,
  source_id uuid references public.jacc_data_sources(id),
  source_record_key text,
  verified boolean not null default false,
  checked_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (chassis_number_hash, source_id, auction_date, lot_number)
);

create table if not exists public.jacc_lookup_cache (
  id uuid primary key default gen_random_uuid(),
  chassis_number_hash text not null,
  normalized_chassis text,
  lookup_kind text not null check (lookup_kind in ('factory_grade', 'model_info', 'auction_history')),
  provider_key text not null,
  status text not null check (status in ('hit', 'not_found', 'error')),
  response_payload jsonb not null default '{}'::jsonb,
  error_code text,
  checked_at timestamptz not null default now(),
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (chassis_number_hash, lookup_kind, provider_key)
);

create table if not exists public.jacc_data_import_batches (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references public.jacc_data_sources(id),
  dataset_name text not null,
  dataset_version text,
  source_checksum text,
  source_license text,
  imported_row_count integer not null default 0,
  rejected_row_count integer not null default 0,
  status text not null default 'staged' check (status in ('staged', 'imported', 'failed', 'rolled_back')),
  imported_at timestamptz,
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists idx_jacc_chassis_prefix on public.jacc_chassis_codes (chassis_prefix_normalized);
create index if not exists idx_jacc_chassis_model on public.jacc_chassis_codes (model_id);
create index if not exists idx_jacc_factory_grade_model on public.jacc_factory_grades (model_id);
create index if not exists idx_jacc_auction_chassis_hash on public.jacc_auction_history (chassis_number_hash);
create index if not exists idx_jacc_lookup_cache_expiry on public.jacc_lookup_cache (expires_at);

-- These tables are queried only by the Railway server-side backend for now.
-- No browser/anon policies are created in this foundation migration.
alter table public.jacc_data_sources enable row level security;
alter table public.jacc_vehicle_makes enable row level security;
alter table public.jacc_vehicle_models enable row level security;
alter table public.jacc_chassis_codes enable row level security;
alter table public.jacc_factory_grades enable row level security;
alter table public.jacc_auction_history enable row level security;
alter table public.jacc_lookup_cache enable row level security;
alter table public.jacc_data_import_batches enable row level security;

insert into public.jacc_data_sources
  (source_key, display_name, source_type, source_url, license_name, commercial_use_allowed, automation_allowed, attribution_required, notes)
values
  ('world_motor_vehicle_list', 'World Motor Vehicle List', 'open_dataset', 'https://github.com/masiton/world-motor-vehicle-list', 'Unlicense', true, true, false, 'Static model/year/edition dictionary; no chassis field. Verify upstream provenance before production use.'),
  ('jacc_manual_verified', 'JACC manually verified mapping', 'manual', null, null, true, true, false, 'Internal JACC mappings based on reviewed chassis/model references.'),
  ('jdmvin_pending_permission', 'JDMVIN', 'provider_api', 'https://jdmvin.com/', null, false, false, true, 'Do not automate until written permission or official API access is obtained.')
on conflict (source_key) do update set
  display_name = excluded.display_name,
  source_type = excluded.source_type,
  source_url = excluded.source_url,
  license_name = excluded.license_name,
  commercial_use_allowed = excluded.commercial_use_allowed,
  automation_allowed = excluded.automation_allowed,
  attribution_required = excluded.attribution_required,
  notes = excluded.notes,
  updated_at = now();

insert into public.jacc_vehicle_makes (make_key, display_name, country_code)
values
  ('toyota', 'Toyota', 'JP'),
  ('lexus', 'Lexus', 'JP'),
  ('nissan', 'Nissan', 'JP'),
  ('honda', 'Honda', 'JP'),
  ('daihatsu', 'Daihatsu', 'JP'),
  ('mitsubishi', 'Mitsubishi', 'JP'),
  ('subaru', 'Subaru', 'JP'),
  ('mazda', 'Mazda', 'JP'),
  ('suzuki', 'Suzuki', 'JP'),
  ('hino', 'Hino', 'JP'),
  ('mitsubishi_fuso', 'Mitsubishi Fuso', 'JP'),
  ('ud_nissan_truck', 'UD/Nissan Truck', 'JP')
on conflict (make_key) do update set
  display_name = excluded.display_name,
  updated_at = now();
