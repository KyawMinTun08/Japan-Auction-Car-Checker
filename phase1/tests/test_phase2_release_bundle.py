from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from phase2 import build_release_candidate_bundle as bundle


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fake_project(root: Path) -> None:
    for relative in {
        "index.html",
        *bundle._APPS_SCRIPT_ASSETS.values(),
        *bundle._RAILWAY_ASSETS.values(),
    }:
        _write(root / relative, f"asset:{relative}\n")


def _sources(root: Path) -> dict[str, Path]:
    return {
        "code_path": _write(root / "sources/Code.gs", "CURRENT_CODE\n"),
        "payment_path": _write(root / "sources/Payment.gs", "CURRENT_PAYMENT\n"),
        "registration_path": _write(
            root / "sources/Registration.gs", "CURRENT_REGISTRATION\n"
        ),
        "phase3_path": _write(
            root / "sources/Phase3Payments.gs", "CURRENT_PHASE3\n"
        ),
    }


def test_builder_packages_candidates_assets_and_valid_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "repo"
    _fake_project(project)
    sources = _sources(tmp_path)

    monkeypatch.setattr(bundle, "patch_code", lambda text: "PATCHED_CODE\n" + text)
    monkeypatch.setattr(bundle, "patch_payment", lambda text: "PATCHED_PAYMENT\n" + text)
    monkeypatch.setattr(
        bundle,
        "patch_registration",
        lambda text: "PATCHED_REGISTRATION\n" + text,
    )
    monkeypatch.setattr(
        bundle,
        "patch_phase3_payments",
        lambda text: "PATCHED_PHASE3\n" + text,
    )

    output = tmp_path / "JACC_Phase2_Release_Candidate.zip"
    result = bundle.build_release_bundle(
        **sources,
        output_path=output,
        project_root=project,
    )

    assert result == output
    assert output.is_file()

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        required = {
            "AppsScript/Code.gs",
            "AppsScript/Payment.gs",
            "AppsScript/Registration.gs",
            "AppsScript/Phase3Payments.gs",
            "AppsScript/Phase2MembershipSecurity.gs",
            "AppsScript/Phase2PaymentApproval.gs",
            "AppsScript/Phase2DeviceBinding.gs",
            "AppsScript/Phase2Routes.gs",
            "AppsScript/Phase2WebsitePayment.gs",
            "AppsScript/Phase2Phase3Payment.gs",
            "AppsScript/Phase2TriggerGuard.gs",
            "Website/index.html",
            "Railway/phase2/install.py",
            "Railway/phase2/payment_callback.py",
            "Railway/ACTIVATION_ORDER.txt",
            "RELEASE_README.md",
            "manifest.json",
        }
        assert required <= names

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["status"] == "review-only"
        assert manifest["productionDeployed"] is False
        assert set(manifest["sourceSha256"]) == {
            "Code.gs",
            "Payment.gs",
            "Registration.gs",
            "Phase3Payments.gs",
        }

        for name, metadata in manifest["files"].items():
            data = archive.read(name)
            assert metadata["bytes"] == len(data)
            assert metadata["sha256"] == hashlib.sha256(data).hexdigest()

        assert archive.read("AppsScript/Code.gs").startswith(b"PATCHED_CODE")
        assert b"Do not deploy one component by itself" in archive.read(
            "RELEASE_README.md"
        )


def test_builder_rejects_literal_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "repo"
    _fake_project(project)
    sources = _sources(tmp_path)
    token_shaped_value = "123456789:" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

    monkeypatch.setattr(
        bundle,
        "patch_code",
        lambda text: f'var BOT_TOKEN = "{token_shaped_value}";\n',
    )
    monkeypatch.setattr(bundle, "patch_payment", lambda text: text)
    monkeypatch.setattr(bundle, "patch_registration", lambda text: text)
    monkeypatch.setattr(bundle, "patch_phase3_payments", lambda text: text)

    output = tmp_path / "unsafe.zip"
    with pytest.raises(bundle.ReleaseBundleError, match="literal credential"):
        bundle.build_release_bundle(
            **sources,
            output_path=output,
            project_root=project,
        )

    assert not output.exists()


def test_builder_fails_when_source_or_staged_asset_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "repo"
    _fake_project(project)
    (project / "index.html").unlink()
    sources = _sources(tmp_path)

    monkeypatch.setattr(bundle, "patch_code", lambda text: text)
    monkeypatch.setattr(bundle, "patch_payment", lambda text: text)
    monkeypatch.setattr(bundle, "patch_registration", lambda text: text)
    monkeypatch.setattr(bundle, "patch_phase3_payments", lambda text: text)

    with pytest.raises(bundle.ReleaseBundleError, match="missing staged repository asset"):
        bundle.build_release_bundle(
            **sources,
            output_path=tmp_path / "missing.zip",
            project_root=project,
        )
