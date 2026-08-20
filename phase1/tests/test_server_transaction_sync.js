const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const code = fs.readFileSync("Code.gs", "utf8");
const deviceBindingsCode = fs.readFileSync("apps-script/device-bindings.gs", "utf8");
const appScriptSource = `${code}\n${deviceBindingsCode}`;
const memberHeader = ["UserID", "Username", "Start", "Expire", "Status", "CancelCount", "Password", "Package", "Token"];
const financeHeader = [
  "Date", "Time", "UserID", "Username", "Package", "Months",
  "Amount(Ks)", "PayType", "TransactionNo", "TransferTo", "Sender", "Status",
  "EntryType", "Source", "PaymentID", "ApprovedBy", "ExpireDate", "Note",
];
const authSessionHeader = [
  "SessionHash", "UserID", "DeviceHash", "ClientApp", "IssuedAt",
  "ExpiresAt", "Status", "RevokedAt", "LastSeenAt",
];

function cloneRows(rows) {
  return rows.map((row) => row.slice());
}

function FakeSheet(rows, name) {
  this.name = name;
  this.rows = rows;
}
FakeSheet.prototype.getLastRow = function () { return this.rows.length; };
FakeSheet.prototype.getLastColumn = function () {
  return Math.max(1, ...this.rows.map((row) => row.length));
};
FakeSheet.prototype.getDataRange = function () {
  const self = this;
  return { getValues: () => cloneRows(self.rows) };
};
FakeSheet.prototype.getRange = function (row, col, numRows = 1, numCols = 1) {
  const self = this;
  return {
    getValues() {
      return self.rows.slice(row - 1, row - 1 + numRows).map((r) =>
        r.slice(col - 1, col - 1 + numCols),
      );
    },
    setValue(value) {
      while (self.rows.length < row) self.rows.push([]);
      while (self.rows[row - 1].length < col) self.rows[row - 1].push("");
      self.rows[row - 1][col - 1] = value;
      return this;
    },
    setValues(values) {
      values.forEach((valuesRow, rowOffset) => {
        const targetRow = row + rowOffset;
        while (self.rows.length < targetRow) self.rows.push([]);
        while (self.rows[targetRow - 1].length < col + valuesRow.length - 1) self.rows[targetRow - 1].push("");
        valuesRow.forEach((value, colOffset) => {
          self.rows[targetRow - 1][col + colOffset - 1] = value;
        });
      });
      return this;
    },
    setFontWeight() { return this; },
    setBackground() { return this; },
    setFontColor() { return this; },
  };
};
FakeSheet.prototype.appendRow = function (row) {
  this.rows.push(row.slice());
};
FakeSheet.prototype.setFrozenRows = function () {};

function makeUtilities() {
  return {
    formatDate(date, _timezone, format) {
      const d = new Date(date);
      const pad = (n) => String(n).padStart(2, "0");
      if (format === "dd/MM/yyyy") return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
      if (format === "HH:mm") return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
      if (format === "dd/MM/yyyy HH:mm:ss") return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
      return d.toISOString();
    },
  };
}

function makeContext(memberRows, financeRows, properties) {
  const members = new FakeSheet(memberRows, "Members");
  const finance = new FakeSheet(financeRows, "Finance");
  const sheets = { Members: members, Finance: finance };
  // Use midday UTC so the Node test process cannot shift the Apps Script date across midnight.
  const fixedNow = new Date("2026-08-20T12:00:00Z");
  class FixedDate extends Date {
    constructor(...args) {
      super(...(args.length ? args : [fixedNow]));
    }
  }
  const props = properties || {};
  const context = {
    console,
    SpreadsheetApp: {
      openById: () => ({
        getSheetByName: (name) => sheets[name] || null,
        insertSheet: (name) => {
          sheets[name] = new FakeSheet([], name);
          return sheets[name];
        },
      }),
    },
    PropertiesService: {
      getScriptProperties: () => ({
        getProperty: (key) => props[key] || "",
        setProperty: (key, value) => { props[key] = String(value); },
        deleteProperty: (key) => { delete props[key]; },
      }),
    },
    Utilities: makeUtilities(),
    Date: FixedDate,
  };
  vm.runInNewContext(appScriptSource, context);
  return { context, members, finance, props, sheets };

}

function payment(overrides = {}) {
  return {
    userId: "1001",
    username: "tester",
    package: "WEB",
    months: 1,
    days: 30,
    expectedAmount: 30000,
    receivedAmount: 30000,
    payType: "KPay",
    transactionNo: "TXN-1001",
    paymentId: "TXN-1001",
    date: "17/08/2026",
    time: "11:00",
    approvedBy: "admin",
    password: "stable-pass",
    source: "PAYMENT_SLIP",
    ...overrides,
  };
}

// New member: one member row and one approved Finance row.
{
  const env = makeContext([memberHeader], [financeHeader]);
  const result = env.context.approvePaymentTransaction_(payment());
  assert.equal(result.status, "ok");
  assert.equal(result.result, "approved");
  assert.equal(result.entryType, "NEW");
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.finance.rows.length, 2);
  assert.equal(env.members.rows[1][0], "1001");
  assert.equal(env.members.rows[1][7], "WEB");
  assert.equal(env.members.rows[1][6], "stable-pass");
  assert.equal(env.members.rows[1][3], "20/09/2026");
  assert.equal(env.finance.rows[1][11], "APPROVED");
  assert.equal(env.finance.rows[1][12], "NEW");
  assert.equal(env.finance.rows[1][13], "PAYMENT_SLIP");
}

// Durable payment drafts survive the in-memory bot session boundary and clear only after approval.
{
  const env = makeContext([memberHeader], [financeHeader]);
  const saved = env.context._savePaymentDraft_({
    userId: "1001", username: "tester", package: "CH", months: 1,
    amount: 15000, method: "kpay", total_paid: 15000,
    slips: [{ slip_info: { AMOUNT: "15000", DATE: "18/08/2026", TIME: "11:00", TYPE: "KPay", TRANSACTION_NO: "TXN-DRAFT", TRANSFER_TO: "KYAW MIN TUN" }, amount_num: 15000, txn_key: "TXN-DRAFT" }],
  });
  assert.equal(saved.status, "ok");
  const restored = env.context._getPaymentDraft_({ userId: "1001" });
  assert.equal(restored.found, true);
  assert.equal(restored.draft.slips[0].slip_info.TRANSACTION_NO, "TXN-DRAFT");
  const cleared = env.context._clearPaymentDraft_({ userId: "1001", transactionNo: "TXN-DRAFT" });
  assert.equal(cleared.result, "cleared");
  assert.equal(env.context._getPaymentDraft_({ userId: "1001" }).found, false);
}

// Repeating the same approval is idempotent: no second member row or Finance row.
{
  const env = makeContext([memberHeader], [financeHeader]);
  const first = env.context.approvePaymentTransaction_(payment());
  const second = env.context.approvePaymentTransaction_(payment());
  assert.equal(first.status, "ok");
  assert.equal(second.duplicate, true);
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.finance.rows.length, 2);
}

// Manual approval is atomic and idempotent: repeated command does not extend twice.
{
  const env = makeContext([memberHeader], [financeHeader]);
  const manual = {
    userId: "4004", username: "manual", package: "CH", months: 1, days: 30,
    approvedBy: "admin", operationId: "MANUAL-4004-CH-30-BUCKET-1",
  };
  const first = env.context.approveManualMemberTransaction_(manual);
  const second = env.context.approveManualMemberTransaction_(manual);
  assert.equal(first.status, "ok");
  assert.equal(first.result, "approved");
  assert.equal(first.entryType, "NEW");
  const expireAfterFirstApproval = env.members.rows[1][3];
  assert.equal(second.status, "ok");
  assert.equal(second.duplicate, true);
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.members.rows[1][3], expireAfterFirstApproval);
  assert.equal(env.finance.rows.length, 2);
  assert.equal(env.finance.rows[1][11], "APPROVED");
  assert.equal(env.finance.rows[1][12], "NEW");
  assert.equal(env.finance.rows[1][13], "MANUAL");
  assert.equal(env.finance.rows[1][14], manual.operationId);
}

// Standard -> Premium is an upgrade and does not create a duplicate member row.
{
  const env = makeContext([
    memberHeader,
    ["2002", "standard", "01/08/2026", "31/08/2026", "ACTIVE", 0, "", "CH", ""],
  ], [financeHeader]);
  const result = env.context.approvePaymentTransaction_(payment({
    userId: "2002", username: "standard", transactionNo: "TXN-UPGRADE", paymentId: "TXN-UPGRADE",
  }));
  assert.equal(result.status, "ok");
  assert.equal(result.entryType, "UPGRADE");
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.members.rows[1][7], "WEB");
  assert.equal(env.members.rows[1][6], "stable-pass");
  assert.equal(env.finance.rows[1][12], "UPGRADE");
}

// A stale/KICKED Premium row can be reactivated as Standard without a new member row.
{
  const env = makeContext([
    memberHeader,
    ["5509257916", "phyokoko116590", "29/06/2026", "29/07/2026", "KICKED", 0, "old-pass", "WEB-PROMO", ""],
  ], [financeHeader]);
  const result = env.context.approvePaymentTransaction_(payment({
    userId: "5509257916", username: "phyokoko116590", package: "CH",
    expectedAmount: 15000, receivedAmount: 15000,
    transactionNo: "TXN-REACTIVATE", paymentId: "TXN-REACTIVATE",
  }));
  assert.equal(result.status, "ok");
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.members.rows[1][0], "5509257916");
  assert.equal(env.members.rows[1][4], "ACTIVE");
  assert.equal(env.members.rows[1][7], "CH");
  assert.notEqual(env.members.rows[1][2], "29/06/2026");
}

// A pending row is recovered only when the canonical member exactly matches the saved transaction.
{
  const financeRows = [
    financeHeader,
    ["18/08/2026", "11:17", "3003", "premium", "WEB", 1, 30000, "KPay", "TXN-RECOVER", "", "", "PENDING", "RENEW", "PAYMENT_SLIP", "TXN-RECOVER", "admin", "", "PENDING member+finance transaction; source=PAYMENT_SLIP; userId=3003; package=WEB; days=30; months=1; entryType=RENEW; approvedBy=admin; financeDate=18/08/2026; previousStatus=ACTIVE; previousPackage=WEB; previousStart=01/08/2026; previousExpire=31/08/2026"],
  ];
  const env = makeContext([
    memberHeader,
    ["3003", "premium", "01/08/2026", "30/09/2026", "ACTIVE", 0, "old-pass", "WEB", ""],
  ], financeRows, { "JACC_TXN_STATE_TXN-RECOVER": "PENDING|2" });
  const result = env.context.approvePaymentTransaction_(payment({
    userId: "3003", username: "premium", transactionNo: "TXN-RECOVER", paymentId: "TXN-RECOVER",
  }));
  assert.equal(result.status, "ok");
  assert.equal(result.result, "recovered");
  assert.equal(env.members.rows.length, 2);
  assert.equal(env.finance.rows[1][11], "APPROVED");
  assert.equal(env.props["JACC_TXN_STATE_TXN-RECOVER"], undefined);
}

// A pending transaction is inspectable but is never silently replayed.
{
  const financeRows = [
    financeHeader,
    ["18/08/2026", "11:17", "1001", "tester", "WEB", 1, 30000, "KPay", "TXN-PENDING", "", "", "PENDING", "NEW", "PAYMENT_SLIP", "TXN-PENDING", "admin", "", "PENDING member+finance transaction"],
  ];
  const env = makeContext([memberHeader], financeRows, { "JACC_TXN_STATE_TXN-PENDING": "PENDING|2" });
  const result = env.context.approvePaymentTransaction_(payment({
    transactionNo: "TXN-PENDING", paymentId: "TXN-PENDING",
  }));
  assert.equal(result.message, "transaction_in_progress");
  const inspected = env.context.inspectPaymentTransaction_({ userId: "1001", paymentId: "TXN-PENDING" });
  assert.equal(inspected.status, "ok");
  assert.equal(inspected.finance.status, "PENDING");
  assert.equal(inspected.state, "PENDING|2");
}

// Existing Premium password is stable on renewal and the start date remains unchanged.
{
  const env = makeContext([
    memberHeader,
    ["3003", "premium", "01/08/2026", "31/08/2026", "ACTIVE", 0, "old-pass", "WEB", ""],
  ], [financeHeader]);
  env.sheets.AuthSessions = new FakeSheet([
    authSessionHeader,
    ["session-hash", "3003", "device-hash", "web", "19/08/2026", "19/09/2026", "ACTIVE", "", "19/08/2026"],
  ], "AuthSessions");
  const result = env.context.approvePaymentTransaction_(payment({
    userId: "3003", username: "premium", transactionNo: "TXN-RENEW", paymentId: "TXN-RENEW", password: "new-requested-pass",
  }));
  assert.equal(result.status, "ok");
  assert.equal(result.entryType, "RENEW");
  assert.equal(env.members.rows[1][2], "01/08/2026");
  assert.equal(env.members.rows[1][6], "old-pass");
  assert.equal(env.members.rows[1][7], "WEB");
  assert.equal(env.finance.rows[1][12], "RENEW");
  assert.equal(env.sheets.AuthSessions.rows[1][6], "REVOKED");
  assert.ok(env.sheets.AuthSessions.rows[1][7], "renewal should record a session revocation timestamp");
}

// Exact amount is fail-closed before any Member or Finance mutation.
{
  const env = makeContext([memberHeader], [financeHeader]);
  const result = env.context.approvePaymentTransaction_(payment({
    receivedAmount: 29999, transactionNo: "TXN-BAD", paymentId: "TXN-BAD",
  }));
  assert.equal(result.message, "payment_amount_mismatch");
  assert.equal(env.members.rows.length, 1);
  assert.equal(env.finance.rows.length, 1);
}

// A transaction already used by a different user is rejected.
{
  const financeRows = [
    financeHeader,
    ["17/08/2026", "10:00", "9999", "other", "WEB", 1, 30000, "KPay", "TXN-USED", "", "", "APPROVED", "NEW", "PAYMENT_SLIP", "TXN-USED", "admin", "", ""],
  ];
  const env = makeContext([memberHeader], financeRows);
  const result = env.context.approvePaymentTransaction_(payment({
    transactionNo: "TXN-USED", paymentId: "TXN-USED",
  }));
  assert.equal(result.message, "transaction_already_used");
  assert.equal(env.members.rows.length, 1);
  assert.equal(env.finance.rows.length, 2);
}

console.log("server transaction sync: ok");
