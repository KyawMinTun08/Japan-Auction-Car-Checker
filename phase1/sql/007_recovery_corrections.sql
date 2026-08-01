-- JACC Phase 1 migration part: 007_recovery_corrections.sql
-- Run after 006_reliability_and_recovery.sql.

begin;

-- Preserve the previous worker id before clearing the stale lock.
create or replace function public.jacc_recover_stuck_outbox(
  p_stuck_after interval default interval '10 minutes'
)
returns table (outbox_id uuid, previous_worker text)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select o.id, o.locked_by
    from public.jacc_message_outbox o
    where o.status = 'processing'
      and o.locked_at < now() - p_stuck_after
    for update skip locked
  ), recovered as (
    update public.jacc_message_outbox o
    set status = case
          when o.attempt_count >= o.max_attempts
            then 'dead_letter'::public.jacc_outbox_status
          else 'retrying'::public.jacc_outbox_status
        end,
        available_at = now(),
        locked_at = null,
        locked_by = null,
        last_error = coalesce(o.last_error, 'Recovered after worker interruption'),
        updated_at = now()
    from candidates c
    where o.id = c.id
    returning o.id, c.locked_by
  )
  select recovered.id, recovered.locked_by from recovered;
end;
$$;

revoke execute on function public.jacc_recover_stuck_outbox(interval) from public;
grant execute on function public.jacc_recover_stuck_outbox(interval) to service_role;

commit;
