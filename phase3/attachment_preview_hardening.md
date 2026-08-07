# Phase 3 — Private Attachment Preview Hardening

Status: REVIEW/STAGING ONLY

## Goal
Harden authorized private photo rendering after attachment-client acceptance without changing production.

## Acceptance matrix
1. Loading state before private retrieval resolves.
2. Success state for authorized JPEG/PNG/WebP.
3. Expired-link state requests a fresh short-lived private retrieval URL.
4. Denied state never falls back to public URL.
5. Missing-object state shows a safe non-sensitive error.
6. Offline/broken-image state supports retry without duplicating messages or attachment metadata.
7. No permanent signed/public URL is stored in DOM datasets, persistent state, logs, message rows, or attachment metadata.
8. Mobile layout remains usable at narrow widths with conversation list/chat transitions.
9. Alt text, focus order and keyboard activation are present for attachment preview controls.
10. Existing Storage RLS, attachment-client, and chat-client E2E workflows remain green.
11. Production `index.html` photo/document controls remain disabled.

## Test strategy
- Static client contract tests for state transitions and URL leakage guards.
- Disposable PostgreSQL/Supabase-compatible regression using migrations 010 -> 012.
- Re-run attachment client and chat client E2E workflows.
- Review-only browser preview; no production deployment.

## Safety
No production Supabase migration, bucket/policy change, Railway change, Apps Script change, Telegram proxy change, Google Sheet/customer-data change, secret use, merge or Ready transition.
