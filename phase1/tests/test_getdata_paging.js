const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('Code.gs', 'utf8') + '\n' +
  fs.readFileSync('apps-script/device-bindings.gs', 'utf8');

class FakeRange {
  constructor(sheet, row, col, numRows = 1, numCols = 1) {
    this.sheet = sheet;
    this.row = row;
    this.col = col;
    this.numRows = numRows;
    this.numCols = numCols;
  }

  getValues() {
    return this.sheet.rows
      .slice(this.row - 1, this.row - 1 + this.numRows)
      .map((row) => row.slice(this.col - 1, this.col - 1 + this.numCols));
  }

  setValue(value) {
    this.sheet.ensure(this.row, this.col);
    this.sheet.rows[this.row - 1][this.col - 1] = value;
    return this;
  }

  setValues(values) {
    values.forEach((line, rowOffset) => line.forEach((value, colOffset) => {
      this.sheet.ensure(this.row + rowOffset, this.col + colOffset);
      this.sheet.rows[this.row + rowOffset - 1][this.col + colOffset - 1] = value;
    }));
    return this;
  }

  setFontWeight() { return this; }
  setBackground() { return this; }
  setFontColor() { return this; }
}

class FakeSheet {
  constructor(name, rows) {
    this.name = name;
    this.rows = rows.map((row) => row.slice());
    this.rangeCalls = [];
    this.dataRangeCalls = 0;
  }

  ensure(row, col) {
    while (this.rows.length < row) this.rows.push([]);
    while (this.rows[row - 1].length < col) this.rows[row - 1].push('');
  }

  getLastRow() { return this.rows.length; }
  getLastColumn() { return Math.max(1, ...this.rows.map((row) => row.length)); }

  getDataRange() {
    this.dataRangeCalls += 1;
    return new FakeRange(this, 1, 1, this.rows.length, this.getLastColumn());
  }

  getRange(row, col, numRows = 1, numCols = 1) {
    this.rangeCalls.push({ row, col, numRows, numCols });
    return new FakeRange(this, row, col, numRows, numCols);
  }

  appendRow(row) { this.rows.push(row.slice()); }
  setFrozenRows() {}
}

const memberHeader = ['UserID', 'Username', 'Start', 'Expire', 'Status', 'CancelCount', 'Password', 'Package', 'Token'];
const bindingHeader = ['UserID', 'DeviceHash', 'ClientApp', 'BoundAt', 'LastSeenAt', 'Status', 'ResetCount', 'ResetAt'];
const sessionHeader = ['SessionHash', 'UserID', 'DeviceHash', 'ClientApp', 'IssuedAt', 'ExpiresAt', 'Status', 'RevokedAt', 'LastSeenAt'];
const sheet1Header = ['Date', 'Chassis', 'Model', 'Color', 'Year', 'Price', 'Location', 'AddedBy', 'Image'];
const fixedNow = new Date('2026-08-20T12:00:00Z');

class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [fixedNow])); }
}

function makeContext() {
  const props = { JACC_DEVICE_BINDING_MODE: 'log', JACC_DEVICE_HASH_SECRET: 'probe-secret' };
  const sheets = {
    Members: new FakeSheet('Members', [
      memberHeader,
      ['1001', 'premium', '01/08/2026', '31/12/2026', 'ACTIVE', 0, 'pw', 'WEB', 'token-1001'],
    ]),
    DeviceBindings: new FakeSheet('DeviceBindings', [bindingHeader]),
    AuthSessions: new FakeSheet('AuthSessions', [sessionHeader]),
    Sheet1: new FakeSheet('Sheet1', [
      sheet1Header,
      ['20/08/2026', 'ABC123', 'CROWN', 'WHITE', '2013', '30000', 'MaeSot', 'admin', ''],
      ['20/08/2026', 'DEF456', 'ALPHARD', 'BLACK', '2014', '45000', 'Klang9', 'admin', ''],
      ['20/08/2026', 'GHI789', 'FIT', 'SILVER', '2015', '22000', 'MaeSot', 'admin', ''],
    ]),
  };
  const digest = (algorithm, value) => crypto.createHash('sha256').update(String(value), 'utf8').digest();
  const context = {
    console,
    Date: FixedDate,
    SpreadsheetApp: {
      openById: () => ({
        getSheetByName: (name) => sheets[name] || null,
        insertSheet: (name) => (sheets[name] = new FakeSheet(name, [])),
      }),
    },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (key) => props[key] || '',
        setProperty: (key, value) => { props[key] = String(value); },
        deleteProperty: (key) => { delete props[key]; },
      }),
    },
    Utilities: {
      DigestAlgorithm: { SHA_256: 'SHA-256' },
      Charset: { UTF_8: 'utf8' },
      computeDigest: digest,
      formatDate: (date, _timezone, format) => {
        const d = new Date(date);
        const pad = (value) => String(value).padStart(2, '0');
        if (format === 'dd/MM/yyyy') return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
        return d.toISOString();
      },
    },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    ContentService: {
      MimeType: { JSON: 'application/json' },
      createTextOutput: (text) => ({
        text,
        setMimeType(type) { this.mimeType = type; return this; },
      }),
    },
  };
  vm.runInNewContext(source, context);

  const deviceId = 'JACC-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const deviceHash = context._hashDeviceId_(deviceId);
  const sessionHash = context._hashSessionToken_('token-1001');
  sheets.DeviceBindings.appendRow(['1001', deviceHash, 'web', fixedNow, fixedNow, 'ACTIVE', 0, '']);
  sheets.AuthSessions.appendRow([sessionHash, '1001', deviceHash, 'web', fixedNow, new Date('2026-12-31T23:59:59Z'), 'ACTIVE', '', fixedNow]);
  return { context, sheets, deviceId };
}

function getData(env, offset, limit) {
  const response = env.context.doPost({
    postData: {
      contents: JSON.stringify({
        action: 'getData',
        token: 'token-1001',
        userId: '1001',
        deviceId: env.deviceId,
        app: 'web',
        offset,
        limit,
      }),
    },
  });
  return JSON.parse(response.text);
}

const env = makeContext();
const first = getData(env, 0, 1);
assert.equal(first.status, 'ok');
assert.equal(first.cars.length, 1);
assert.equal(first.cars[0].chassis, 'ABC123');
assert.deepEqual(first.page, { offset: 0, limit: 1, total: 3, hasMore: true });

const second = getData(env, 1, 1);
assert.equal(second.status, 'ok');
assert.equal(second.cars.length, 1);
assert.equal(second.cars[0].chassis, 'DEF456');
assert.deepEqual(second.page, { offset: 1, limit: 1, total: 3, hasMore: true });

const empty = getData(env, 3, 1);
assert.equal(empty.status, 'ok');
assert.deepEqual(empty.cars, []);
assert.deepEqual(empty.page, { offset: 3, limit: 1, total: 3, hasMore: false });

const sheet1 = env.sheets.Sheet1;
assert.equal(sheet1.dataRangeCalls, 0, 'getData must not load the full Sheet1 range');
assert.deepEqual(sheet1.rangeCalls.slice(0, 4), [
  { row: 1, col: 1, numRows: 1, numCols: 9 },
  { row: 2, col: 1, numRows: 1, numCols: 9 },
  { row: 1, col: 1, numRows: 1, numCols: 9 },
  { row: 3, col: 1, numRows: 1, numCols: 9 },
]);

console.log('getData paging: ok');
