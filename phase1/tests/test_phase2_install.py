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

    installed = phase2_install.install()

    assert order == ["membership", "channel"]
    assert installed.membership.name == "membership"
    assert installed.channel.name == "channel"
