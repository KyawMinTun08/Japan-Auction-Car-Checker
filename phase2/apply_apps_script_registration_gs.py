"""Guarded transformer for the reviewed current JACC Registration.gs source.

The transformer is intentionally narrow and refuses source drift. It fixes only
reviewed Phase 2 integration risks:

* nested ScriptLock acquisition under the current outer doPost lock;
* completed registrations blocking a new renewal registration;
* missing WEB_PROMO package alias support; and
* public registration-status responses leaking Telegram account details.
"""

from __future__ import annotations

import argparse
from pathlib import Path


class RegistrationScriptPatchError(RuntimeError):
    """Raised when Registration.gs no longer matches the reviewed contract."""


_MARKER = "// Phase 2: reuse the outer doPost ScriptLock when already held."

_WEB_ALIAS_OLD = """  if (
    pkg === 'WEB' ||
    pkg === 'PREMIUM' ||
    pkg === 'WEB_PREMIUM'
  ) {"""

_WEB_ALIAS_NEW = """  if (
    pkg === 'WEB' ||
    pkg === 'PREMIUM' ||
    pkg === 'WEB_PREMIUM' ||
    pkg === 'WEB_PROMO'
  ) {"""

_ACCEPTED_OLD = """        'CH',
        'CHANNEL',
        'STANDARD',
        'WEB',
        'PREMIUM',
        'WEB_PREMIUM'"""

_ACCEPTED_NEW = """        'CH',
        'CHANNEL',
        'STANDARD',
        'CH_PROMO',
        'WEB',
        'PREMIUM',
        'WEB_PREMIUM',
        'WEB_PROMO'"""

_LOCK_OLD = """  const lock = LockService.getScriptLock();

  try {
    lock.waitLock(10000);"""

_LOCK_NEW = """  const lock = LockService.getScriptLock();
  let releaseHere = false;

  try {
    // Phase 2: reuse the outer doPost ScriptLock when already held.
    if (!lock.hasLock()) {
      lock.waitLock(10000);
      releaseHere = true;
    }"""

_UNLOCK_OLD = """  } finally {
    try {
      lock.releaseLock();
    } catch (ignore) {}
  }"""

_UNLOCK_NEW = """  } finally {
    if (releaseHere) {
      try {
        lock.releaseLock();
      } catch (ignore) {}
    }
  }"""

_ALREADY_LINKED_OLD = """      return {
        ok: false,
        error: 'REGISTRATION_ALREADY_LINKED',
        telegramId: currentTelegramId
      };"""

_ALREADY_LINKED_NEW = """      return {
        ok: false,
        error: 'REGISTRATION_ALREADY_LINKED',
        linked: true
      };"""

_DUPLICATE_STATUS_OLD = "!['REJECTED', 'EXPIRED'].includes(existingStatus)"
_DUPLICATE_STATUS_NEW = "!['APPROVED', 'REJECTED', 'EXPIRED'].includes(existingStatus)"

_TELEGRAM_LINKED_OLD = """          return {
            ok: false,
            error: 'TELEGRAM_ALREADY_LINKED',
            registrationCode: existingCode
          };"""

_TELEGRAM_LINKED_NEW = """          return {
            ok: false,
            error: 'TELEGRAM_ALREADY_LINKED'
          };"""

_CHECK_RETURN_OLD = """    return {
      ok: true,
      registrationCode: r[0],
      telegramId: r[1],
      username: r[2],
      package: jaccPublicRegistrationPackage_(storedPackage) || r[3],
      storedPackage: storedPackage || r[3],
      status: r[4],
      createdAt: r[5],
      telegramConnected: Boolean(String(r[1] || '').trim())
    };"""

_CHECK_RETURN_NEW = """    return {
      ok: true,
      registrationCode: r[0],
      package: jaccPublicRegistrationPackage_(storedPackage) || r[3],
      status: r[4],
      createdAt: r[5],
      telegramConnected: Boolean(String(r[1] || '').trim())
    };"""


def _replace_count(source: str, old: str, new: str, count: int, label: str) -> str:
    actual = source.count(old)
    if actual != count:
        raise RegistrationScriptPatchError(
            f"{label} contract drift: expected {count} reviewed anchor(s), found {actual}"
        )
    return source.replace(old, new)


def _validate_patched(source: str) -> None:
    required = (
        _MARKER,
        "pkg === 'WEB_PROMO'",
        "'CH_PROMO'",
        "'WEB_PROMO'",
        "!['APPROVED', 'REJECTED', 'EXPIRED'].includes(existingStatus)",
        "linked: true",
        "if (releaseHere)",
    )
    for marker in required:
        if marker not in source:
            raise RegistrationScriptPatchError(
                f"patched Registration.gs is missing marker: {marker}"
            )

    if source.count(_MARKER) != 2:
        raise RegistrationScriptPatchError(
            "patched Registration.gs must reuse the outer lock in exactly "
            "createRegistration and connectTelegram"
        )
    if source.count("if (releaseHere)") != 2:
        raise RegistrationScriptPatchError(
            "patched Registration.gs must release only locally acquired locks"
        )

    forbidden = (
        "telegramId: currentTelegramId",
        "registrationCode: existingCode",
        "telegramId: r[1]",
        "username: r[2]",
        "storedPackage: storedPackage || r[3]",
        _DUPLICATE_STATUS_OLD,
    )
    for marker in forbidden:
        if marker in source:
            raise RegistrationScriptPatchError(
                f"legacy Registration.gs contract is still active: {marker}"
            )


def apply_patch_text(source: str) -> str:
    """Return a guarded Phase 2 Registration.gs candidate."""

    if _MARKER in source:
        _validate_patched(source)
        return source

    patched = _replace_count(source, _WEB_ALIAS_OLD, _WEB_ALIAS_NEW, 1, "WEB alias")
    patched = _replace_count(
        patched, _ACCEPTED_OLD, _ACCEPTED_NEW, 1, "accepted package list"
    )
    patched = _replace_count(
        patched, _LOCK_OLD, _LOCK_NEW, 2, "nested ScriptLock acquisition"
    )
    patched = _replace_count(
        patched, _UNLOCK_OLD, _UNLOCK_NEW, 2, "ScriptLock release"
    )
    patched = _replace_count(
        patched,
        _ALREADY_LINKED_OLD,
        _ALREADY_LINKED_NEW,
        1,
        "registration linked response",
    )
    patched = _replace_count(
        patched,
        _DUPLICATE_STATUS_OLD,
        _DUPLICATE_STATUS_NEW,
        1,
        "completed registration renewal policy",
    )
    patched = _replace_count(
        patched,
        _TELEGRAM_LINKED_OLD,
        _TELEGRAM_LINKED_NEW,
        1,
        "Telegram linked response",
    )
    patched = _replace_count(
        patched,
        _CHECK_RETURN_OLD,
        _CHECK_RETURN_NEW,
        1,
        "public checkRegistration response",
    )

    _validate_patched(patched)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Current Registration.gs source")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the patched candidate here instead of replacing the input",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail unless the source is already patched and valid",
    )
    args = parser.parse_args()

    source = args.path.read_text(encoding="utf-8")
    patched = apply_patch_text(source)

    if args.check:
        if patched != source:
            raise RegistrationScriptPatchError(
                "Registration.gs still needs the Phase 2 patch"
            )
        print("Apps Script Phase 2 Registration.gs contract: valid")
        return 0

    target = args.output or args.path
    target.write_text(patched, encoding="utf-8")
    print(f"Apps Script Phase 2 Registration.gs candidate written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
