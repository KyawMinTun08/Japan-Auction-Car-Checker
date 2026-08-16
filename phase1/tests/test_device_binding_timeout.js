const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('phase2/website_device_binding.js', 'utf8');
const values = new Map([
  ['jan_session', JSON.stringify({ token: 'token-1', userId: '123', ver: 'v4' })],
]);
const storage = {
  getItem: (key) => values.get(key) || null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const cryptoObject = { getRandomValues: (bytes) => bytes.fill(7) };
const windowObject = {
  crypto: cryptoObject,
  AbortController,
  URLSearchParams,
  matchMedia: () => ({ matches: false }),
  navigator: { userAgent: 'JACC-Test' },
  location: { search: '' },
};
const context = {
  window: windowObject,
  setTimeout,
  clearTimeout,
  AbortController,
  URLSearchParams,
};
vm.runInNewContext(source, context, { filename: 'website_device_binding.js' });

(async () => {
  const result = await windowObject.JACCDeviceBinding.verifyStoredSession({
    storage,
    crypto: cryptoObject,
    webhook: 'https://example.invalid',
    timeoutMs: 25,
    fetchImpl: () => new Promise(() => {}),
  });
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, 'backend_unavailable');
  assert.strictEqual(result.error.code, 'REQUEST_TIMEOUT');
  console.log('device binding timeout fallback passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
