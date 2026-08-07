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
