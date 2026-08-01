-- JACC Phase 1 migration part: 005_rls_and_permissions.sql
-- Run migrations in filename order.

begin;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table public.jacc_profiles enable row level security;
alter table public.jacc_memberships enable row level security;
alter table public.jacc_broker_profiles enable row level security;
alter table public.jacc_service_requests enable row level security;
alter table public.jacc_request_offers enable row level security;
alter table public.jacc_request_assignments enable row level security;
alter table public.jacc_request_updates enable row level security;
alter table public.jacc_request_status_history enable row level security;
alter table public.jacc_audit_logs enable row level security;

-- Profiles: self, assigned counterpart through backend, or admin.
drop policy if exists jacc_profiles_self_read on public.jacc_profiles;
create policy jacc_profiles_self_read on public.jacc_profiles
for select using (id = public.jacc_current_profile_id() or public.jacc_is_admin());

-- Membership: member can read only own record; admin can manage.
drop policy if exists jacc_memberships_self_read on public.jacc_memberships;
create policy jacc_memberships_self_read on public.jacc_memberships
for select using (user_id = public.jacc_current_profile_id() or public.jacc_is_admin());

-- Broker public operational fields can be read by brokers/admin; writes via backend RPC/service role.
drop policy if exists jacc_broker_profiles_read on public.jacc_broker_profiles;
create policy jacc_broker_profiles_read on public.jacc_broker_profiles
for select using (user_id = public.jacc_current_profile_id() or public.jacc_is_admin());

-- Customer sees own requests; assigned broker sees assigned requests; admin sees all.
drop policy if exists jacc_requests_read on public.jacc_service_requests;
create policy jacc_requests_read on public.jacc_service_requests
for select using (
  customer_id = public.jacc_current_profile_id()
  or assigned_broker_id = public.jacc_current_profile_id()
  or public.jacc_is_admin()
);

-- Customer creates only own request through RPC; direct insert remains blocked.
drop policy if exists jacc_requests_no_direct_insert on public.jacc_service_requests;
create policy jacc_requests_no_direct_insert on public.jacc_service_requests
for insert with check (false);

-- Broker sees only own offers; admin sees all.
drop policy if exists jacc_offers_read on public.jacc_request_offers;
create policy jacc_offers_read on public.jacc_request_offers
for select using (broker_id = public.jacc_current_profile_id() or public.jacc_is_admin());

-- Assignment visible to customer, assigned broker, and admin.
drop policy if exists jacc_assignments_read on public.jacc_request_assignments;
create policy jacc_assignments_read on public.jacc_request_assignments
for select using (
  broker_id = public.jacc_current_profile_id()
  or exists (
    select 1 from public.jacc_service_requests r
    where r.id = request_id and r.customer_id = public.jacc_current_profile_id()
  )
  or public.jacc_is_admin()
);

-- Updates visible only inside the same request relationship.
drop policy if exists jacc_updates_read on public.jacc_request_updates;
create policy jacc_updates_read on public.jacc_request_updates
for select using (
  exists (
    select 1 from public.jacc_service_requests r
    where r.id = request_id
      and (
        r.customer_id = public.jacc_current_profile_id()
        or r.assigned_broker_id = public.jacc_current_profile_id()
        or public.jacc_is_admin()
      )
  )
);

-- Status history follows request access.
drop policy if exists jacc_status_history_read on public.jacc_request_status_history;
create policy jacc_status_history_read on public.jacc_request_status_history
for select using (
  exists (
    select 1 from public.jacc_service_requests r
    where r.id = request_id
      and (
        r.customer_id = public.jacc_current_profile_id()
        or r.assigned_broker_id = public.jacc_current_profile_id()
        or public.jacc_is_admin()
      )
  )
);

-- Audit logs: admin only.
drop policy if exists jacc_audit_admin_read on public.jacc_audit_logs;
create policy jacc_audit_admin_read on public.jacc_audit_logs
for select using (public.jacc_is_admin());

-- ---------------------------------------------------------------------------
-- FUNCTION EXECUTION PERMISSIONS
-- ---------------------------------------------------------------------------

revoke all on function public.jacc_create_my_request(public.jacc_service_type, jsonb) from public;
revoke all on function public.jacc_create_request_for_customer(uuid, public.jacc_service_type, jsonb) from public;
revoke all on function public.jacc_dispatch_next_offer(uuid) from public;
revoke all on function public.jacc_accept_offer(uuid, uuid) from public;
revoke all on function public.jacc_decline_offer(uuid, uuid, text) from public;
revoke all on function public.jacc_expire_pending_offers() from public;
revoke all on function public.jacc_record_meaningful_update(uuid, uuid, text, jsonb) from public;
revoke all on function public.jacc_reassign_stale_requests() from public;

-- Premium App customers may create their own request through RLS-aware auth.
grant execute on function public.jacc_create_my_request(public.jacc_service_type, jsonb) to authenticated;

-- Telegram bridge, offer dispatch, broker actions and timers must go through Railway/server only.
grant execute on function public.jacc_create_request_for_customer(uuid, public.jacc_service_type, jsonb) to service_role;
grant execute on function public.jacc_dispatch_next_offer(uuid) to service_role;
grant execute on function public.jacc_accept_offer(uuid, uuid) to service_role;
grant execute on function public.jacc_decline_offer(uuid, uuid, text) to service_role;
grant execute on function public.jacc_expire_pending_offers() to service_role;
grant execute on function public.jacc_record_meaningful_update(uuid, uuid, text, jsonb) to service_role;
grant execute on function public.jacc_reassign_stale_requests() to service_role;

commit;
