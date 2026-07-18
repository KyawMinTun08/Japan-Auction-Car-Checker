/** JACC Phase 3 — Website Payment Integration
 * Add this file to the existing Apps Script project.
 * Required Script Properties: BOT_TOKEN, ADMIN_CHAT_ID, PAYMENT_DRIVE_FOLDER_ID
 */
const PAYMENT_SHEET_NAME = 'PaymentRequests';

function handlePhase3PaymentAction_(body) {
  const action = String(body.action || '');
  if (action === 'submitWebPayment') return submitWebPayment_(body);
  if (action === 'getWebPaymentStatus') return getWebPaymentStatus_(body.paymentId, body.userId);
  if (action === 'approveWebPayment') return approveWebPayment_(body.paymentId, body.adminId);
  if (action === 'rejectWebPayment') return rejectWebPayment_(body.paymentId, body.adminId, body.reason);
  return null;
}

function submitWebPayment_(body) {
  const userId = clean_(body.userId);
  const username = clean_(body.username);
  const packageName = clean_(body.package || 'WEB').toUpperCase();
  const months = Math.max(1, Number(body.months || 1));
  const amount = clean_(body.amount);
  const method = clean_(body.method).toUpperCase();
  const imageData = String(body.slipBase64 || '');
  const mimeType = clean_(body.mimeType || 'image/jpeg');
  if (!userId || !imageData) throw new Error('userId and slipBase64 are required');
  const paymentId = 'WP-' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyyMMdd-HHmmss') + '-' + Math.floor(Math.random() * 9000 + 1000);
  const slipUrl = savePaymentSlip_(paymentId, imageData, mimeType);
  const sh = getPaymentSheet_();
  sh.appendRow([paymentId, new Date(), userId, username, packageName, months, amount, method, slipUrl, 'PENDING', '', '', new Date()]);
  notifyPaymentAdmin_({paymentId, userId, username, packageName, months, amount, method, slipUrl});
  return {ok:true, paymentId:paymentId, status:'PENDING', slipUrl:slipUrl};
}

function getWebPaymentStatus_(paymentId, userId) {
  const row = findPaymentRow_(paymentId);
  if (!row) return {ok:false, error:'PAYMENT_NOT_FOUND'};
  if (userId && clean_(row.values[2]) !== clean_(userId)) return {ok:false, error:'FORBIDDEN'};
  return {ok:true, paymentId:row.values[0], status:row.values[9], package:row.values[4], months:row.values[5], amount:row.values[6], method:row.values[7], updatedAt:row.values[12]};
}

function approveWebPayment_(paymentId, adminId) {
  const row = findPaymentRow_(paymentId);
  if (!row) return {ok:false, error:'PAYMENT_NOT_FOUND'};
  if (String(row.values[9]).toUpperCase() === 'APPROVED') return {ok:true, status:'APPROVED', alreadyApproved:true};
  const userId = clean_(row.values[2]);
  const username = clean_(row.values[3]);
  const pkg = clean_(row.values[4]);
  const months = Number(row.values[5] || 1);
  const password = pkg === 'WEB' ? generateWebPassword_() : '';
  const saved = saveMember(userId, username, months * 30, password, pkg);
  if (saved === false) return {ok:false, error:'MEMBER_SAVE_FAILED'};
  row.sheet.getRange(row.row, 10, 1, 4).setValues([['APPROVED', clean_(adminId), '', new Date()]]);
  sendTelegramMessage_(userId, '✅ JACC payment approved!\n📦 Package: ' + pkg + '\n📅 Duration: ' + months + ' month(s)' + (password ? '\n🔑 Website password: ' + password : ''));
  return {ok:true, status:'APPROVED', userId:userId, package:pkg, months:months, password:password};
}

function rejectWebPayment_(paymentId, adminId, reason) {
  const row = findPaymentRow_(paymentId);
  if (!row) return {ok:false, error:'PAYMENT_NOT_FOUND'};
  row.sheet.getRange(row.row, 10, 1, 4).setValues([['REJECTED', clean_(adminId), clean_(reason || 'Payment could not be verified'), new Date()]]);
  sendTelegramMessage_(clean_(row.values[2]), '❌ JACC payment rejected.\nReason: ' + clean_(reason || 'Payment could not be verified') + '\nPlease upload a clear payment slip again.');
  return {ok:true, status:'REJECTED'};
}

function getPaymentSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PAYMENT_SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(PAYMENT_SHEET_NAME);
    sh.appendRow(['PaymentID','CreatedAt','UserID','Username','Package','Months','Amount','Method','SlipURL','Status','AdminID','RejectReason','UpdatedAt']);
    sh.setFrozenRows(1);
  }
  return sh;
}

function findPaymentRow_(paymentId) {
  const sh = getPaymentSheet_();
  const values = sh.getDataRange().getValues();
  for (let i = 1; i < values.length; i++) if (String(values[i][0]) === String(paymentId)) return {sheet:sh,row:i+1,values:values[i]};
  return null;
}

function savePaymentSlip_(paymentId, dataUrl, mimeType) {
  const folderId = PropertiesService.getScriptProperties().getProperty('PAYMENT_DRIVE_FOLDER_ID');
  if (!folderId) throw new Error('PAYMENT_DRIVE_FOLDER_ID is missing');
  const raw = dataUrl.indexOf(',') >= 0 ? dataUrl.split(',').pop() : dataUrl;
  const ext = mimeType.indexOf('png') >= 0 ? 'png' : 'jpg';
  const blob = Utilities.newBlob(Utilities.base64Decode(raw), mimeType, paymentId + '.' + ext);
  const file = DriveApp.getFolderById(folderId).createFile(blob);
  return file.getUrl();
}

function notifyPaymentAdmin_(p) {
  const props = PropertiesService.getScriptProperties();
  const admin = props.getProperty('ADMIN_CHAT_ID');
  const token = props.getProperty('BOT_TOKEN');
  if (!admin || !token) throw new Error('BOT_TOKEN or ADMIN_CHAT_ID is missing');
  const text = '💳 NEW WEBSITE PAYMENT\n\n🆔 ' + p.paymentId + '\n👤 @' + (p.username || '-') + ' (' + p.userId + ')\n📦 ' + p.packageName + ' · ' + p.months + ' month(s)\n💰 ' + p.amount + '\n🏦 ' + p.method;
  const keyboard = {inline_keyboard:[[{text:'✅ Approve',callback_data:'webpay_approve_' + p.paymentId},{text:'❌ Reject',callback_data:'webpay_reject_' + p.paymentId}],[{text:'🧾 Open Slip',url:p.slipUrl}]]};
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage',{method:'post',contentType:'application/json',payload:JSON.stringify({chat_id:admin,text:text,reply_markup:keyboard})});
}

function sendTelegramMessage_(chatId, text) {
  const token = PropertiesService.getScriptProperties().getProperty('BOT_TOKEN');
  if (!token || !chatId) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage',{method:'post',contentType:'application/json',payload:JSON.stringify({chat_id:chatId,text:text})});
}

function generateWebPassword_() { return Math.random().toString(36).slice(-8).toUpperCase(); }
function clean_(v) { return String(v == null ? '' : v).trim(); }
