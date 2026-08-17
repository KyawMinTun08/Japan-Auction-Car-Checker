const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const code = fs.readFileSync("Code.gs", "utf8");

const header = [
  "Date", "Time", "UserID", "Username", "Package", "Months",
  "Amount(Ks)", "PayType", "TransactionNo", "TransferTo", "Sender", "Status",
  "EntryType", "Source", "PaymentID", "ApprovedBy", "ExpireDate", "Note",
];

const rows = [
  header,
  ["01/08/2026", "10:00", "1", "a", "Standard", 1, "10000", "KPay", "tx-1", "", "", "APPROVED", "NEW", "PAYMENT_SLIP", "tx-1", "admin", "", ""],
  ["05/08/2026", "11:00", "2", "b", "Premium", 1, "20000", "Wave", "tx-2", "", "", "APPROVED", "RENEW", "PAYMENT_SLIP", "tx-2", "admin", "", ""],
  ["10/08/2026", "12:00", "3", "c", "Premium", 1, "30000", "CB", "tx-3", "", "", "APPROVED", "UPGRADE", "PAYMENT_SLIP", "tx-3", "admin", "", ""],
  ["12/08/2026", "13:00", "4", "d", "Standard", 1, "", "MANUAL", "", "", "", "NO_PAYMENT", "RENEW", "MANUAL", "", "admin", "", ""],
  ["13/08/2026", "14:00", "5", "e", "Standard", 1, "10000", "KPay", "tx-1", "", "", "APPROVED", "NEW", "PAYMENT_SLIP", "tx-1", "admin", "", ""],
  ["31/07/2026", "14:00", "6", "f", "Standard", 1, "90000", "KPay", "tx-old", "", "", "APPROVED", "NEW", "PAYMENT_SLIP", "tx-old", "admin", "", ""],
];

const range = {
  getValues: () => [header],
  setFontWeight() { return this; },
  setBackground() { return this; },
  setFontColor() { return this; },
};
const sheet = {
  getLastRow: () => rows.length,
  getLastColumn: () => header.length,
  getRange: () => range,
  getDataRange: () => ({ getValues: () => rows }),
};

const context = {
  console,
  SpreadsheetApp: { openById: () => ({ getSheetByName: () => sheet }) },
  PropertiesService: { getScriptProperties: () => ({ getProperty: () => "test-key" }) },
  Utilities: { formatDate: () => "2026-08-01" },
};
vm.runInNewContext(code, context);

assert.equal(context._financeDateKey_("01/08/2026"), "2026-08-01");
assert.equal(context._financeDateKey_("2026-08-31"), "2026-08-31");
assert.equal(context._financeAmount_("55,000 Ks"), 55000);
assert.equal(context._financeMethod_("CB"), "Bank");
assert.equal(context._financeEntryType_("upgrade", "PAYMENT_SLIP"), "UPGRADE");

const result = context.getFinanceReport_("2026-08");
assert.equal(result.status, "ok");
assert.equal(result.summary.totalAmount, 60000);
assert.equal(result.summary.paymentCount, 3);
assert.equal(result.summary.activityCount, 4);
assert.equal(result.summary.duplicateCount, 1);
assert.equal(result.summary.missingTransactionCount, 0);
assert.equal(result.summary.legacyUnclassifiedCount, 0);
assert.equal(result.summary.legacyAmount, 0);
assert.equal(result.summary.byMethod.KPay.count, 1);
assert.equal(result.summary.byMethod.KPay.total, 10000);
assert.equal(result.summary.byMethod.Wave.count, 1);
assert.equal(result.summary.byMethod.Wave.total, 20000);
assert.equal(result.summary.byMethod.Bank.count, 1);
assert.equal(result.summary.byMethod.Bank.total, 30000);
assert.equal(result.summary.byMethod.Other.count, 0);
assert.equal(result.summary.byEntryType.NEW, 1);
assert.equal(result.summary.byEntryType.RENEW, 2);
assert.equal(result.summary.byEntryType.UPGRADE, 1);
assert.equal(result.summary.byEntryType.MANUAL, 0);
assert.equal(result.summary.byEntryType.PROMO, 0);
assert.equal(result.summary.byEntryType.UNKNOWN, 0);
assert.equal(result.summary.bySource.PAYMENT_SLIP, 3);
assert.equal(result.summary.bySource.MANUAL, 1);
assert.equal(result.summary.bySource.PROMO, 0);

const legacyRows = [
  header,
  ["20/08/2026", "15:00", "7", "g", "Standard", 1, "50000", "KPay", "legacy-tx", "", "", "APPROVED", "", "", "", "", "", ""],
];
const legacySheet = {
  getLastRow: () => legacyRows.length,
  getLastColumn: () => header.length,
  getRange: () => range,
  getDataRange: () => ({ getValues: () => legacyRows }),
};
context.SpreadsheetApp.openById = () => ({ getSheetByName: () => legacySheet });
const legacyResult = context.getFinanceReport_("2026-08");
assert.equal(legacyResult.summary.totalAmount, 0);
assert.equal(legacyResult.summary.paymentCount, 0);
assert.equal(legacyResult.summary.activityCount, 0);
assert.equal(legacyResult.summary.legacyUnclassifiedCount, 1);
assert.equal(legacyResult.summary.legacyAmount, 50000);

const dataFirstRows = [
  ["20/08/2026", "15:00", "7", "g", "Standard", 1, "50000", "KPay", "legacy-tx", "", "", "APPROVED", "", "", "", "", "", ""],
];
const dataFirstSheet = {
  getLastRow: () => dataFirstRows.length,
  getLastColumn: () => header.length,
  getRange: (row, col, numRows, numCols) => ({
    getValues: () => [dataFirstRows[0]],
    setFontWeight() { return this; },
    setBackground() { return this; },
    setFontColor() { return this; },
    setValue(value) {
      if (row === 1 && col >= 1 && col <= header.length) dataFirstRows[0][col - 1] = value;
      return this;
    },
  }),
  insertRowBefore: (row) => {
    assert.equal(row, 1);
    dataFirstRows.unshift(Array(header.length).fill(""));
  },
  getDataRange: () => ({ getValues: () => dataFirstRows }),
};
context.SpreadsheetApp.openById = () => ({ getSheetByName: () => dataFirstSheet });
const dataFirstResult = context.getFinanceReport_("2026-08");
assert.equal(dataFirstRows[0][0], "Date");
assert.equal(dataFirstResult.summary.totalAmount, 0);
assert.equal(dataFirstResult.summary.legacyUnclassifiedCount, 1);
assert.equal(dataFirstResult.summary.legacyAmount, 50000);
console.log("finance report logic: ok");
