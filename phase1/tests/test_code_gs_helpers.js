const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const code = fs.readFileSync('Code.gs', 'utf8');
const context = {
  PropertiesService: {
    getScriptProperties: () => ({
      getProperty: (name) => name === 'JACC_SERVER_KEY' ? 'test-key' : ''
    })
  },
  ContentService: {
    MimeType: { JSON: 'application/json' },
    createTextOutput: (value) => ({ value, setMimeType() { return this; } })
  },
  SpreadsheetApp: {},
  Utilities: { formatDate: () => '16/08/2026 00:00:00' },
  DriveApp: {},
  MimeType: { CSV: 'text/csv' },
  Logger: { log() {} },
};
vm.createContext(context);
vm.runInContext(code, context);

assert.strictEqual(context._normalizePackage('Web Premium'), 'WEB');
assert.strictEqual(context._serverKeyMatches({ serverKey: 'test-key' }), true);
assert.strictEqual(context._serverKeyMatches({ serverKey: 'wrong' }), false);
assert.strictEqual(context._paymentKey({ transactionNo: 'TX-1' }), 'REF:TX-1');
assert.strictEqual(context.monthlyPasswordReset().result, 'disabled');
console.log('Code.gs helper harness passed');
