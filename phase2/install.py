"""Single Phase 2 runtime installer.

Call ``install()`` before ``legacy_bot.main()`` registers Telegram handlers.
This keeps membership hardening and renewed-member channel reactivation in one
controlled activation point.
"""

from __future__ import annotations

from types import SimpleNamespace

import phase2_membership_guard
from phase2 import channel_reactivation


def install() -> SimpleNamespace:
    membership = phase2_membership_guard.install()
    channel = channel_reactivation.install()
    return SimpleNamespace(membership=membership, channel=channel)
