# JACC Phase 3 Chat UI Review

This task adds a standalone review route at `phase3/chat-preview.html`.

## Why the production `index.html` is not rewritten

The current application already contains working dashboard, price, model, compare, member, login and device-binding flows. Replacing the file would create unnecessary regression risk. The chat interface is therefore reviewed in isolation first and will only be mounted into the existing navigation after security, staging and owner acceptance.

## Included

- Mobile-first conversation list and active conversation screen
- Unread badge and responsive back navigation
- Text composer with a 2,000-character limit
- Safe rendering through `textContent` before HTML insertion
- App-only payload contract with client-generated UUID
- Explicit Premium/App and signed-in profile gate
- Loading/error-ready structure and accessible labels

## Deliberately disabled

- Photo upload
- Voice upload
- Document upload
- Telegram relay
- Production Supabase calls
- Service-role credentials in browser code

The attachment button remains disabled until a private Storage bucket and `storage.objects` policies have been designed, reviewed and tested in isolated staging.

## Integration sequence

1. Run schema migrations 010 and 011 only in isolated staging.
2. Test customer, broker, admin, expired-member, suspended-broker and anonymous access.
3. Add an authenticated server/client adapter using the public anon key only; RLS remains the security boundary.
4. Replace demo data with staging conversation queries.
5. Mount the reviewed component into the existing `index.html` navigation without replacing existing screens.
6. Run mobile, session, device-binding and regression tests before any production decision.

## Safety statement

No production HTML, Apps Script, Railway service, Supabase database, Telegram proxy or secret was changed by this task.
