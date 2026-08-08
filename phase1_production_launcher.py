"""Production entrypoint for the JACC Phase 1 sequential broker flow.

This launcher enables the guarded Phase 1 path before importing the existing
production launch stack. Keeping the flag here avoids changing legacy_bot.py
and makes the production cutover explicit and reversible.
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
import device_reset_patch  # noqa: F401,E402  (admin /resetdevice command)
import auction_deposit_mmk_patch  # noqa: F401,E402  (MMK 1,000,000 auction deposit)
import auction_deposit_text_patch  # noqa: F401,E402  (legacy reply/edit deposit text)

# Railway auto-deploy trigger: resetdevice command enabled in production.
# Retry trigger after the previous Metal builder scheduling stall.
# Active queue launcher now imports device_reset_patch directly as well.

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
