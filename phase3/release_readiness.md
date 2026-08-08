# Phase 3 Chat Pre-production Release Readiness

This document is review/staging only. It must not be treated as permission to deploy production.

## Required PASS gates

1. Branch chain remains stacked and Draft/unmerged.
2. SQL migrations remain ordered: `010_chat_architecture.sql` -> `011_chat_security.sql` -> `012_chat_storage_security.sql`.
3. Chat Client E2E passes on disposable PostgreSQL.
4. Storage RLS acceptance passes on disposable PostgreSQL/Supabase-compatible storage contract.
5. Attachment Client E2E passes.
6. Attachment Preview hardening passes.
7. Production `index.html` attachment controls remain disabled.
8. No production Railway, Apps Script, Telegram proxy, Sheets/customer-data or secret change exists in this readiness PR.
9. Client files do not contain service-role keys or persistent/public attachment URL helpers.
10. Rollback references remain documented before any production plan.
11. Hosted staging validation, if used later, must be isolated from production and separately evidenced.

## Current blocker policy

Passing disposable CI is necessary but not sufficient for production rollout. A coordinated hosted-staging acceptance and explicit release approval are still required before any production migration, bucket/policy change, merge-to-production, Railway deploy, Apps Script deploy, or feature enablement.
