from __future__ import annotations

from types import SimpleNamespace

from phase2 import install as phase2_install


def test_phase2_installer_activates_membership_before_channel(monkeypatch) -> None:
    order: list[str] = []

    def install_membership():
        order.append("membership")
        return SimpleNamespace(name="membership")

    def install_channel():
        order.append("channel")
        return SimpleNamespace(name="channel")

    async def approve_payment(**kwargs):
        return kwargs

    def build_key(member_id, payment):
        return f"key-{member_id}-{payment['id']}"

    monkeypatch.setattr(
        phase2_install.phase2_membership_guard,
        "install",
        install_membership,
    )
    monkeypatch.setattr(
        phase2_install.channel_reactivation,
        "install",
        install_channel,
    )
    monkeypatch.setattr(
        phase2_install.payment_approval,
        "approve_pending_payment",
        approve_payment,
    )
    monkeypatch.setattr(
        phase2_install.payment_approval,
        "build_idempotency_key",
        build_key,
    )

    installed = phase2_install.install()

    assert order == ["membership", "channel"]
    assert installed.membership.name == "membership"
    assert installed.channel.name == "channel"
    assert installed.payment.approve_pending_payment is approve_payment
    assert installed.payment.build_idempotency_key is build_key
