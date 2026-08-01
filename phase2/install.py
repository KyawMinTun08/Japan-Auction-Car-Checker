"""Single Phase 2 runtime installer.

Call ``install()`` before ``legacy_bot.main()`` registers Telegram handlers.
This keeps membership hardening and renewed-member channel reactivation in one
controlled activation point. Payment approval remains an explicit helper until
the legacy ``slip_ok_`` callback is refactored to call it.
"""

from __future__ import annotations

from types import SimpleNamespace

import phase2_membership_guard
from phase2 import channel_reactivation, payment_approval


def install() -> SimpleNamespace:
    membership = phase2_membership_guard.install()
    channel = channel_reactivation.install()
    return SimpleNamespace(
        membership=membership,
        channel=channel,
        payment=SimpleNamespace(
            approve_pending_payment=payment_approval.approve_pending_payment,
            build_idempotency_key=payment_approval.build_idempotency_key,
        ),
    )
