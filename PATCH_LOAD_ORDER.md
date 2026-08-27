# Bot runtime patch chain — load order and winners

`legacy_bot.py` holds the real implementation of every command. Everything
else in this list is a *runtime monkey-patch* module: it imports
`legacy_bot`, defines its own version of some function, and reassigns
`legacy_bot.<name> = its_own_version` (or `ExtBot.<name> = ...`) at import
time. `legacy_bot.main()` reads those same names — `CommandHandler`,
`mypassword_cmd`, etc. — from its own module globals only when it actually
registers handlers, which happens last, after every patch module below has
already run. So **whichever module patches a given name *last* is the one
that's live in production** — earlier patches to that same name are
silently shadowed (the function still exists and is harmless, but nothing
calls it anymore).

This file exists because that turned out to be true for far more of the
codebase than expected — 17 files patch into this chain, not the 5 that
seemed obvious from the surface. It was written by tracing the actual
`Procfile` entrypoint end to end (2026-08-27), not by guessing from
filenames. **If you add a new patch module or change an import order,
re-verify this table** — a stale copy of this doc is worse than none.

## Confirmed live entrypoint

```
Procfile: web: python -u phase1_production_launcher.py
```

Any doc/comment elsewhere claiming `queue_launcher.py`, `bot.py`, or
`admin_launcher.py` is "what Railway starts directly" is describing an
**earlier** stage of this project and is no longer accurate — they're all
imported *by* `phase1_production_launcher.py` now, not run standalone.

## Full import cascade (top to bottom = execution order)

```
(Python interpreter startup, before any script code runs)
  sitecustomize.py      — auto-imported by the `site` module if present on sys.path
  usercustomize.py      — auto-imported next, IF user-site is enabled (unverified
                           in this container — see "Open question" below)

phase1_production_launcher.py                  (the actual __main__)
├─ sets PHASE1_* env vars
├─ import queue_launcher
│   ├─ import completion_launcher
│   │   └─ import admin_launcher
│   │       └─ import bot
│   │           └─ import bot_core
│   │               ├─ import legacy_bot as _legacy   (base implementation)
│   │               ├─ patches: submit_request, button_callback,
│   │               │            available_cmd, busy_cmd
│   │               └─ import sitecustomize            (no-op re-import; already
│   │                                                    ran at interpreter startup)
│   │           patches: submit_request, cancelrequest_cmd
│   │       patches: CommandHandler, brokers_cmd, cancelrequest_cmd
│   │   patches: button_callback
│   patches: CommandHandler, brokers_cmd, mypassword_cmd, save_member_to_sheet,
│            send_approval_dm, ExtBot.set_my_commands
│   ├─ import phase1_healthcheck
│   │   patches: CommandHandler, ExtBot.set_my_commands
│   ├─ import phase1_restore_latest
│   │   ├─ patches: ExtBot.send_document
│   │   ├─ import phase1_selftest
│   │   │   patches: CommandHandler, ExtBot.set_my_commands
│   │   ├─ import phase1_broker_sync
│   │   │   patches: addbroker_cmd, available_cmd, busy_cmd
│   │   ├─ import phase1_resilience_test
│   │   │   patches: CommandHandler, ExtBot.set_my_commands
│   │   ├─ import phase1_final_pilot
│   │   │   patches: CommandHandler, ExtBot.set_my_commands
│   │   └─ import phase1_final_pilot_guard
│   │       (no shared-name patches found)
│   └─ import membership_approval_patch
│       patches: save_member_to_sheet, send_approval_dm, button_callback
├─ import phase1_healthcheck        (no-op; already imported above)
├─ import membership_approval_patch (no-op; already imported above)
└─ import device_reset_patch        (NEW — nothing else imports this file)
    patches: CommandHandler, resetdevice_cmd, ExtBot.set_my_commands
```

## Who actually wins, per patched name

Verified by checking every `CommandHandler`-wrapper function in the chain
for whether it special-cases a given command string (i.e. actually swaps
the registered callback) or just passes through to the layer under it.

| Name | Live implementation | Notes |
|---|---|---|
| `CommandHandler` | `device_reset_patch.py` (outermost wrapper) | Only special-cases `resetpass`→adds `resetdevice` alias. Everything else passes through to the layer it wrapped (`phase1_final_pilot.py` at the time it ran), and so on down the chain. |
| `mypassword_cmd` | `queue_launcher.py` | The only wrapper anywhere in the chain that special-cases `"mypassword"` after queue_launcher's own patch runs. `sitecustomize.py` and `usercustomize.py` both define a `mypassword_cmd` too, but both are shadowed — neither is what actually answers `/mypassword`. |
| `mystatus_cmd` | `sitecustomize.py` | **Not** shadowed — no later file patches this name. This is the one genuinely live piece of `sitecustomize.py`. |
| `brokers_cmd` | `queue_launcher.py` | Re-patched by `admin_launcher.py` then `queue_launcher.py`; queue_launcher's is last. |
| `save_member_to_sheet` | `membership_approval_patch.py` | Patched by `queue_launcher.py` then `membership_approval_patch.py`; the latter is imported later inside queue_launcher.py's own bottom-of-file imports. |
| `send_approval_dm` | `membership_approval_patch.py` | Same ordering as above. |
| `button_callback` | `membership_approval_patch.py` | Patched by `bot_core.py` → `completion_launcher.py` → `membership_approval_patch.py`, in that order. |
| `submit_request` | `bot.py` | Patched by `bot_core.py` then `bot.py`; nothing later touches it. |
| `available_cmd` / `busy_cmd` | `phase1_broker_sync.py` | Patched by `bot_core.py` then `phase1_broker_sync.py`. |
| `cancelrequest_cmd` | `admin_launcher.py` | Patched by `bot.py` then `admin_launcher.py`. |
| `resetdevice_cmd` | `device_reset_patch.py` | Only source of this command; not patched elsewhere. |
| `ExtBot.set_my_commands` | `device_reset_patch.py` (outermost) | Chains through `sitecustomize` → `usercustomize` → `queue_launcher` → `phase1_healthcheck` → `phase1_selftest` → `phase1_resilience_test` → `phase1_final_pilot` → `device_reset_patch`; each layer merges its own commands into whatever list the layer under it produced, so nothing here is actually dead — they compose rather than shadow. |
| `ExtBot.send_document` | `phase1_restore_latest.py` | Not patched elsewhere. |
| `addbroker_cmd` | `phase1_broker_sync.py` | Not patched elsewhere. |

## Practically shadowed (safe to know about, not safe to delete blindly)

- `sitecustomize.py`'s `CommandHandler`, `mypassword_cmd`, `brokers_cmd` — defined, but overwritten before `legacy_bot.main()` ever reads them. Its `mystatus_cmd` patch is still live (see table above), so the file as a whole is **not** dead code.
- `usercustomize.py`'s `CommandHandler`, `mypassword_cmd` — same story, and unlike `sitecustomize.py` it does not own any name that stays unshadowed through to the end of the chain. Whether Python's user-site mechanism even loads this file in the current container is unverified (see below) — if it doesn't load at all, the file is inert already; if it does load, everything in it is shadowed.
- `admin_launcher.py`'s `CommandHandler` — overwritten by every later `CommandHandler` patch, but its `brokers_cmd`/`cancelrequest_cmd` patches are not — those stay live only until `queue_launcher.py` (`brokers_cmd`) re-patches, so `admin_launcher.py`'s own `brokers_cmd` is *also* shadowed. Its `cancelrequest_cmd` is the one still-live piece.

## Open question — not resolved by static reading

Whether `usercustomize.py` is actually auto-imported by the Python
interpreter in this Railway/Nixpacks container depends on interpreter
flags and `site`-module configuration (`ENABLE_USER_SITE`,
`PYTHONNOUSERSITE`, virtualenv settings) that can't be confirmed by
reading source files — it would need to be checked by adding a one-line
log statement and inspecting a deploy's startup logs, or running
`python -c "import sys; print('usercustomize' in sys.modules)"` in the
actual container. Nothing in this chain depends on the answer either way
(every name it patches is shadowed downstream regardless), but it's worth
knowing before deleting the file outright.

## Other entrypoint scripts in this repo (not used by Railway)

- `menu_launcher.py` references `sitecustomize`/`usercustomize` but is not
  imported by anything in the live chain and is not named in the
  `Procfile`. Appears to be an earlier or alternate entrypoint, currently
  unused. Do not assume it's exercised by anything running in production.
