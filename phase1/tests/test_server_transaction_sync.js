const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const code = fs.readFileSync("Code.gs", "utf8");
const memberHeader = ["UserID", "Username", "Start", "Expire", "Status", "CancelCount", "Password", "Package", "Token"];
const financeHeader = [
  "Date", "Time", "UserID", "Username", "Package", "Months",
  "Amount(Ks)", "PayType", "TransactionNo", "TransferTo", "Sender", "Status",
  "EntryType", "Source", "PaymentID", "ApprovedBy", "ExpireDate", "Note",
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
  };
  vm.runInNewContext(code, context);
  return { context, members, finance, props };
}

function payment(overrides = {}) {
  return {
    userId: "1001",
    username: "tester",
    package: "WEB",
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
  assert.equal(env.finance.rows[1][11], "APPROVED");
  assert.equal(env.finance.rows[1][12], "NEW");
  assert.equal(env.finance.rows[1][13], "PAYMENT_SLIP");
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

// Existing Premium password is stable on renewal and the start date remains unchanged.
{
  const env = makeContext([
    memberHeader,
    ["3003", "premium", "01/08/2026", "31/08/2026", "ACTIVE", 0, "old-pass", "WEB", ""],
  ], [financeHeader]);
  const result = env.context.approvePaymentTransaction_(payment({
    userId: "3003", username: "premium", transactionNo: "TXN-RENEW", paymentId: "TXN-RENEW", password: "new-requested-pass",
  }));
  assert.equal(result.status, "ok");
  assert.equal(result.entryType, "RENEW");
  assert.equal(env.members.rows[1][2], "01/08/2026");
  assert.equal(env.members.rows[1][6], "old-pass");
  assert.equal(env.members.rows[1][7], "WEB");
  assert.equal(env.finance.rows[1][12], "RENEW");
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
