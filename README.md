# Japan Auction Car Checker

Japan Auction Car Price Tracker & Broker Marketplace.

## JACC Broker Service — Phase 1

The first database-backed broker assignment foundation is available in [`phase1/`](phase1/README.md).

Phase 1 includes:

- Premium App and Standard Telegram service routing
- Auction and Outside Car request types
- Sequential fair broker offers with a 10-minute expiry
- One Auction slot and one Outside Car slot per broker
- PostgreSQL transaction locking for offer acceptance
- A 48-hour meaningful-update reassignment worker
- Supabase row-level security and server-only service-role access

This foundation is isolated from the current production flow until the Supabase migrations, Railway environment variables, and Telegram Bot integration are configured and tested.
