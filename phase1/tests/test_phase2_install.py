from __future__ import annotations

from types import SimpleNamespace

from phase2 import install as phase2_install


def test_phase2_installer_uses_safe_dependency_order(monkeypatch) -> None:
    order: list[str] = []

    def install_membership():
        order.append("membership")
        return SimpleNamespace(name="membership")

    def install_sheet_auth():
        order.append("sheet_auth")
        return SimpleNamespace(name="sheet_auth")

    def install_channel():
        order.append("channel")
        return SimpleNamespace(name="channel")

    def install_payment():
        order.append("payment")
        return SimpleNamespace(name="payment")

    monkeypatch.setattr(
        phase2_install.phase2_membership_guard,
        "install",
        install_membership,
    )
    monkeypatch.setattr(
        phase2_install.legacy_sheet_auth,
        "install",
        install_sheet_auth,
    )
    monkeypatch.setattr(
        phase2_install.channel_reactivation,
        "install",
        install_channel,
    )
    monkeypatch.setattr(
        phase2_install.payment_callback,
        "install",
        install_payment,
    )

    installed = phase2_install.install()

    assert order == ["membership", "sheet_auth", "channel", "payment"]
    assert installed.membership.name == "membership"
    assert installed.sheet_auth.name == "sheet_auth"
    assert installed.channel.name == "channel"
    assert installed.payment.name == "payment"
