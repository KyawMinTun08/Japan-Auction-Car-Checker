"""Runtime hardening for Web Premium reminder Google credential loading.

The reminder must read DeviceID directly from the Members Google Sheet.  The
Railway credential may be stored in several real-world formats, so this module
normalises them before gspread is used.  It deliberately never falls back to
Apps Script because the legacy getMembers response cannot prove DeviceID state.
"""

from __future__ import annotations

import ast
import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import web_activation_reminder_patch as _reminder


_REQUIRED = ("client_email", "private_key")


def _normalise_service_account(info: dict[str, Any]) -> dict[str, Any]:
    result = dict(info)

    # Some secret managers wrap the actual credential object.
    for key in (
        "credentials",
        "service_account",
        "serviceAccount",
        "google_credentials",
        "GOOGLE_CREDS_JSON",
    ):
        nested = result.get(key)
        if isinstance(nested, dict):
            result = dict(nested)
            break

    if result.get("private_key"):
        result["private_key"] = str(result["private_key"]).replace("\\n", "\n")

    # token_uri is required by google-auth but is occasionally omitted from
    # hand-copied Railway secrets.  Google's service-account token endpoint is
    # stable, so supplying the canonical value is safe.
    result.setdefault("token_uri", "https://oauth2.googleapis.com/token")
    result.setdefault("type", "service_account")

    missing = [name for name in _REQUIRED if not result.get(name)]
    if missing:
        raise ValueError("service-account fields missing: " + ",".join(missing))

    private_key = str(result.get("private_key") or "")
    if "BEGIN PRIVATE KEY" not in private_key:
        raise ValueError("private_key is not a PEM private key")

    return result


def _json_or_literal(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None

    current: Any = text
    for _ in range(4):
        if isinstance(current, dict):
            return _normalise_service_account(current)
        if not isinstance(current, str):
            break
        candidate = current.strip()
        try:
            current = json.loads(candidate)
            continue
        except Exception:
            pass
        try:
            current = ast.literal_eval(candidate)
            continue
        except Exception:
            return None
    if isinstance(current, dict):
        return _normalise_service_account(current)
    return None


def _decode_base64_text(value: str) -> list[str]:
    raw = str(value or "").strip()
    if raw.lower().startswith("base64:"):
        raw = raw.split(":", 1)[1].strip()
    if not raw:
        return []

    padded = raw + ("=" * ((4 - len(raw) % 4) % 4))
    outputs: list[str] = []
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            data = decoder(padded.encode("utf-8"))
            text = data.decode("utf-8").strip()
            if text and text not in outputs:
                outputs.append(text)
        except Exception:
            pass
    return outputs


def _candidate_strings(raw: str) -> list[str]:
    candidates: list[str] = []

    def add(value: str) -> None:
        value = str(value or "").strip()
        if value and value not in candidates:
            candidates.append(value)

    add(raw)
    add(raw.strip("'\""))

    # Accept secrets pasted as a .env assignment.
    for value in list(candidates):
        stripped = value.strip()
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" in stripped:
            left, right = stripped.split("=", 1)
            if left.strip() in {
                "GOOGLE_CREDS_JSON",
                "GOOGLE_APPLICATION_CREDENTIALS_JSON",
                "GOOGLE_SERVICE_ACCOUNT_JSON",
            }:
                add(right.strip())
                add(right.strip().strip("'\""))

    # URL-encoded secret values are sometimes produced by copy/paste tooling.
    for value in list(candidates):
        try:
            decoded = unquote(value)
            if decoded != value:
                add(decoded)
        except Exception:
            pass

    # Handle JSON whose quotes were escaped before being placed in Railway.
    for value in list(candidates):
        if '\\"' in value:
            add(value.replace('\\"', '"'))

    # Base64 / URL-safe Base64 representations.
    for value in list(candidates):
        for decoded in _decode_base64_text(value):
            add(decoded)

    return candidates


def robust_decode_google_credentials() -> dict[str, Any]:
    env_names = (
        "GOOGLE_CREDS_JSON",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    )
    raw = ""
    source_name = ""
    for name in env_names:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            raw = value
            source_name = name
            break

    # Also support the standard GOOGLE_APPLICATION_CREDENTIALS file variable.
    if not raw:
        file_var = str(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()
        if file_var:
            raw = file_var
            source_name = "GOOGLE_APPLICATION_CREDENTIALS"

    if not raw:
        raise RuntimeError("Google service-account credential variable is empty")

    # Railway file variables can resolve to a mounted path.
    path_candidate = raw.strip("'\"")
    try:
        path = Path(path_candidate)
        if path.is_file():
            parsed = _json_or_literal(path.read_text(encoding="utf-8"))
            if parsed:
                return parsed
    except Exception:
        pass

    last_problem = "unrecognised credential format"
    for candidate in _candidate_strings(raw):
        try:
            parsed = _json_or_literal(candidate)
            if parsed:
                return parsed
        except Exception as exc:
            last_problem = str(exc)

    raise RuntimeError(
        f"{source_name or 'Google credential'} could not be decoded: {last_problem}"
    )


def _safe_error(exc: Exception) -> str:
    """Return a short diagnostic that never includes credential values."""
    message = str(exc or "").replace("\n", " ").strip()
    lowered = message.lower()

    if "credential" in lowered and ("empty" in lowered or "decoded" in lowered):
        return "google_credential_invalid"
    if "private_key" in lowered or "pem" in lowered:
        return "google_private_key_invalid"
    if "spreadsheetnotfound" in lowered or "spreadsheet not found" in lowered:
        return "sheet_not_found_or_not_shared"
    if "permission" in lowered or "forbidden" in lowered or "403" in lowered:
        return "google_sheet_permission_denied"
    if "api" in lowered and "disabled" in lowered:
        return "google_sheets_api_disabled"
    if "invalid_grant" in lowered or "jwt" in lowered or "signature" in lowered:
        return "google_service_account_auth_failed"
    if "timeout" in lowered or "timed out" in lowered:
        return "google_sheet_timeout"
    return f"{type(exc).__name__}"


async def direct_sheet_only_load_members():
    """Read Members directly; never infer DeviceID through the legacy webhook."""
    try:
        members = await _reminder.asyncio.to_thread(_reminder._load_members_from_sheet_sync)
        return members, "google_sheet"
    except Exception as exc:
        _reminder._legacy.logger.exception("direct Members sheet read failed: %s", exc)
        raise RuntimeError(
            "Direct Members sheet read failed; reminders safely blocked. "
            f"Cause: {_safe_error(exc)}"
        ) from exc


_reminder._decode_google_credentials = robust_decode_google_credentials
_reminder._load_members = direct_sheet_only_load_members
