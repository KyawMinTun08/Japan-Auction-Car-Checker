# JACC Phase 1 — Final Merge Checklist

## Current production status

The Phase 1 Telegram bot path is deployed on Railway and the following live checks have passed:

- Customer request creation and canonical Request ID consistency
- Duplicate active-request prevention
- Customer cancellation and queue removal
- Broker availability synchronization between Google Sheets and Supabase
- Real sequential Broker offer delivery and acceptance
- Customer ↔ Broker proxy chat in both directions
- Close Chat, rating, and CLOSED request status
- Encrypted logical backup and logical restore verification
- Database self-test: decline routing, concurrent accept lock, capacity guard, and expiry
- Live resilience test: outbox retry-to-dead-letter and 48-hour stale reassignment
- GitHub CI and all three Railway Phase 1 services

## Blocking item before the final pilot

The first `/phase1finalpilot` run found a PostgreSQL ambiguity in the deployed `jacc_dispatch_next_offer()` function:

```text
column reference "request_id" is ambiguous
SQLSTATE 42702
```

Synthetic test rows were cleaned up. No real customer or broker data was changed.

Repository migration prepared:

```text
phase1/sql/008_fix_dispatch_offer_ambiguity.sql
```

The migration fully qualifies `request_id`, `status`, `expires_at`, `sequence_no`, and related table references in the dispatch function. A regression test is included in:

```text
phase1/tests/test_sql_dispatch_hotfix.py
```

## Steps to finish at the laptop

1. Open Supabase project `slhhncwrbyvocajijuir`.
2. Open **SQL Editor** → **New query**.
3. Copy all SQL from `phase1/sql/008_fix_dispatch_offer_ambiguity.sql`.
4. Run the query and confirm Success.
5. In the Telegram Admin account run:

```text
/phase1finalpilot
```

Expected result:

- Isolated restart recovery PASS
- 10 requests dispatched
- 10 offers accepted
- 10 assignments completed
- 10 distinct synthetic brokers used
- Synthetic cleanup completed

6. Run:

```text
/phase1check
```

Confirm no stuck, retrying, or dead-letter outbox rows remain.

## Final PR decision

Only after the migration and final pilot pass:

1. Confirm PR #8 is mergeable.
2. Confirm Phase 1 GitHub Actions CI passes on the latest head.
3. Confirm Railway checks pass for:
   - `web`
   - `Japan-Auction-Car-Checker`
   - `peaceful-luck`
4. Mark PR #8 ready for review.
5. Merge PR #8 into `main` using a merge commit or squash only after the production checks above are green.

## Rollback plan

- Do not remove the Phase 1 branch immediately after merge.
- Keep the pre-hotfix backup branch/ref available until the post-merge smoke test passes.
- If Telegram polling or assignment fails after merge, redeploy the last known-good Phase 1 branch commit.
- Do not delete Supabase data during rollback.
- Re-run `/phase1check` after rollback and confirm outbox health.

## Backup limitation

Supabase Free Plan does not provide managed scheduled backups. Current protection is an encrypted logical export with SHA-256 checksum and logical restore verification. This is not a full restore into a separate Supabase project.
