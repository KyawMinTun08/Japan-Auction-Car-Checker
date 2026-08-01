"""Single Phase 2 runtime installer.

Call ``install()`` before ``legacy_bot.main()`` registers Telegram handlers.
The order is deliberate:

1. membership functions become expiry-aware and authenticated;
2. remaining direct legacy membership Sheet calls gain scoped server-key auth;
3. approval/channel delivery gains old-ban auto-reactivation;
4. the Telegram ``slip_ok_`` callback uses the retry-safe payment contract.
"""

from __future__ import annotations

from types import SimpleNamespace

import phase2_membership_guard
from phase2 import channel_reactivation, legacy_sheet_auth, payment_callback


def install() -> SimpleNamespace:
    membership = phase2_membership_guard.install()
    sheet_auth = legacy_sheet_auth.install()
    channel = channel_reactivation.install()
    payment = payment_callback.install()
    return SimpleNamespace(
        membership=membership,
        sheet_auth=sheet_auth,
        channel=channel,
        payment=payment,
    )
