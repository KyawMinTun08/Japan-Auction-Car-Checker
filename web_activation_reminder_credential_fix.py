"""Runtime hardening for Web Premium reminder Google credential loading.

Railway's GOOGLE_CREDS_JSON has existed for the production bot for a long time,
but environment values may arrive as plain JSON, JSON wrapped in quotes, base64
(with or without padding), urlsafe-base64, or a mounted file path.  The first
reminder implementation only accepted two of those forms and then fell back to
Apps Script, whose legacy getMembers response does not include DeviceID.

This patch keeps the safe rule: never send reminders from a source that cannot
prove DeviceID state.  It only broadens credential decoding for the direct
Members sheet read and removes the unsafe Apps Script fallback path.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import web_activation_reminder_patch as _reminder


def _normalise_service_account(info: dict[str, Any]) -> dict[str, Any]:
    result = dict(info)
    if result.get("private_key"):
        result["private_key"] = str(result["private_key"]).replace("\\n", "\n")
    if not result.get("client_email") or not result.get("private_key"):
        raise ValueError("service-account fields missing")
    return result


def _try_json(value: str) -> dict[str, Any] | None:
    current: Any = value.strip()
    for _ in range(3):
        if not isinstance(current, str):
            break
        try:
            current = json.loads(current)
        except Exception:
            return None
        if isinstance(current, dict):
            return _normalise_service_account(current)
    return None


def _decode_base64_text(value: str) -> list[str]:
    raw = value.strip()
    if raw.lower().startswith("base64:"):
        raw = raw.split(":", 1)[1].strip()
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


def robust_decode_google_credentials() -> dict[str, Any]:
    raw = str(os.environ.get("GOOGLE_CREDS_JSON", "") or "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_CREDS_JSON is empty")

    # Railway can expose secret/file variables as a mounted file path.
    path_candidate = raw.strip("'\"")
    try:
        path = Path(path_candidate)
        if path.is_file():
            parsed = _try_json(path.read_text(encoding="utf-8"))
            if parsed:
                return parsed
    except Exception:
        pass

    candidates: list[str] = [raw]
    unquoted = raw.strip("'\"")
    if unquoted and unquoted != raw:
        candidates.append(unquoted)

    for candidate in list(candidates):
        for decoded in _decode_base64_text(candidate):
            if decoded not in candidates:
                candidates.append(decoded)

    last_problem = "unrecognised credential format"
    for candidate in candidates:
        try:
            parsed = _try_json(candidate)
            if parsed:
                return parsed
        except Exception as exc:
            last_problem = str(exc)

    raise RuntimeError(f"GOOGLE_CREDS_JSON could not be decoded: {last_problem}")


async def direct_sheet_only_load_members():
    """Never fall back to Apps Script because legacy getMembers omits DeviceID."""
    try:
        members = await _reminder.asyncio.to_thread(_reminder._load_members_from_sheet_sync)
        return members, "google_sheet"
    except Exception as exc:
        # Keep detailed cause in Railway logs; member DMs remain blocked.
        _reminder._legacy.logger.exception("direct Members sheet read failed: %s", exc)
        raise RuntimeError(
            "Direct Members sheet read failed; reminders safely blocked. "
            f"Cause: {type(exc).__name__}"
        ) from exc


_reminder._decode_google_credentials = robust_decode_google_credentials
_reminder._load_members = direct_sheet_only_load_members
