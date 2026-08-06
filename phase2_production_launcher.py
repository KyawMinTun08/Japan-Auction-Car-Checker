"""Guarded JACC Phase 2 production entrypoint.

This launcher keeps the proven Phase 1 queue/runtime stack, including the live
Sheet URL sanitization and chassis-safe price parsing guards, then installs the
staged Phase 2 membership, payment, device, and channel wrappers before
``legacy_bot.main()`` registers Telegram handlers.

Railway must continue using the Phase 1 launcher until the coordinated Apps
Script, Railway, and website release window. Switching to this entrypoint is
an explicit and reversible cutover step.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback

# These values must exist before bot_core/sitecustomize are imported.
os.environ.setdefault("PHASE1_SEQUENTIAL_ENABLED", "1")
os.environ.setdefault("PHASE1_POLL_SECONDS", "30")
os.environ.setdefault("PHASE1_QUEUE_BATCH_SIZE", "25")

# Import the exact safety wrapper currently used by production first. Importing
# it sanitizes Sheet URL variables and patches legacy price parsing without
# starting the bot because its main block is guarded by __name__.
import safe_queue_launcher as phase1_safe  # noqa: E402

# Reuse the already-imported and safety-patched queue launcher instance.
queue_launcher = phase1_safe._queue

import phase1_healthcheck  # noqa: F401,E402
from phase2 import install as phase2_install  # noqa: E402


logger = logging.getLogger("jacc-phase2-launcher")


def _required_setting(name: str, value: object) -> str:
    """Return one configured value without ever logging or printing it."""
    configured = str(value or "").strip()
    if not configured:
        raise RuntimeError(f"{name} is not configured")
    return configured


def install_phase2_runtime():
    """Fail closed, then install Phase 2 before Telegram handler registration."""
    _required_setting("SHEET_SERVER_KEY", os.environ.get("SHEET_SERVER_KEY"))
    _required_setting(
        "SHEET_WEBHOOK",
        getattr(queue_launcher._legacy, "SHEET_WEBHOOK", ""),
    )
    installed = phase2_install.install()
    logger.info("Phase 2 membership runtime installed")
    return installed


PHASE2_RUNTIME = install_phase2_runtime()


if __name__ == "__main__":
    try:
        asyncio.run(queue_launcher.main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.error("FATAL CRASH: %s", exc)
        logger.error(traceback.format_exc())
        raise
