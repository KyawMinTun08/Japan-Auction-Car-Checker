"""Apply small production-safe guards before starting the JACC bot.

The wrapper:
- removes accidental non-printable characters from Sheet environment values;
- prevents a chassis suffix such as ``NT31-236260`` from being parsed as a
  standalone car price;
- leaves the existing Phase 1 bot launcher and handlers otherwise unchanged.

No secret values are logged.
"""

from __future__ import annotations

import asyncio
import os
import re as _stdlib_re
import traceback


def _clean_env(name: str) -> None:
    value = os.environ.get(name)
    if value is None:
        return
    cleaned = "".join(ch for ch in value.strip() if ch >= " " and ch != "\x7f")
    os.environ[name] = cleaned


for _name in ("SHEET_ID", "SHEET_WEBHOOK"):
    _clean_env(_name)


import queue_launcher as _queue  # noqa: E402


_PRICE_PATTERN = r"(?<![A-Z0-9])(\d{4,6})(?![A-Z0-9])"


class _SafeLegacyRegex:
    """Delegate to :mod:`re` while hardening the legacy price search only."""

    def __getattr__(self, name: str):
        return getattr(_stdlib_re, name)

    @staticmethod
    def search(pattern, string, flags=0):
        if pattern != _PRICE_PATTERN:
            return _stdlib_re.search(pattern, string, flags)

        text = str(string or "")
        for match in _stdlib_re.finditer(pattern, text, flags):
            value = int(match.group(1))

            # A numeric suffix immediately following a chassis separator is
            # part of the chassis, not a price (for example NT31-236260).
            if match.start() > 0 and text[match.start() - 1] in "-_/":
                continue

            # A standalone four-digit model year is not a price.
            if 1900 <= value <= 2099:
                continue

            return match
        return None


_queue._legacy.re = _SafeLegacyRegex()


if __name__ == "__main__":
    try:
        asyncio.run(_queue.main())
    except KeyboardInterrupt:
        _queue._legacy.logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as exc:
        _queue._legacy.logger.error("FATAL CRASH: %s", exc)
        _queue._legacy.logger.error(traceback.format_exc())
        raise
