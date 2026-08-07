(() => {
  'use strict';

  const SAFE_SCHEMES = new Set(['blob:', 'https:']);
  const STATES = Object.freeze(['idle','loading','ready','expired','denied','missing','offline','error']);

  function normalizeAlt(value) {
    const alt = String(value || '').trim();
    return alt.slice(0, 180) || 'Private chat photo';
  }

  function assertPrivateUrl(url) {
    const raw = String(url || '');
    let parsed;
    try { parsed = new URL(raw, 'https://preview.invalid/'); } catch (_) { throw new Error('private_url_invalid'); }
    if (!SAFE_SCHEMES.has(parsed.protocol)) throw new Error('private_url_scheme_not_allowed');
    if (parsed.protocol === 'https:' && !/(token|signature|signed|expires|exp)=/i.test(parsed.search)) {
      throw new Error('private_url_not_short_lived');
    }
    return raw;
  }

  function classifyReadError(error) {
    const code = String(error && (error.code || error.status || error.message) || '').toLowerCase();
    if (code.includes('401') || code.includes('403') || code.includes('denied') || code.includes('forbidden')) return 'denied';
    if (code.includes('404') || code.includes('missing') || code.includes('not_found')) return 'missing';
    if (code.includes('expired') || code.includes('signature') || code.includes('token')) return 'expired';
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return 'offline';
    return 'error';
  }

  function createAttachmentPreview(adapter) {
    if (!adapter || typeof adapter.createPrivateReadUrl !== 'function') throw new Error('preview_adapter_incomplete');

    async function resolve({ bucket, path, alt, expiresIn = 60 }) {
      const result = { state: 'loading', url: null, alt: normalizeAlt(alt), retryable: true };
      try {
        const url = await adapter.createPrivateReadUrl({ bucket, path, expiresIn: Math.max(15, Math.min(120, Number(expiresIn) || 60)) });
        result.url = assertPrivateUrl(url);
        result.state = 'ready';
        result.retryable = false;
        return result;
      } catch (error) {
        result.state = classifyReadError(error);
        result.retryable = !['denied','missing'].includes(result.state);
        result.error = String(error && error.message || error || 'preview_failed');
        return result;
      }
    }

    async function refresh(input) { return resolve(input); }

    function bindImage(img, input) {
      if (!img || typeof img.setAttribute !== 'function') throw new Error('image_element_required');
      img.setAttribute('alt', normalizeAlt(input && input.alt));
      img.setAttribute('tabindex', '0');
      img.setAttribute('decoding', 'async');
      img.setAttribute('loading', 'lazy');
      return resolve(input).then(result => {
        img.dataset.previewState = result.state;
        if (result.state === 'ready') img.src = result.url;
        else img.removeAttribute('src');
        img.onerror = () => {
          img.removeAttribute('src');
          img.dataset.previewState = (typeof navigator !== 'undefined' && navigator.onLine === false) ? 'offline' : 'error';
        };
        return result;
      });
    }

    return Object.freeze({ resolve, refresh, bindImage });
  }

  const api = Object.freeze({ STATES, normalizeAlt, assertPrivateUrl, classifyReadError, createAttachmentPreview });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  globalThis.JACCChatAttachmentPreview = api;
})();
