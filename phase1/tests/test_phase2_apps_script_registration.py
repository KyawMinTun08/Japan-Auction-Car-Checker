from __future__ import annotations

import pytest

from phase2.apply_apps_script_registration_gs import (
    RegistrationScriptPatchError,
    apply_patch_text,
)


CURRENT_REGISTRATION_CONTRACT = """function jaccNormalizeRegistrationPackage_(value) {
  const pkg = String(value || 'STANDARD')
    .trim()
    .toUpperCase()
    .replace(/[\\s-]+/g, '_');

  if (
    pkg === 'STANDARD' ||
    pkg === 'CH' ||
    pkg === 'CHANNEL' ||
    pkg === 'CH_PROMO'
  ) {
    return 'STANDARD';
  }

  if (
    pkg === 'WEB' ||
    pkg === 'PREMIUM' ||
    pkg === 'WEB_PREMIUM'
  ) {
    return 'WEB_PREMIUM';
  }
  return '';
}

function createRegistration(data) {
  const storedPackage = jaccNormalizeRegistrationPackage_(data.package);
  if (!storedPackage) {
    return {
      ok: false,
      error: 'INVALID_PACKAGE',
      acceptedPackages: [
        'CH',
        'CHANNEL',
        'STANDARD',
        'WEB',
        'PREMIUM',
        'WEB_PREMIUM'
      ]
    };
  }

  const lock = LockService.getScriptLock();

  try {
    lock.waitLock(10000);
    return {ok:true};
  } finally {
    try {
      lock.releaseLock();
    } catch (ignore) {}
  }
}

function connectTelegram(data) {
  const currentTelegramId = '123';
  const telegramId = '456';
  if (currentTelegramId && currentTelegramId !== telegramId) {
      return {
        ok: false,
        error: 'REGISTRATION_ALREADY_LINKED',
        telegramId: currentTelegramId
      };
  }

  const lock = LockService.getScriptLock();

  try {
    lock.waitLock(10000);
    const rows = [];
    for (let i = 0; i < rows.length; i++) {
      const existingCode = String(rows[i][0] || '').trim().toUpperCase();
      const existingTelegramId = String(rows[i][1] || '').trim();
      const existingStatus = String(rows[i][4] || '').trim().toUpperCase();
      const code = 'REG-TEST';
      if (
          existingCode !== code &&
          existingTelegramId === telegramId &&
          !['REJECTED', 'EXPIRED'].includes(existingStatus)
        ) {
          return {
            ok: false,
            error: 'TELEGRAM_ALREADY_LINKED',
            registrationCode: existingCode
          };
        }
    }
    return {ok:true};
  } finally {
    try {
      lock.releaseLock();
    } catch (ignore) {}
  }
}

function checkRegistration(data) {
  const r = [];
  const storedPackage = 'WEB_PREMIUM';
  return {
      ok: true,
      registrationCode: r[0],
      telegramId: r[1],
      username: r[2],
      package: jaccPublicRegistrationPackage_(storedPackage) || r[3],
      storedPackage: storedPackage || r[3],
      status: r[4],
      createdAt: r[5],
      telegramConnected: Boolean(String(r[1] || '').trim())
    };
}
"""


def test_transformer_reuses_outer_lock_without_releasing_it() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    assert patched.count("if (!lock.hasLock())") == 2
    assert patched.count("releaseHere = true") == 2
    assert patched.count("if (releaseHere)") == 2
    assert patched.count("lock.waitLock(10000)") == 2


def test_completed_registration_does_not_block_new_renewal() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    assert "!['APPROVED', 'REJECTED', 'EXPIRED'].includes(existingStatus)" in patched
    assert "!['REJECTED', 'EXPIRED'].includes(existingStatus)" not in patched


def test_public_registration_status_redacts_account_details() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    check = patched.split("function checkRegistration", 1)[1]
    assert "telegramId: r[1]" not in check
    assert "username: r[2]" not in check
    assert "storedPackage: storedPackage || r[3]" not in check
    assert "telegramConnected" in check
    assert "package:" in check
    assert "status:" in check


def test_link_conflicts_do_not_disclose_other_identifiers() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    assert "telegramId: currentTelegramId" not in patched
    assert "registrationCode: existingCode" not in patched
    assert "linked: true" in patched


def test_web_promo_alias_is_supported() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    assert "pkg === 'WEB_PROMO'" in patched
    assert "'CH_PROMO'" in patched
    assert "'WEB_PROMO'" in patched


def test_transformer_is_idempotent() -> None:
    patched = apply_patch_text(CURRENT_REGISTRATION_CONTRACT)
    assert apply_patch_text(patched) == patched


def test_transformer_refuses_unknown_registration_drift() -> None:
    with pytest.raises(RegistrationScriptPatchError, match="WEB alias contract drift"):
        apply_patch_text(
            CURRENT_REGISTRATION_CONTRACT.replace("pkg === 'WEB_PREMIUM'", "pkg === 'WEB_PLUS'")
        )
