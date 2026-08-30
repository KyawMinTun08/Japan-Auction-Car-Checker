/*
 * JACC Phase 2 website device-binding helper.
 *
 * STAGED ONLY. index.html must be transformed with
 * phase2/apply_website_device_binding.py before production activation.
 *
 * Policy:
 * - every WEB/PWA/Flutter installation owns one stable random installation ID;
 * - the ID is sent only to the JACC Apps Script auth/data routes;
 * - logout keeps the installation ID so the same device can sign in again;
 * - clearing site data or moving to another device requires an authenticated
 *   admin reset of Members!J (DeviceID);
 * - IP addresses are logging/diagnostic data only and are never device keys.
 */
(function (global) {
  'use strict';

  const INSTALLATION_KEY = 'jacc_installation_id';
  const SESSION_KEY = 'jan_session';
  const SESSION_VERSION = 'v4';
  const ID_PATTERN = /^JACC-[a-f0-9]{48}$/;
  const DEVICE_ACTIONS = new Set(['verifyLogin', 'verifyToken', 'getData', 'verifyGoogleLogin']);

  function storageOrThrow(storage) {
    const target = storage || global.localStorage;
    if (!target || typeof target.getItem !== 'function') {
      throw new Error('device_storage_unavailable');
    }
    return target;
  }

  function randomInstallationId(cryptoObject) {
    const source = cryptoObject || global.crypto;
    if (!source || typeof source.getRandomValues !== 'function') {
      throw new Error('secure_random_unavailable');
    }
    const bytes = new Uint8Array(24);
    source.getRandomValues(bytes);
    return 'JACC-' + Array.from(bytes, function (value) {
      return value.toString(16).padStart(2, '0');
    }).join('');
  }

  function getInstallationId(storage, cryptoObject) {
    const target = storageOrThrow(storage);
    const existing = String(target.getItem(INSTALLATION_KEY) || '').trim();
    if (ID_PATTERN.test(existing)) return existing;

    const created = randomInstallationId(cryptoObject);
    target.setItem(INSTALLATION_KEY, created);
    return created;
  }

  function detectClientApp(locationObject, navigatorObject) {
    const locationValue = locationObject || global.location || {};
    const navigatorValue = navigatorObject || global.navigator || {};
    let requested = '';
    try {
      requested = new URLSearchParams(locationValue.search || '').get('app') || '';
    } catch (error) {
      requested = '';
    }

    const app = String(requested).trim().toLowerCase();
    const userAgent = String(navigatorValue.userAgent || '').toLowerCase();
    if (app === 'flutter' || global.JACC_FLUTTER_APP === true || userAgent.indexOf('jaccflutter') >= 0) return 'flutter';
    if (app === 'pwa' || (global.matchMedia && global.matchMedia('(display-mode: standalone)').matches) || navigatorValue.standalone === true) return 'pwa';
    return 'web';
  }

  function deviceFields(options) {
    const config = options || {};
    return {
      app: detectClientApp(config.location, config.navigator),
      deviceId: getInstallationId(config.storage, config.crypto),
    };
  }

  function withDevice(action, fields, options) {
    const payload = Object.assign({}, fields || {}, { action: action });
    if (DEVICE_ACTIONS.has(String(action || ''))) Object.assign(payload, deviceFields(options));
    return payload;
  }

  function reasonOf(response) {
    return String((response && (response.message || response.msg || response.error)) || '').trim().toLowerCase();
  }

  function isDeviceError(response) {
    const reason = reasonOf(response);
    return reason === 'device_mismatch' || reason === 'device_required' || reason === 'device_invalid' || reason === 'device_lock_busy';
  }

  function deviceErrorMessage(response) {
    const reason = reasonOf(response);
    if (reason === 'device_mismatch') return '🔒 ဒီ Membership ကို အခြား device တစ်ခုနဲ့ ချိတ်ထားပါတယ်။ Telegram Bot မှ Admin ကို Device Reset တောင်းပါ။';
    if (reason === 'device_required' || reason === 'device_invalid') return '⚠️ ဒီ browser/app မှာ secure Device ID မဖန်တီးနိုင်ပါ။ Private mode ပိတ်ပြီး ပြန်ဖွင့်ပါ။';
    if (reason === 'device_lock_busy') return '⏳ Device စစ်ဆေးမှု အလုပ်များနေပါတယ်။ ခဏနေရင် ပြန်ကြိုးစားပါ။';
    return '⚠️ Device verification မအောင်မြင်ပါ။';
  }

  function readSession(storage) {
    const target = storageOrThrow(storage);
    try {
      const parsed = JSON.parse(target.getItem(SESSION_KEY) || 'null');
      if (!parsed || !parsed.token || parsed.ver !== SESSION_VERSION) {
        target.removeItem(SESSION_KEY);
        return null;
      }
      return parsed;
    } catch (error) {
      target.removeItem(SESSION_KEY);
      return null;
    }
  }

  function saveSession(session, storage) {
    const target = storageOrThrow(storage);
    const value = Object.assign({}, session || {}, {
      ver: SESSION_VERSION,
      installationId: getInstallationId(target),
      clientApp: detectClientApp(),
    });
    target.setItem(SESSION_KEY, JSON.stringify(value));
    return value;
  }

  function clearSession(storage) {
    storageOrThrow(storage).removeItem(SESSION_KEY);
  }

  async function postJson(webhook, payload, fetchImpl, timeoutMs) {
    const sender = fetchImpl || global.fetch;
    if (typeof sender !== 'function') throw new Error('fetch_unavailable');
    const milliseconds = Math.max(1000, Number(timeoutMs) || 12000);
    const controller = typeof global.AbortController === 'function' ? new global.AbortController() : null;
    let timer;
    const requestOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload),
    };
    if (controller) requestOptions.signal = controller.signal;
    const request = sender(webhook, requestOptions);
    const timeout = new Promise(function (_, reject) {
      timer = setTimeout(function () {
        if (controller) controller.abort();
        const error = new Error('request_timeout');
        error.code = 'REQUEST_TIMEOUT';
        reject(error);
      }, milliseconds);
    });
    try {
      const response = await Promise.race([request, timeout]);
      if (!response.ok) throw new Error('http_' + response.status);
      return response.json();
    } finally {
      clearTimeout(timer);
    }
  }

  async function verifyStoredSession(options) {
    const config = options || {};
    const storage = storageOrThrow(config.storage);
    const session = readSession(storage);
    if (!session) return { ok: false, reason: 'session_missing' };

    let result;
    try {
      result = await postJson(
        config.webhook,
        withDevice('verifyToken', { token: session.token, userId: session.userId }, config),
        config.fetchImpl,
        config.timeoutMs
      );
    } catch (error) {
      return { ok: false, reason: 'backend_unavailable', error: error };
    }

    if (!result || String(result.status || '').toLowerCase() !== 'ok') {
      clearSession(storage);
      return { ok: false, reason: reasonOf(result) || 'token_rejected', deviceError: isDeviceError(result), response: result };
    }

    const refreshed = saveSession(Object.assign({}, session, {
      token: result.token || session.token,
      userId: result.userId || session.userId,
      username: result.username || session.username,
      package: result.package || session.package,
      expireDate: result.expireDate || result.expiredDate || session.expireDate,
      // JACC Google Login: memberStatus distinguishes a PENDING signup
      // (awaiting its first payment) from an approved ACTIVE member. Without
      // refreshing it here, a member approved via /googleapprove would stay
      // stuck on the pending-payment screen forever after their next reload,
      // since the stale PENDING value from the original sign-in would never
      // be overwritten even though verifyToken now reports ACTIVE.
      memberStatus: result.memberStatus || session.memberStatus,
      verifiedAt: Date.now(),
    }), storage);

    return { ok: true, session: refreshed, response: result };
  }

  global.JACCDeviceBinding = Object.freeze({
    INSTALLATION_KEY: INSTALLATION_KEY,
    SESSION_KEY: SESSION_KEY,
    SESSION_VERSION: SESSION_VERSION,
    randomInstallationId: randomInstallationId,
    getInstallationId: getInstallationId,
    detectClientApp: detectClientApp,
    deviceFields: deviceFields,
    withDevice: withDevice,
    reasonOf: reasonOf,
    isDeviceError: isDeviceError,
    deviceErrorMessage: deviceErrorMessage,
    readSession: readSession,
    saveSession: saveSession,
    clearSession: clearSession,
    postJson: postJson,
    verifyStoredSession: verifyStoredSession,
  });
})(window);