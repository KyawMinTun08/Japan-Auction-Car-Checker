"""Sanitize URL-related Railway variables before starting the JACC bot.

This wrapper keeps production behavior unchanged while removing accidental
leading/trailing whitespace and non-printable ASCII characters that can make
HTTP clients reject a URL.  It intentionally logs no secret values.
"""

from __future__ import annotations

import os
import runpy


def _clean_env(name: str) -> None:
    value = os.environ.get(name)
    if value is None:
        return
    cleaned = "".join(ch for ch in value.strip() if ch >= " " and ch != "\x7f")
    os.environ[name] = cleaned


for _name in ("SHEET_ID", "SHEET_WEBHOOK"):
    _clean_env(_name)

runpy.run_path("queue_launcher.py", run_name="__main__")
