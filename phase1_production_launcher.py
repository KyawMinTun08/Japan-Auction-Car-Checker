"""Production entrypoint for the JACC Phase 1 sequential broker flow.

This launcher enables the guarded Phase 1 path before importing the existing
production launch stack. Keeping the flag here avoids changing legacy_bot.py
and makes the production cutover explicit and reversible.

This is the file the Procfile actually starts (`web: python -u
phase1_production_launcher.py`) — every runtime patch module in this repo
(17 files, most importing each other in a chain) ultimately gets pulled in
through the `import queue_launcher` below. If you're trying to figure out
which file's version of some patched function (CommandHandler,
mypassword_cmd, etc.) is the one actually running, see PATCH_LOAD_ORDER.md
at the repo root — it traces the full cascade and states which module wins
for each shared name, verified against this exact entrypoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback

# These values must exist before bot_core and sitecustomize are imported.
os.environ.setdefault("PHASE1_SEQUENTIAL_ENABLED", "1")
os.environ.setdefault("PHASE1_POLL_SECONDS", "30")
os.environ.setdefault("PHASE1_QUEUE_BATCH_SIZE", "25")

import queue_launcher  # noqa: E402  (environment must be set first)
import phase1_healthcheck  # noqa: F401,E402  (patch before handler registration)
import membership_approval_patch  # noqa: F401,E402  (safe Sheet retry patch)
import device_reset_patch  # noqa: F401,E402  (admin /resetdevice command)


if __name__ == "__main__":
    try:
        asyncio.run(queue_launcher.main())
    except KeyboardInterrupt:
        logging.getLogger("jacc-phase1-launcher").info("Bot stopped by user")
    except Exception as exc:
        logger = logging.getLogger("jacc-phase1-launcher")
        logger.error("FATAL CRASH: %s", exc)
        logger.error(traceback.format_exc())
        raise
