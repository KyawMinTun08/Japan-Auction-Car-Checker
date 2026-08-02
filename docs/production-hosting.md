# JACC production hosting

## Decision

- **Primary website:** GitHub Pages
- **Secondary preview/fallback:** Vercel
- **Telegram bot:** Railway
- **Membership and payment backend:** Google Apps Script + Google Sheets during Phase 2 rollout

## Release boundary

A Vercel preview failure must not block a Telegram/Railway-only release unless the release also changes the website. Website, Railway, and Apps Script must still be deployed together when a Phase 2 membership contract changes across all three components.

## Current static deployment

The repository root is a static site. `vercel.json` exists only to make Vercel preview deployments deterministic. The public production URL remains the GitHub Pages URL until an explicit hosting migration is approved.
