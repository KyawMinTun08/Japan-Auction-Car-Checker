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
console.log("finance report logic: ok");
