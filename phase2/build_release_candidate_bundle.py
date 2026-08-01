"""Build a reviewable JACC Phase 2 release-candidate ZIP.

This tool is staged only. It never deploys Apps Script, Railway, or the website.
It accepts owner-exported current Apps Script sources, applies the guarded
transformers, packages the additive Phase 2 modules and runtime files, scans for
literal credentials, and writes a SHA-256 manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Callable

from phase2.apply_apps_script_code_gs import apply_patch_text as patch_code
from phase2.apply_apps_script_payment_gs import apply_patch_text as patch_payment
from phase2.apply_apps_script_phase3_payments_gs import (
    apply_patch_text as patch_phase3_payments,
)
from phase2.apply_apps_script_registration_gs import (
    apply_patch_text as patch_registration,
)


class ReleaseBundleError(RuntimeError):
    """Raised when the release candidate cannot be built safely."""


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXED_ZIP_TIMESTAMP = (2026, 8, 1, 0, 0, 0)

_APPS_SCRIPT_ASSETS = {
    "AppsScript/Phase2MembershipSecurity.gs": (
        "phase2/apps_script_membership_security_patch.gs"
    ),
    "AppsScript/Phase2PaymentApproval.gs": (
        "phase2/apps_script_payment_approval_patch.gs"
    ),
    "AppsScript/Phase2DeviceBinding.gs": (
        "phase2/apps_script_device_binding_patch.gs"
    ),
    "AppsScript/Phase2Routes.gs": "phase2/apps_script_release_routes.gs",
    "AppsScript/Phase2WebsitePayment.gs": (
        "phase2/apps_script_website_payment_patch.gs"
    ),
    "AppsScript/Phase2Phase3Payment.gs": (
        "phase2/apps_script_phase3_payment_patch.gs"
    ),
    "AppsScript/Phase2TriggerGuard.gs": "phase2/apps_script_trigger_guard.gs",
}

_RAILWAY_ASSETS = {
    "Railway/phase2_membership_guard.py": "phase2_membership_guard.py",
    "Railway/phase2/install.py": "phase2/install.py",
    "Railway/phase2/legacy_sheet_auth.py": "phase2/legacy_sheet_auth.py",
    "Railway/phase2/channel_reactivation.py": "phase2/channel_reactivation.py",
    "Railway/phase2/payment_approval.py": "phase2/payment_approval.py",
    "Railway/phase2/payment_callback.py": "phase2/payment_callback.py",
}

_SECRET_PATTERNS = (
    re.compile(
        rb"(?i)(?:JACC_SERVER_KEY|SHEET_SERVER_KEY|BOT_TOKEN)\s*[:=]\s*"
        rb"[\"'][^\"'\r\n]{8,}[\"']"
    ),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(rb"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
)

_RELEASE_README = """# JACC Phase 2 Release Candidate

Status: REVIEW ONLY. Do not deploy one component by itself.

## Contents

- Four guarded Apps Script candidates generated from the owner-exported current
  sources.
- Seven additive Phase 2 Apps Script modules.
- Generated Phase 2 website.
- Railway Phase 2 installer and its runtime dependencies.
- SHA-256 manifest for every packaged file and every source input.

## Mandatory release order

1. Back up every current Apps Script file/version and the Members sheet.
2. Review the four generated Apps Script candidates against the current project.
3. Add the seven additive Apps Script modules.
4. Run the trigger audit and disable `monthlyPasswordReset` unless explicitly
   retained.
5. Set matching secrets outside this ZIP:
   - Apps Script property `JACC_SERVER_KEY`
   - Railway variable `SHEET_SERVER_KEY`
6. Confirm the Telegram bot has channel ban/unban permission.
7. Import and run `phase2.install()` before `legacy_bot.main()` registers
   handlers.
8. Deploy Apps Script, Railway, and Website in one maintenance window.
9. Run the full live acceptance matrix before marking PR #12 Ready.

## Rollback

On any failed acceptance test, roll back Railway and Website to the previous
release and redeploy the previous Apps Script version. Do not delete Members,
ledger, Finance, payment, registration, audit, or recovery rows.

This ZIP deliberately contains no production server key, bot token, customer
rows, passwords, tokens, installation IDs, or device hashes.
"""

_ACTIVATION_ORDER = """JACC Phase 2 Railway activation contract

1. Keep the existing production launcher unchanged until the coordinated window.
2. During activation, import the Phase 2 installer and call phase2.install().
3. Call it before legacy_bot.main() registers Telegram handlers.
4. Do not activate Railway before the matching Apps Script deployment is ready.
5. Missing SHEET_SERVER_KEY must fail closed; never log or print the value.
"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_required(path: Path, label: str) -> str:
    if not path.is_file():
        raise ReleaseBundleError(f"missing {label}: {path}")
    return path.read_text(encoding="utf-8")


def _patch_source(
    source: str,
    patcher: Callable[[str], str],
    label: str,
) -> bytes:
    try:
        patched = patcher(source)
    except Exception as exc:  # guarded transformers expose specific errors
        raise ReleaseBundleError(f"{label} transformer rejected source: {exc}") from exc
    if patched == source:
        # Already-patched inputs are valid, but still pass transformer validation.
        return patched.encode("utf-8")
    return patched.encode("utf-8")


def _load_repo_asset(project_root: Path, relative_path: str) -> bytes:
    path = project_root / relative_path
    if not path.is_file():
        raise ReleaseBundleError(f"missing staged repository asset: {relative_path}")
    return path.read_bytes()


def _scan_for_literal_secrets(files: dict[str, bytes]) -> None:
    for name, content in files.items():
        for pattern in _SECRET_PATTERNS:
            if pattern.search(content):
                raise ReleaseBundleError(
                    f"literal credential pattern detected in bundle file: {name}"
                )


def _zip_write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_release_bundle(
    *,
    code_path: Path,
    payment_path: Path,
    registration_path: Path,
    phase3_path: Path,
    output_path: Path,
    project_root: Path | None = None,
) -> Path:
    """Build and return a deterministic review-only release candidate ZIP."""

    root = project_root or PROJECT_ROOT
    sources = {
        "Code.gs": _read_required(code_path, "Code.gs"),
        "Payment.gs": _read_required(payment_path, "Payment.gs"),
        "Registration.gs": _read_required(registration_path, "Registration.gs"),
        "Phase3Payments.gs": _read_required(phase3_path, "Phase3Payments.gs"),
    }

    files: dict[str, bytes] = {
        "AppsScript/Code.gs": _patch_source(sources["Code.gs"], patch_code, "Code.gs"),
        "AppsScript/Payment.gs": _patch_source(
            sources["Payment.gs"], patch_payment, "Payment.gs"
        ),
        "AppsScript/Registration.gs": _patch_source(
            sources["Registration.gs"], patch_registration, "Registration.gs"
        ),
        "AppsScript/Phase3Payments.gs": _patch_source(
            sources["Phase3Payments.gs"],
            patch_phase3_payments,
            "Phase3Payments.gs",
        ),
        "Website/index.html": _load_repo_asset(root, "index.html"),
        "RELEASE_README.md": _RELEASE_README.encode("utf-8"),
        "Railway/ACTIVATION_ORDER.txt": _ACTIVATION_ORDER.encode("utf-8"),
    }

    for bundle_name, repo_path in {**_APPS_SCRIPT_ASSETS, **_RAILWAY_ASSETS}.items():
        files[bundle_name] = _load_repo_asset(root, repo_path)

    _scan_for_literal_secrets(files)

    manifest = {
        "formatVersion": 1,
        "status": "review-only",
        "productionDeployed": False,
        "sourceSha256": {
            name: _sha256(text.encode("utf-8")) for name, text in sorted(sources.items())
        },
        "files": {
            name: {"sha256": _sha256(data), "bytes": len(data)}
            for name, data in sorted(files.items())
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    files["manifest.json"] = manifest_bytes

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as archive:
        for name in sorted(files):
            _zip_write(archive, name, files[name])

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--payment", required=True, type=Path)
    parser.add_argument("--registration", required=True, type=Path)
    parser.add_argument("--phase3", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = build_release_bundle(
        code_path=args.code,
        payment_path=args.payment,
        registration_path=args.registration,
        phase3_path=args.phase3,
        output_path=args.output,
    )
    print(f"JACC Phase 2 release candidate written: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
