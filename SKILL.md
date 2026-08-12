---
name: jacc-repository
description: Maintain, debug, and safely extend the Japan Auction Car Checker (JACC) website, Google Apps Script membership API, Telegram bot, and Phase 1 broker workflow without breaking production contracts.
---

# JACC Repository Skill

## Purpose

Use this skill whenever working on the **Japan Auction Car Checker (JACC)** repository.

The goal is to make changes safely across the JACC website, Telegram bot, Google Apps Script backend, membership system, Phase 1 broker/request flow, PWA files, and deployment configuration while preserving existing production behavior.

Repository:

- `KyawMinTun08/Japan-Auction-Car-Checker`
- Default branch: `main`

Do not treat this as a clean greenfield project. It contains production code, compatibility layers, migration/patch files, and newer Phase 1 infrastructure beside legacy code.

---

## 1. Current Production Architecture

JACC is a multi-part system.

### Website / PWA

Primary files:

- `index.html` — main customer-facing web app and UI
- `manifest.json` — PWA manifest
- `sw.js` — service worker
- `icon-192.png`, `icon-512.png` — app icons
- `privacy-policy.html` — privacy page

The website is currently a static app and includes its UI, login flow, charts, data fetches, and member-facing functionality in `index.html`.

The canonical public GitHub Pages URL is based on:

`https://kyawmintun08.github.io/Japan-Auction-Car-Checker/`

When changing the web app, preserve the existing Content Security Policy unless the requested feature genuinely requires a new allowed origin.

### Google Apps Script / Google Sheets backend

Primary files:

- `Code.gs` — Apps Script API and member/data operations
- `apps-script/` — additional Apps Script-related material when present

`Code.gs` exposes the current Apps Script API through `doGet(e)` and `doPost(e)`.

The **Members** sheet column contract is critical and must not be casually reordered:

| Index | Column |
|---:|---|
| 0 | UserID |
| 1 | Username |
| 2 | StartDate |
| 3 | ExpireDate |
| 4 | Status |
| 5 | CancelCount |
| 6 | Password |
| 7 | Package |
| 8 | Token |

Current constants in `Code.gs` must remain aligned with that order:

```javascript
var C_USERID      = 0;
var C_USERNAME    = 1;
var C_START       = 2;
var C_EXPIRE      = 3;
var C_STATUS      = 4;
var C_CANCELCOUNT = 5;
var C_PASSWORD    = 6;
var C_PACKAGE     = 7;
var C_TOKEN       = 8;
```

Important API actions already handled by `doPost(e)` include member save/update, member listing, login verification, token verification, password lookup/reset, Telegram ID update, status changes, backup/data operations, promo handling, finance/payment logging, and broker-related operations.

Before editing any Apps Script action, inspect the current `doPost(e)` switch and the implementation of the called function. Do not infer an old action shape from previous versions.

### Telegram bot

Important files:

- `bot.py` — current compatibility/safety wrapper
- `bot_core.py` — preserved production bot module surface
- `legacy_bot.py` — large legacy implementation still used through compatibility layers
- `admin_launcher.py`
- `completion_launcher.py`
- `queue_launcher.py`
- `production_launcher.py`
- `phase1_production_launcher.py`
- `membership_approval_patch.py`
- `device_reset_patch.py`
- `sitecustomize.py`
- `usercustomize.py`

**Do not replace `bot.py` with an older monolithic bot file.**

The current `bot.py` imports and re-exports `bot_core.py`, then adds Phase 1 request safety behavior such as duplicate-request protection and central cancellation synchronization.

Treat this wrapper relationship as a production contract unless a task explicitly redesigns the architecture.

### Phase 1 request / broker flow

Relevant files include:

- `phase1/`
- `phase1_broker_sync.py`
- `phase1_final_pilot.py`
- `phase1_final_pilot_guard.py`
- `phase1_healthcheck.py`
- `phase1_production_launcher.py`
- `phase1_resilience_test.py`
- `phase1_restore_latest.py`
- `phase1_selftest.py`
- `phase2/`
- `phase3_payment_callbacks.py`
- `integrations/`

The current production launcher enables the guarded Phase 1 path before importing the queue/production stack.

The production process command is defined by `Procfile` as:

```text
web: python -u phase1_production_launcher.py
```

Do not silently change the production entrypoint.

---

## 2. Source-of-Truth Rules

When several files appear to implement similar behavior, never guess which one is active.

Use these rules:

1. Read `Procfile` first for the deployed Python entrypoint.
2. Follow imports from the active launcher.
3. Treat `bot.py` as the current compatibility/safety wrapper when it is imported by the active stack.
4. Treat `bot_core.py` and `legacy_bot.py` as compatibility-sensitive code.
5. Read the current implementation before applying an older fix from chat history, screenshots, backup files, or copied snippets.
6. Prefer the smallest patch that fixes the reported behavior.
7. Never overwrite a newer production file with an older uploaded copy without a line-by-line comparison.

If repository code conflicts with an old note, the repository is the source of truth unless the user explicitly says the repository version is broken and provides a newer authoritative copy.

---

## 3. Membership System Contract

Membership bugs are high-risk because the website, Telegram bot, Apps Script, and Google Sheet all depend on the same record.

When touching membership code, verify all of the following:

- UserID is read from column A / index `0`.
- Username is read from column B / index `1`.
- Start date is index `2`.
- Expiry date is index `3`.
- Status is index `4`.
- CancelCount is index `5`.
- Password is index `6`.
- Package is index `7`.
- Token is index `8`.

For password-related code, use the password column constant rather than a hard-coded numeric index.

Preferred pattern:

```javascript
String(rows[i][C_PASSWORD] || "")
```

For package-related code:

```javascript
String(rows[i][C_PACKAGE] || "CH")
```

When saving or updating member data, keep password and package writes aligned with the column constants.

Do not add trimming, quoting, or formatting that changes the actual stored password unless the task explicitly changes the password format. UI copy operations should copy only the intended password value, without extra quotes or spaces.

### Login and token flow

When debugging web login:

1. Check the password submitted by `index.html`.
2. Check the `validateLogin` / `verifyLogin` Apps Script action.
3. Check the password column used in Apps Script.
4. Check the returned token and username/package fields.
5. Check `verifyToken` on subsequent page loads.
6. Check expiry/status rules before changing authentication logic.

Never log full passwords, bot tokens, access tokens, service-role keys, or private credentials.

---

## 4. Package and Access Rules

JACC has membership/package behavior shared between Telegram and the website.

When fixing Standard/Premium/Web access problems:

- Inspect current package values in the repository and Apps Script before assuming an old package name.
- Preserve existing active members where possible.
- Avoid migrations that unexpectedly reset passwords, expiry dates, Telegram IDs, or tokens.
- A package upgrade should not silently shorten an existing membership period.
- An extension should not silently change the package unless that is the requested operation.
- Status changes such as active/kicked/banned must be handled separately from package type unless current code intentionally links them.

For Telegram channel access, remember that Telegram bots generally cannot force a user account to join a channel. The system should issue/validate the proper invite or membership flow and then verify access where supported.

---

## 5. Web App Rules

`index.html` is large and production-sensitive.

Before editing it:

1. Locate the exact UI component, function, and event handler involved.
2. Search for duplicate function names or older versions in the same file.
3. Confirm the active API URL/action name used by that feature.
4. Patch only the necessary section.
5. Re-check mobile behavior because JACC is frequently used on phones.

Preserve:

- Burmese font support
- responsive/mobile layout
- existing login behavior unless the task targets login
- Chart.js initialization and chart containers
- CSP compatibility
- PWA registration
- existing member/session storage keys unless intentionally migrated

Do not add a large framework to solve a small UI bug.

### Password copy UX

For password copy buttons:

- copy the exact password value
- do not copy surrounding quotes
- do not copy labels such as `Password:`
- do not introduce leading/trailing spaces
- provide a clear success state after copy

---

## 6. Telegram Bot Rules

The bot is production code. Avoid broad rewrites.

### Preserve compatibility layers

Before changing a Telegram command or request flow:

1. Find whether the handler lives in `bot.py`, `bot_core.py`, `legacy_bot.py`, or a patch module.
2. Follow the imports from `phase1_production_launcher.py` and `queue_launcher.py`.
3. Check whether a monkey patch/wrapper intentionally overrides a legacy function.
4. Change the active layer rather than editing an inactive copy.

### Request safety

The Phase 1 wrapper protects against duplicate active requests and synchronizes customer cancellation with the central request system.

Do not remove these protections while fixing unrelated commands.

When changing request states, keep related records consistent across the central request, offer, assignment, and history tables where the current flow requires them.

### User-facing messages

JACC Telegram messages are primarily Burmese with technical identifiers and commands in English.

Keep messages:

- short enough for mobile reading
- clear about the next action
- consistent with existing command names
- explicit when an operation failed versus when it is still pending

Do not expose stack traces, secrets, internal database IDs, or service keys to end users.

---

## 7. Secrets and Security

Never commit real secrets to the repository.

Examples include:

- Telegram `BOT_TOKEN`
- Supabase service-role keys
- private API keys
- Google service-account credentials
- OAuth client secrets
- private admin passwords
- Railway/Vercel secret values

Use environment variables, Apps Script Properties, or the deployment platform's secret store.

When reviewing a patch, search touched lines for accidental tokens or credentials before committing.

Do not move a secret from an environment variable into JavaScript/HTML just to make a feature easier to call from the browser.

Anything delivered to `index.html` is effectively public to the browser.

---

## 8. Deployment Rules

JACC has multiple deployment surfaces. A GitHub commit does not necessarily deploy all of them.

### Static website

Changes to `index.html`, `manifest.json`, `sw.js`, icons, and other static assets are associated with the GitHub-hosted web app.

After a web change, account for service-worker caching. A correct deployment can appear stale on a phone if an older service worker/cache is still active.

### Python / Telegram bot

The repository currently declares the production process through `Procfile` and `phase1_production_launcher.py`.

When deployment configuration changes, verify:

- the production entrypoint still exists
- imports succeed
- required environment variables remain server-side
- no development launcher accidentally becomes production

### Google Apps Script

Do not assume editing `Code.gs` in GitHub automatically updates the live Apps Script project.

After an Apps Script change, determine the actual sync/deploy method being used. If manual deployment is required, clearly tell the user that the Apps Script deployment/version must also be updated.

---

## 9. Validation Checklist

Run the smallest relevant validation set for the files changed.

### Python changes

At minimum:

```bash
python -m py_compile <changed_python_files>
```

When Phase 1 behavior changes, also inspect/run the most relevant existing self-test, healthcheck, pilot guard, or resilience test instead of inventing a new test harness first.

### Apps Script changes

Check:

- braces and switch/case structure
- action names used by callers
- member column indexes
- returned JSON shape
- date/time zone behavior
- lock usage around writes
- no accidental fall-through in `switch`

### Website changes

Check:

- HTML/JS syntax
- mobile layout
- login
- API calls
- no console-breaking duplicate declarations
- Chart.js still loads
- service worker still registers
- CSP allows every newly required external origin

### Membership regression checks

For member-related changes, verify these scenarios conceptually or with available tests:

- existing active member login
- expired member login
- wrong password
- correct token reload
- package readback
- password retrieval
- member extension
- Standard/Premium upgrade path
- status kick/reactivation behavior

---

## 10. Safe Change Workflow

Use this workflow for JACC fixes and features.

### Step 1 — Identify the affected surface

Classify the issue as one or more of:

- website/UI
- Apps Script/API
- Google Sheet member data
- Telegram command
- Telegram membership/channel access
- Phase 1 request flow
- broker flow
- payment flow
- deployment/configuration

### Step 2 — Read current code

Inspect the active files before proposing a fix.

Do not rely only on an old chat snippet.

### Step 3 — Trace the full path

For example, a login bug may cross:

`index.html` → Apps Script `doPost` → `verifyLogin` → Members sheet → returned token → browser storage.

A request bug may cross:

Telegram handler → wrapper/legacy handler → Phase 1 integration → Supabase request/offer/assignment/history records.

### Step 4 — Make the smallest coherent patch

Avoid unrelated cleanup in the same change.

### Step 5 — Validate

Run relevant syntax/tests and inspect the final diff.

### Step 6 — Deploy only the affected surface

Clearly separate:

- GitHub web deployment
- Railway/Python bot deployment
- Google Apps Script deployment
- database/configuration changes

### Step 7 — Report what changed

State:

- root cause
- files changed
- exact behavior fixed
- tests/checks performed
- any manual deployment step still required

---

## 11. GitHub Change Policy

For non-trivial changes:

- create a feature/fix branch
- keep commits focused
- open a draft PR first unless the user explicitly asks for direct merge
- do not mix unrelated fixes
- inspect changed files before merging

Suggested branch names:

- `agent/fix-member-login`
- `agent/fix-channel-access`
- `agent/web-password-copy`
- `agent/phase1-request-fix`

Never force-push or rewrite `main` history for a normal fix.

---

## 12. High-Risk Files

Treat these as high-risk and inspect carefully before editing:

- `index.html`
- `Code.gs`
- `bot.py`
- `bot_core.py`
- `legacy_bot.py`
- `queue_launcher.py`
- `phase1_production_launcher.py`
- `sitecustomize.py`
- `membership_approval_patch.py`
- `device_reset_patch.py`
- `Procfile`

Avoid wholesale replacement of these files unless there is a verified reason.

---

## 13. Common JACC Failure Patterns

### Wrong member column

Symptom:

- correct password rejected
- package becomes wrong
- password field contains unrelated data

First check the Members column constants and every hard-coded index.

### Password copies with spaces or quotes

Symptom:

- password looks correct but pasted login fails

Check browser copy code and display formatting separately from the stored password.

### Premium member gets wrong access

Trace:

member save/update → package column → Apps Script response → Telegram/web access rule.

Do not patch only the visible label.

### Website works but Telegram channel access fails

Treat website authentication and Telegram channel membership as separate systems. Verify the invite/access path and bot permissions instead of assuming web login automatically joins Telegram.

### Bot fix appears to do nothing

Check whether the edited function is actually active through the current wrapper/launcher stack. Similar functions may exist in legacy and compatibility files.

### GitHub code changed but live Apps Script did not

A repository edit may still require Apps Script sync/redeployment. Verify the deployment boundary.

### Web change appears stale on phone

Check PWA/service-worker cache before reverting correct code.

---

## 14. What Not To Do

Do not:

- replace current production files with old chat attachments without comparing them
- hard-code member column numbers when constants exist
- expose server secrets in `index.html`
- remove Phase 1 request guards to simplify unrelated code
- assume `legacy_bot.py` is the direct production entrypoint
- assume a GitHub commit deploys Google Apps Script
- silently change membership package semantics
- reset existing passwords during a routine package extension
- refactor the whole bot while fixing one command
- change `Procfile` entrypoint without tracing the startup chain
- merge a high-risk patch without checking the diff

---

## 15. Preferred Response Style When Helping With JACC

When explaining a JACC issue to the project owner:

1. Explain the problem in Burmese where practical.
2. Keep file names, function names, commands, API actions, and code identifiers in English.
3. State clearly whether the fix is already committed, only proposed, or still requires a live deployment step.
4. For phone-only steps, give short numbered instructions with the exact button/menu name.
5. Never claim the live bot/site/Apps Script is fixed until the relevant deployed surface is actually updated or verified.

---

## 16. Definition of Done

A JACC task is done only when:

- the correct active code path was identified
- the requested behavior was changed
- unrelated production behavior was preserved
- secrets were not exposed
- relevant validation passed
- the correct deployment surface was identified
- any remaining manual deployment step was stated clearly

For membership or request-flow fixes, also confirm that the change does not break existing active users or leave inconsistent state across JACC's connected systems.
