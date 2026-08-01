"""Single Phase 2 runtime installer.

Call ``install()`` before ``legacy_bot.main()`` registers Telegram handlers.
The order is deliberate:

1. membership functions become expiry-aware and authenticated;
2. approval/channel delivery gains old-ban auto-reactivation;
3. the Telegram ``slip_ok_`` callback uses the retry-safe payment contract.
"""

from __future__ import annotations

from types import SimpleNamespace

import phase2_membership_guard
from phase2 import channel_reactivation, payment_callback


def install() -> SimpleNamespace:
    membership = phase2_membership_guard.install()
    channel = channel_reactivation.install()
    payment = payment_callback.install()
    return SimpleNamespace(
        membership=membership,
        channel=channel,
        payment=payment,
    )
