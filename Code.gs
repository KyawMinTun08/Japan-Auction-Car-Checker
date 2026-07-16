// ═══════════════════════════════════════════════════════════
//  JAN JAPAN Auction — Apps Script (Code.gs)
//  Members Sheet Columns:
//  [0] UserID  [1] Username  [2] StartDate  [3] ExpireDate
//  [4] Status  [5] CancelCount  [6] Password  [7] Package  [8] Token
// ═══════════════════════════════════════════════════════════

var SS_ID    = "1ZRw9xUS2pqZe5rJdmBtsX6yS7hAc65BHDO6K3zG1mpY";
var MEMBERS  = "Members";
var LOG_SHEET = "ID_Change_Log";
var PAY_SHEET = "Payment_History";

// Column indexes (0-based)
var C_USERID   = 0;
var C_USERNAME = 1;
var C_START    = 2;
var C_EXPIRE   = 3;
var C_STATUS   = 4;
var C_CANCELCOUNT = 5;
var C_PASSWORD = 6;
var C_PACKAGE  = 7;
var C_TOKEN    = 8;

// ── doGet — Price Data ─────────────────────────────────────
function doGet(e) {
  try {
    var sheet = SpreadsheetApp.openById(SS_ID).getSheetByName("Sheet1");
    var rows   = sheet.getDataRange().getValues();
    var data   = [];
    for (var i = 1; i < rows.length; i++) {
      var row = rows[i];
      if (!row[1]) continue;

      var dateVal = row[0];
      var dateStr = (dateVal instanceof Date)
        ? Utilities.formatDate(dateVal, "Asia/Bangkok", "dd/MM/yyyy")
        : String(dateVal);

      data.push({
        date:      dateStr,
        chassis:   String(row[1] || ""),
        model:     String(row[2] || "UNKNOWN"),
        color:     String(row[3] || "-"),
        year:      parseInt(row[4]) || 0,
        price:     parseFloat(row[5]) || 0,
        location:  String(row[6] || ""),
        addedBy:   String(row[7] || ""),
        image_url: String(row[8] || "")
      });
    }

    return ContentService
      .createTextOutput(JSON.stringify({status:"ok", data:data}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status:"error", message:err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── doPost — All Actions ───────────────────────────────────
function doPost(e) {
  try {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
    var ss   = SpreadsheetApp.openById(SS_ID);
    var data = JSON.parse(e.postData.contents);
    var payload = data;

    switch (data.action) {

      // ── Save / Update Member ─────────────────────────────
      case "saveMember":
        return _json(saveMember(
          data.userId, data.username, data.days,
          data.password || "", data.package || "CH"
        ));

      // ── Get Members List ─────────────────────────────────
      case "getMembers":
        return _json({status:"ok", members: getMembers()});

      // ── Verify Login (Password → Token) ─────────────────
      case "validateLogin":
      case "verifyLogin":
        var loginResult = verifyLogin(data.password);
        writeAuditLog(
          loginResult.username || "Unknown",
          "LOGIN",
          "WebApp",
          loginResult.status === "ok" ? "SUCCESS" : "FAIL:" + (loginResult.message || "")
        );
        return _json(loginResult);

      // ── Verify Token (on page load) ──────────────────────
      case "verifyToken":
        return _json(verifyToken(data.token));

      // ── Get Password by UserID ───────────────────────────
      case "getPassword":
        return _json(getPassword(data.userId));

      // ── Reset Password ───────────────────────────────────
      case "resetPassword":
        return _json(resetPassword(data.username, data.password));

      // ── Update Member Telegram ID ────────────────────────
      case "updateMemberId":
        return _json(updateMemberId(data.username, data.newId, data.password));

      // ── Backup CSV ───────────────────────────────────────
      case "getBackupCSV":
        return _json(getBackupCSV());// ── Get Cars Count ─────────────────────────
      case "getCarsCount":
        var gcSheet = ss.getSheetByName("Sheet1");
        if (!gcSheet) return _json({count: 0});
        return _json({count: gcSheet.getLastRow() - 1});
        // —— Update Car (Price / Color / Model) ————
      case "updateCar":
        var uc_sheet   = ss.getSheetByName("Sheet1");
        var uc_field   = data.field;
        var uc_chassis = data.chassis;
        var uc_value   = data.value;
        var fieldMap   = { "price":"Price", "color":"Color", "model":"Model" };
        var colName    = fieldMap[uc_field];
        if (!colName) return _json({status:"error", msg:"Invalid field"});
        var uc_headers = uc_sheet.getRange(1,1,1,uc_sheet.getLastColumn()).getValues()[0];
        var uc_col     = uc_headers.indexOf(colName) + 1;
        var uc_chCol   = uc_headers.indexOf("Chassis") + 1;
        var uc_rows    = uc_sheet.getRange(2,uc_chCol,uc_sheet.getLastRow()-1,1).getValues();
        var uc_row     = -1;
        for (var i = 0; i < uc_rows.length; i++) {
          if (uc_rows[i][0].toString().toUpperCase() === uc_chassis.toUpperCase()) {
            uc_row = i + 2; break;
          }
        }
        if (uc_row === -1) return _json({status:"error", msg:"Chassis not found"});
        uc_sheet.getRange(uc_row, uc_col).setValue(uc_value);
        writeAuditLog('Admin', 'CAR_EDIT:' + uc_field, uc_chassis, uc_value);
        return _json({status:"ok"});
// —— Promo Code Redeem ————————————————————
 case "redeemPromo":
  var promoSheet = ss.getSheetByName("Promos");
  if (!promoSheet) return _json({status:"error", msg:"no_sheet"});
  var pCode   = data.code.toString().toUpperCase();
  var pUserId = String(data.userId);
  var pRows   = promoSheet.getDataRange().getValues();

  for (var pi = 1; pi < pRows.length; pi++) {
    if (pRows[pi][0].toString().toUpperCase() !== pCode) continue;

    var pUsed = pRows[pi][1] ? pRows[pi][1].toString().split(",").filter(Boolean) : [];
    var pMax  = parseInt(pRows[pi][2]) || 40;
    var pDays = parseInt(pRows[pi][3]) || 30;
    var pPkg  = String(pRows[pi][4] || 'WEB').trim().toUpperCase();

    if (pUsed.includes(pUserId))
      return _json({status:"error", msg:"already_used"});

    if (pUsed.length >= pMax)
      return _json({status:"error", msg:"max_reached", used:pUsed.length, max:pMax});

    pUsed.push(pUserId);
    promoSheet.getRange(pi+1, 2).setValue(pUsed.join(","));
    return _json({status:"ok", days:pDays, used:pUsed.length, max:pMax, package:pPkg});
  }
  return _json({status:"error", msg:"invalid_code"});
        












  






      // —— Promo Stats ————————————————————————
      case "promoStats":
        var psSheet = ss.getSheetByName("Promos");
        var psRows  = psSheet ? psSheet.getDataRange().getValues() : [];
        var psData  = [];
        for (var pj = 1; pj < psRows.length; pj++) {
          var psUsed = psRows[pj][1] ? psRows[pj][1].toString().split(",").filter(Boolean) : [];
          psData.push({code:psRows[pj][0], used:psUsed.length,
                       max:parseInt(psRows[pj][2])||40, days:parseInt(psRows[pj][3])||30});
        }
        return _json({status:"ok", stats:psData});// ── Verify Old ID // ── Update Member Status ──────────────────────────
      case "updateStatus":
        var usSheet = ss.getSheetByName("Members");
        if (!usSheet) return _json({status:"error", msg:"no_sheet"});
        var usId     = String(data.userId || "");
        var usStatus = String(data.status || "KICKED");
        var usRows   = usSheet.getDataRange().getValues();
        for (var ui = 1; ui < usRows.length; ui++) {
        if (String(usRows[ui][0]) === usId) {
        usSheet.getRange(ui + 1, 5).setValue(usStatus);
        writeAuditLog('Admin', usStatus === 'KICKED' ? 'KICK' : 'ACTIVATE', 'UserID:' + usId, 'SUCCESS');
        return _json({status:'ok', userId: usId, newStatus: usStatus});
      }
         
      
    
        
       
        }
        return _json({status:"error", msg:"not_found"});
      case "verifyOId":
        var voSheet = ss.getSheetByName("Members");
        if (!voSheet) return _json({status:"error", msg:"no_sheet"});
        var voUsername = (data.username || "").toString().toLowerCase().replace("@","");
        var voOldId    = String(data.oldId || "");
        var voRows     = voSheet.getDataRange().getValues();
        for (var vi = 1; vi < voRows.length; vi++) {
          var rowUser = (voRows[vi][1] || "").toString().toLowerCase().replace("@","");
          var rowId   = String(voRows[vi][0] || "");
          if (rowUser === voUsername && rowId === voOldId) {
            return _json({status:"ok", row: vi+1});
          }
        }
        return _json({status:"error", msg:"not_found"});

      // ── Log Payment to Finance Sheet ───────────────
      case "logPayment":
        var finSheet = ss.getSheetByName("Finance");
        if (!finSheet) {
          finSheet = ss.insertSheet("Finance");
          finSheet.appendRow([
            "Date","Time","UserID","Username","Package","Months",
            "Amount(Ks)","PayType","TransactionNo","TransferTo","Sender","Status"
          ]);
          finSheet.getRange(1,1,1,12).setFontWeight("bold")
            .setBackground("#1A2535").setFontColor("#FFFFFF");
        }
        var fp = data.payment || {};
        finSheet.appendRow([
          fp.date || "", fp.time || "", fp.userId || "",
          fp.username || "", fp.package || "", fp.months || "",
          fp.amount || "", fp.payType || "", fp.transactionNo || "",
          fp.receiver || "", fp.sender || "", fp.status || "APPROVED"
        ]);
        return _json({status:"ok"});
      case "getBrokers":
        var gbSheet = ss.getSheetByName("Brokers");
        if (!gbSheet) return _json({status:"ok", brokers:[]});
        var gbRows = gbSheet.getDataRange().getValues();
        var brokers = [];
        for (var gi = 1; gi < gbRows.length; gi++) {
          var r = gbRows[gi];
          brokers.push({
            brokerId:     String(r[0]||""),
            telegramId:   String(r[1]||""),
            username:     String(r[2]||""),
            status:       String(r[3]||"FREE"),
            rating:       Number(r[4]||0),
            deals:        Number(r[5]||0),
            rating1Count: Number(r[6]||0),
            joinDate:     String(r[7]||""),
            declineCount: Number(r[8]||0)
          })
        }
        return _json({status:"ok", brokers:brokers});

      // ── Add Broker ───────────────────────────────────
      case "addBroker":
        var abSheet = ss.getSheetByName("Brokers");
        if (!abSheet) {
          abSheet = ss.insertSheet("Brokers");
          abSheet.appendRow([
            "BrokerID","TelegramID","Username","Status",
            "Rating","Deals","Rating1Count","JoinDate","DeclineCount"
          ]),
          abSheet.getRange(1,1,1,8).setFontWeight("bold")
            .setBackground("#1A2535").setFontColor("#FFFFFF");
        }
        var ab = data;
        abSheet.appendRow([
          ab.brokerId   || "",
          ab.telegramId || "",
          ab.username   || "",
          "FREE", 0, 0, 0,
          Utilities.formatDate(new Date(),"Asia/Bangkok","dd/MM/yyyy")
        ]);
        return _json({status:"ok"});

      // ── Update Broker ─────────────────────────────────
      case "updateBroker":
        var ubSheet = ss.getSheetByName("Brokers");
        if (!ubSheet) return _json({status:"error",msg:"no_sheet"});
        var ubId   = String(data.telegramId||"");
        var ubRows = ubSheet.getDataRange().getValues();
        for (var ubi = 1; ubi < ubRows.length; ubi++) {
          if (String(ubRows[ubi][1]) === ubId) {
            if (data.status      !== undefined)
              ubSheet.getRange(ubi+1,4).setValue(data.status);
            if (data.rating      !== undefined)
              ubSheet.getRange(ubi+1,5).setValue(data.rating);
            if (data.deals       !== undefined)
              ubSheet.getRange(ubi+1,6).setValue(data.deals);
            if (data.rating1Count !== undefined)
              ubSheet.getRange(ubi+1,7).setValue(data.rating1Count);
             if (data.declineCount !== undefined)
             ubSheet.getRange(ubi+1,9).setValue(data.declineCount); 
            return _json({status:"ok"});
          }
        }
        return _json({status:"error",msg:"not_found"});
       // — Increment Decline Count ————————————
case "incrementDecline":
  var idSheet = ss.getSheetByName("Brokers");
  if (!idSheet) return _json({status:"error"});
  var idRows = idSheet.getDataRange().getValues();
  for (var ii = 1; ii < idRows.length; ii++) {
    if (String(idRows[ii][1]) === String(data.telegramId)) {
      var cur = Number(idRows[ii][8]||0);
      idSheet.getRange(ii+1, 9).setValue(cur + 1);
      return _json({status:"ok", declineCount: cur+1});
    }
  }
  return _json({status:"error", msg:"not_found"});
      // ── Add Request ───────────────────────────────────
      case "addRequest":
        var arSheet = ss.getSheetByName("Requests");
        if (!arSheet) {
          arSheet = ss.insertSheet("Requests");
          arSheet.appendRow([
            "ReqID","CustomerID","Username","CarType",
            "Budget","Year","Grade","Condition",
            "Timeline","Status","BrokerID","CreatedDate"
          ]);
          arSheet.getRange(1,1,1,12).setFontWeight("bold")
            .setBackground("#1A2535").setFontColor("#FFFFFF");
        }
        var ar = data;
        arSheet.appendRow([
          ar.reqId      || "",
          ar.customerId || "",
          ar.username   || "",
          ar.carType    || "",
          ar.budget     || "",
          ar.year       || "",
          ar.grade      || "",
          ar.condition  || "",
          ar.timeline   || "",
          "OPEN", "", 
          Utilities.formatDate(new Date(),"Asia/Bangkok","dd/MM/yyyy HH:mm")
        ]);
        return _json({status:"ok"});

      // ── Update Request ────────────────────────────────
      case "updateRequest":
        var urSheet = ss.getSheetByName("Requests");
        if (!urSheet) return _json({status:"error",msg:"no_sheet"});
        var urId   = String(data.reqId||"");
        var urRows = urSheet.getDataRange().getValues();
        for (var uri = 1; uri < urRows.length; uri++) {
          if (String(urRows[uri][0]) === urId) {
            if (data.status   !== undefined)
              urSheet.getRange(uri+1,10).setValue(data.status);
            if (data.brokerId !== undefined)
              urSheet.getRange(uri+1,11).setValue(data.brokerId);
            return _json({status:"ok"});
          }
        }
        return _json({status:"error",msg:"not_found"});// ── Get Request ──────────────────────────────
      case "getRequest":
        var grSheet = ss.getSheetByName("Requests");
        if (!grSheet) return _json({status:"error",msg:"no_sheet"});
        var grId   = String(data.reqId || "");
        var grRows = grSheet.getDataRange().getValues();
        for (var gri = 1; gri < grRows.length; gri++) {
          if (String(grRows[gri][0]) === grId) {
            return _json({
              status:     "ok",
              reqId:      String(grRows[gri][0]),
              customerId: String(grRows[gri][1]),
              username:   String(grRows[gri][2]),
              carType:    String(grRows[gri][3]),
              budget:     String(grRows[gri][4]),
              year:       String(grRows[gri][5]),
              grade:      String(grRows[gri][6]),
              condition:  String(grRows[gri][7]),
              timeline:   String(grRows[gri][8]),
              reqStatus:  String(grRows[gri][9]),
            });
          }
        }
        return _json({status:"error",msg:"not_found"});  // ════════════════════════════════════════════════════════
// DEPOSIT FLOW — Code.gs ADDITIONS
// "// ── Price Data (POST)" comment အပေါ်မှာ ထည့်ပါ
// ════════════════════════════════════════════════════════

case 'saveDeposit': {
  const ss = SpreadsheetApp.openById(SS_ID);
  let depSheet = ss.getSheetByName('Deposits');
  if (!depSheet) {
    depSheet = ss.insertSheet('Deposits');
    depSheet.appendRow([
      'ReqId','CustomerId','BrokerTgId',
      'THB_Amount','MMK_Amount','MMK_Rate',
      'Date','TxnNo','PayType','Status','AuctionResult','CarPrice'
    ]);
  }

  const {
    reqId, customerId, brokerTgId,
    thbAmount, mmkAmount, mmkRate,
    date, txnNo, payType
  } = payload;

  depSheet.appendRow([
    reqId, customerId, brokerTgId,
    thbAmount, mmkAmount, mmkRate,
    date, txnNo, payType,
    'HOLD', '', ''
  ]);

  return _json({ status: 'ok' });
}

case 'getDeposit': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const depSheet = ss.getSheetByName('Deposits');
  if (!depSheet) return _json({ status: 'error', msg: 'no_sheet' });

  const data    = depSheet.getDataRange().getValues();
  const headers = data[0];
  const reqIdx  = headers.indexOf('ReqId');
  const cidIdx  = headers.indexOf('CustomerId');
  const bidIdx  = headers.indexOf('BrokerTgId');
  const thbIdx  = headers.indexOf('THB_Amount');
  const mmkIdx  = headers.indexOf('MMK_Amount');
  const rateIdx = headers.indexOf('MMK_Rate');
  const statIdx = headers.indexOf('Status');

  for (let i = 1; i < data.length; i++) {
    if (data[i][reqIdx] == payload.reqId) {
      return _json({
        status:      'ok',
        reqId:       data[i][reqIdx],
        customerId:  String(data[i][cidIdx]),
        brokerTgId:  String(data[i][bidIdx]),
        thbAmount:   data[i][thbIdx],
        mmkAmount:   data[i][mmkIdx],
        mmkRate:     data[i][rateIdx],
        depositStatus: data[i][statIdx],
      });
    }
  }
  return _json({ status: 'error', msg: 'not_found' });
}

case 'updateDeposit': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const depSheet = ss.getSheetByName('Deposits');
  if (!depSheet) return _json({ status: 'error', msg: 'no_sheet' });

  const data      = depSheet.getDataRange().getValues();
  const headers   = data[0];
  const reqIdx    = headers.indexOf('ReqId');
  const statIdx   = headers.indexOf('Status');
  const resIdx    = headers.indexOf('AuctionResult');
  const priceIdx  = headers.indexOf('CarPrice');

  for (let i = 1; i < data.length; i++) {
    if (data[i][reqIdx] == payload.reqId) {
      // AuctionResult update
      if (payload.auctionResult) {
        depSheet.getRange(i + 1, resIdx + 1).setValue(payload.auctionResult);

        // Status update
        if (payload.auctionResult === 'WON') {
          depSheet.getRange(i + 1, statIdx + 1).setValue('WON');
        } else if (payload.auctionResult === 'LOST') {
          depSheet.getRange(i + 1, statIdx + 1).setValue('LOST');
        } else if (payload.auctionResult === 'REFUNDED') {
          depSheet.getRange(i + 1, statIdx + 1).setValue('REFUNDED');
        }
      }
      // CarPrice update
      if (payload.carPrice && priceIdx >= 0) {
        depSheet.getRange(i + 1, priceIdx + 1).setValue(payload.carPrice);
      }
      return _json({ status: 'ok' });
    }
  }
  return _json({ status: 'error', msg: 'not_found' }); 
  }
  case 'saveRating': {
  const rSs = SpreadsheetApp.openById(SS_ID);
  let rSheet = rSs.getSheetByName('Ratings');
  if (!rSheet) {
    rSheet = rSs.insertSheet('Ratings');
    rSheet.appendRow(['ReqId','BrokerId','CustomerId','Stars','Date']);
  }
  const now2 = Utilities.formatDate(new Date(),'Asia/Bangkok','dd/MM/yyyy HH:mm');
  rSheet.appendRow([payload.reqId, payload.brokerId, payload.customerId, payload.stars, now2]);

  const bSheet2 = rSs.getSheetByName('Brokers');
  if (!bSheet2) return _json({status:'ok', ban:false});
  const bData2 = bSheet2.getDataRange().getValues();
  const bH2 = bData2[0];
  const bidI = bH2.indexOf('BrokerId');
  const rI   = bH2.indexOf('Rating');
  const dI   = bH2.indexOf('Deals');
  const r1I  = bH2.indexOf('Rating1Count');
  const allR = rSheet.getDataRange().getValues();
  const bRatings = allR.slice(1).filter(r=>String(r[1])==String(payload.brokerId)).map(r=>Number(r[3]));
  const avg  = bRatings.length > 0 ? bRatings.reduce((a,b)=>a+b,0)/bRatings.length : 0;
  const one  = bRatings.filter(s=>s===1).length;
  const ban2 = one >= 3;
  for (let i=1; i<bData2.length; i++) {
    if (String(bData2[i][bidI]) == String(payload.brokerId)) {
      if (rI  >= 0) bSheet2.getRange(i+1,rI+1).setValue(avg.toFixed(2));
      if (dI  >= 0) bSheet2.getRange(i+1,dI+1).setValue(bRatings.length);
      if (r1I >= 0) bSheet2.getRange(i+1,r1I+1).setValue(one);
      break;
    }
  }
  return _json({status:'ok', ban:ban2, newRating:avg, oneStarCount:one});
}














































case 'getCancelCount': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const sheet = ss.getSheetByName('Members');
  if (!sheet) return _json({ status: 'error', cancelCount: 0 });

  const rows = sheet.getDataRange().getValues();
  const uid  = String(payload.userId || '');

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === uid) {
      const count = parseInt(rows[i][C_CANCELCOUNT]) || 0;
      return _json({ status: 'ok', cancelCount: count });
    }
  }
  return _json({ status: 'ok', cancelCount: 0 });
}

case 'saveCancelCount': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const sheet = ss.getSheetByName('Members');
  if (!sheet) return _json({ status: 'error', msg: 'no_sheet' });

  const rows    = sheet.getDataRange().getValues();
  const uid     = String(payload.userId || '');
  const newCount = parseInt(payload.cancelCount) || 0;

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === uid) {
      sheet.getRange(i + 1, C_CANCELCOUNT + 1).setValue(newCount);
      return _json({ status: 'ok', cancelCount: newCount });
    }
  }
  return _json({ status: 'error', msg: 'user_not_found' });
}

case 'banCustomer': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const sheet = ss.getSheetByName('Members');
  if (!sheet) return _json({ status: 'error', msg: 'no_sheet' });

  const rows      = sheet.getDataRange().getValues();
  const uid       = String(payload.userId || '');
  const banExpire = payload.banExpire || '';

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === uid) {
      // Status = BANNED
      sheet.getRange(i + 1, 5).setValue('BANNED');
      // ExpireDate = ban expire date (col 4, index 3, 1-based = 4)
      // Store ban info in the Token column and invalidate any active session.
      sheet.getRange(i + 1, C_TOKEN + 1).setValue('BAN_EXPIRE:' + banExpire);
      writeAuditLog('Admin', 'BAN', 'UserID:' + uid, 'expire:' + banExpire);
      return _json({ status: 'ok', banExpire: banExpire });
      
    }
  }
  return _json({ status: 'error', msg: 'user_not_found' });
}
 case 'getData': {
  var tokenResult = verifyToken(data.token);
  if (tokenResult.status !== 'ok') return _json({status:'error', msg:'invalid_token'});
  var gdSheet = ss.getSheetByName('Sheet1');
  if (!gdSheet) return _json({status:'error', msg:'no_sheet'});
  var gdRows = gdSheet.getDataRange().getValues();
  if (gdRows.length < 2) return _json({status:'ok', cars:[]});
  var gdCars = [];
  for (var gdi = 1; gdi < gdRows.length; gdi++) {
    var r = gdRows[gdi];
    if (!r[0] && !r[1]) continue;
    gdCars.push({
      date:     r[0] ? String(r[0]) : '',
      chassis:  r[1] ? String(r[1]) : '',
      model:    r[2] ? String(r[2]) : '',
      color:    r[3] ? String(r[3]) : '',
      year:     r[4] ? String(r[4]) : '',
      price:    r[5] ? String(r[5]) : '',
      location: r[6] ? String(r[6]) : '',
      addedBy:  r[7] ? String(r[7]) : '',
      imageUrl: r[8] ? String(r[8]) : ''
    });
  }
  return _json({status:'ok', cars:gdCars});
}
case 'removeBroker': {
  const telegramId = String(payload.telegramId || '').trim();
  if (!telegramId) return _json({ status: 'error', msg: 'telegramId missing' });

  const ss    = SpreadsheetApp.openById(SS_ID);
  const sheet = ss.getSheetByName('Brokers');
  if (!sheet) return _json({ status: 'error', msg: 'Brokers sheet not found' });

  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]).trim() === telegramId) {
      sheet.deleteRow(i + 1);
      return _json({ status: 'ok' });
    }
  }
  return _json({ status: 'error', msg: 'broker_not_found' });
}
case 'logVisitor': {
  const ss = SpreadsheetApp.openById(SS_ID);
  let sheet = ss.getSheetByName('Visitors');
  if (!sheet) {
    sheet = ss.insertSheet('Visitors');
    sheet.appendRow(['Date','Time','Country','City','Region','IP']);
    sheet.getRange(1,1,1,6).setFontWeight('bold')
      .setBackground('#1A2535').setFontColor('#FFFFFF');
  }
  const now = Utilities.formatDate(new Date(),'Asia/Bangkok','dd/MM/yyyy');
  const time = Utilities.formatDate(new Date(),'Asia/Bangkok','HH:mm:ss');
  sheet.appendRow([
    now,
    time,
    data.country || '',
    data.city    || '',
    data.region  || '',
    data.ip      || ''
  ]);
  return _json({ status: 'ok' });
}
case "getCompletedOutsideCount": {
  var custId = data.customerId;
  var reqSheet = ss.getSheetByName("Requests");
  var rows = reqSheet.getDataRange().getValues();
  var count = 0;
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][1]) === String(custId) &&
        String(rows[i][0]).startsWith("R") &&
        String(rows[i][9]).toUpperCase() === "COMPLETED") {
      count++;
    }
  }
  return ContentService.createTextOutput(
    JSON.stringify({status:"ok", count: count})
  ).setMimeType(ContentService.MimeType.JSON);
}
case "getAuctionCancelCount": {
  var custId = String(data.customerId || '');
  var acSheet = ss.getSheetByName("AuctionCancels");
  if (!acSheet) return _json({status:"ok", banCount:0});
  var rows = acSheet.getDataRange().getValues();
  var banCount = 0;
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === custId) {
      banCount = Number(rows[i][4]) || 0;
      break;
    }
  }
  // အသစ်:
var banStatus = '';
var banExpire = '';
for (var i = 1; i < rows.length; i++) {
  if (String(rows[i][0]) === custId) {
    banCount  = Number(rows[i][4]) || 0;
    banStatus = String(rows[i][5] || '');
    banExpire = String(rows[i][6] || '');
    break;
  }
}
return _json({status:"ok", banCount: banCount, banStatus: banStatus, banExpire: banExpire});
}

case "saveAuctionCancel": {
  var acSheet = ss.getSheetByName("AuctionCancels");
  if (!acSheet) {
    acSheet = ss.insertSheet("AuctionCancels");
    acSheet.appendRow(["CustomerID","Username","ReqId","CancelDate","BanCount","BanStatus","BanExpire"]);
    acSheet.getRange(1,1,1,7).setFontWeight("bold")
      .setBackground("#1A2535").setFontColor("#FFFFFF");
  }
  var now = Utilities.formatDate(new Date(),'Asia/Bangkok','dd/MM/yyyy');
  var custId   = String(data.customerId || '');
  var username = String(data.username || '');
  var reqId    = String(data.reqId || '');
  var banCount = Number(data.banCount || 1);
  var banStatus= String(data.banStatus || '');
  var banExpire= String(data.banExpire || '');

  // existing row update လုပ် မရှိရင် append
  var rows = acSheet.getDataRange().getValues();
  var found = false;
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === custId) {
      acSheet.getRange(i+1,3,1,5).setValues([[reqId, now, banCount, banStatus, banExpire]]);
      found = true; break;
    }
  }
  if (!found) {
    acSheet.appendRow([custId, username, reqId, now, banCount, banStatus, banExpire]);
  }
  return _json({status:"ok"});
}
case 'getMyRequests': {
  const ss = SpreadsheetApp.openById(SS_ID);
  const sheet = ss.getSheetByName('Requests');
  if (!sheet) return _json({status:'ok', requests:[]});
  const rows = sheet.getDataRange().getValues();
  const uid = String(payload.customerId || '');
  const results = [];
  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][1]) === uid) {
      results.push({
        reqId:    String(rows[i][0]),
        carType:  String(rows[i][3]),
        budget:   String(rows[i][4]),
        status:   String(rows[i][9]),
        brokerId: String(rows[i][10]),
      });
    }
  }
  return _json({status:'ok', requests: results.reverse()});
}
   // ── liftExpiredBans ──────────────────────────────────
    case "liftExpiredBans": {
      var acSheet  = ss.getSheetByName("AuctionCancels");
       if  (!acSheet) return _json({ lifted: [] });

      var rows     = acSheet.getDataRange().getValues();
      var today    = new Date();
      today.setHours(0, 0, 0, 0);
      var lifted   = [];

      for (var i = 1; i < rows.length; i++) {
        var banStatus = String(rows[i][5] || "").trim();
        var banExpire = String(rows[i][6] || "").trim();

        if (!banStatus || banStatus === "LIFETIME_BAN" || banStatus === "LIFTED") continue;
        if (banStatus !== "BAN_7D" && banStatus !== "BAN_1M") continue;
        if (!banExpire || banExpire === "LIFETIME") continue;

        var parts = banExpire.split("/");
        if (parts.length !== 3) continue;
        var expireDate = new Date(
          parseInt(parts[2]),
          parseInt(parts[1]) - 1,
          parseInt(parts[0])
        );
        expireDate.setHours(0, 0, 0, 0);

        if (today > expireDate) {
          acSheet.getRange(i + 1, 6).setValue("LIFTED");
          acSheet.getRange(i + 1, 7).setValue("");
          lifted.push({
            customerId: String(rows[i][0]),
            username:   String(rows[i][1] || ""),
            banStatus:  banStatus,
          });
        }
      }
      return _json({ lifted: lifted });
    }
     case 'getPaymentQR': {
      const method = data.method || '';
      if (!method) {
        return _json({ ok: false, error: 'method required' });
      }
      const result = getPaymentQR_(method);
      if (!result || !result.fileId) {
        return _json({ ok: false, error: 'QR not configured for ' + method });
      }
      return _json({
        ok: true,
        method: result.method,
        fileId: result.fileId,
        updated: result.updated
      });
    }
    
    case 'setPaymentQR': {
      const method = data.method || '';
      const fileId = data.fileId || '';
      const adminName = data.adminName || 'admin';
      if (!method || !fileId) {
        return _json({ ok: false, error: 'method and fileId required' });
      }
      const result = setPaymentQR_(method, fileId, adminName);
      return _json(result);
    }
      // ── Price Data (POST) ─────────────────────────────────
      default:
        var sheet = ss.getSheetByName("Sheet1");
        sheet.appendRow([
          data.date, data.chassis, data.model, data.color,
          data.year, data.price, data.location, data.added_by,
          data.image_url || ""
        ]);
        return _json({status:"ok"});
    }

  } catch(err) {
    return ContentService
      .createTextOutput(JSON.stringify({status:"error", message:err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
  
}
     // ── Audit Log ──────────────────────────────────────────
function writeAuditLog(actor, action, target, result) {
  try {
    var ss  = SpreadsheetApp.openById(SS_ID);
    var log = ss.getSheetByName('AuditLog');
    if (!log) {
      log = ss.insertSheet('AuditLog');
      log.appendRow(['Timestamp','Actor','Action','Target','Result']);
      log.getRange(1,1,1,5).setFontWeight('bold')
        .setBackground('#1A2535').setFontColor('#FFFFFF');
    }
    var now = Utilities.formatDate(new Date(),'Asia/Bangkok','dd/MM/yyyy HH:mm:ss');
    log.appendRow([now, actor, action, target, result]);
  } catch(e) {}
}
// ── Helper: JSON response ──────────────────────────────────
function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _parseMemberDate(value) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    var dateValue = new Date(value.getTime());
    dateValue.setHours(23, 59, 59, 999);
    return dateValue;
  }

  var text = String(value || "").trim();
  var match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  var parsed;
  if (match) {
    parsed = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  } else {
    match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    parsed = match
      ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
      : new Date(text);
  }

  if (isNaN(parsed.getTime())) return null;
  parsed.setHours(23, 59, 59, 999);
  return parsed;
}

function _normalizePackage(value) {
  var pkg = String(value || "CH").trim().toUpperCase()
    .replace(/[_-]+/g, " ");
  if (pkg.indexOf("WEB") !== -1 || pkg.indexOf("PREMIUM") !== -1) return "WEB";
  if (pkg === "CH" || pkg === "CH PROMO" || pkg.indexOf("STANDARD") !== -1 || pkg === "CHANNEL") return "CH";
  return pkg.replace(/\s+/g, "-") || "CH";
}

// ── saveMember ─────────────────────────────────────────────
function saveMember(userId, username, expireDays, password, pkg) {
  var ss     = SpreadsheetApp.openById(SS_ID);
  var sheet  = ss.getSheetByName(MEMBERS);
  var now    = new Date();
  var expire = new Date(now.getTime() + parseInt(expireDays) * 24 * 60 * 60 * 1000);
  var startStr  = Utilities.formatDate(now,    "Asia/Bangkok", "dd/MM/yyyy");
  var expireStr = Utilities.formatDate(expire, "Asia/Bangkok", "dd/MM/yyyy");
  var normalizedPackage = _normalizePackage(pkg);

  var rows = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_USERID]) === String(userId)) {
      // Update existing row
      sheet.getRange(i+1, C_START+1).setValue(startStr);
      sheet.getRange(i+1, C_EXPIRE+1).setValue(expireStr);
      sheet.getRange(i+1, C_STATUS+1).setValue("ACTIVE");
      if (password) sheet.getRange(i+1, C_PASSWORD+1).setValue(password);
      sheet.getRange(i+1, C_PACKAGE+1).setValue(normalizedPackage);
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      return {status:"ok", result:"updated"};
    }
  }

  // New member
  sheet.appendRow([
    userId, username, startStr, expireStr, "ACTIVE",
    0, password, normalizedPackage, ""
  ]);
  writeAuditLog('Admin', 'APPROVE', username, 'pkg:' + normalizedPackage);
  return {status:"ok", result:"added"};
  
}

// ── getMembers ─────────────────────────────────────────────
function getMembers() {
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows  = sheet.getDataRange().getValues();
  var now   = new Date();
  var members = [];
  for (var i = 1; i < rows.length; i++) {
    if (!rows[i][C_USERID]) continue;
    var rawDate    = rows[i][C_EXPIRE];
    var expireDate = _parseMemberDate(rawDate);
    var savedStatus = String(rows[i][C_STATUS] || "").trim().toUpperCase();
    var status = (savedStatus === "KICKED" || savedStatus === "BANNED")
      ? savedStatus
      : (expireDate && expireDate >= now ? "ACTIVE" : "EXPIRED");
    // Update status in sheet
    sheet.getRange(i+1, C_STATUS+1).setValue(status);
    members.push({
      userId:     String(rows[i][C_USERID]),
      username:   String(rows[i][C_USERNAME]),
      startDate:  String(rows[i][C_START]),
      expireDate: expireDate
        ? Utilities.formatDate(expireDate, "Asia/Bangkok", "dd/MM/yyyy")
        : String(rawDate || ""),
      status:     status,
      package:    _normalizePackage(rows[i][C_PACKAGE])
    });
  }
  return members;
}

// ── verifyLogin (Password → return token) ─────────────────
function verifyLogin(password) {
  if (!password) return {status:"error", message:"No password"};
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows  = sheet.getDataRange().getValues();
  var now   = new Date();

  for (var i = 1; i < rows.length; i++) {
    var storedPw = String(rows[i][C_PASSWORD] || "");
    if (!storedPw) continue;
    if (storedPw.trim() !== password.trim()) continue;

    var memberStatus = String(rows[i][C_STATUS] || "").trim().toUpperCase();
    if (memberStatus === "KICKED" || memberStatus === "BANNED" || memberStatus === "EXPIRED") {
      return {status:"error", message:memberStatus.toLowerCase()};
    }

    // Check expiry
    var rawDate    = rows[i][C_EXPIRE];
    var expireDate = _parseMemberDate(rawDate);
    if (!expireDate || expireDate < now) {
      return {status:"error", message:"expired"};
    }

    // Generate session token
    var token = Utilities.getUuid();
    sheet.getRange(i+1, C_TOKEN+1).setValue(token);
    return {
      status:     "ok",
      token:      token,
      userId:     String(rows[i][C_USERID]),
      username:   String(rows[i][C_USERNAME]),
      
      package:    _normalizePackage(rows[i][C_PACKAGE]),
      expireDate: Utilities.formatDate(expireDate, "Asia/Bangkok", "dd/MM/yyyy")
    };
  }

  return {status:"error", message:"wrong_password"};
}

// ── verifyToken ────────────────────────────────────────────
function verifyToken(token) {
  if (!token) return {status:"error", message:"No token"};
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows  = sheet.getDataRange().getValues();
  var now   = new Date();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_TOKEN]) !== token) continue;
    var memberStatus = String(rows[i][C_STATUS] || "").trim().toUpperCase();
    if (memberStatus === "KICKED" || memberStatus === "BANNED" || memberStatus === "EXPIRED") {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      return {status:"error", message:memberStatus.toLowerCase()};
    }
    var rawDate    = rows[i][C_EXPIRE];
    var expireDate = _parseMemberDate(rawDate);
    if (!expireDate || expireDate < now) {
      sheet.getRange(i+1, C_TOKEN+1).setValue("");
      // Clear expired token
      return {status:"error", message:"expired"};
    }
    return {
      status:     "ok",
      userId:     String(rows[i][C_USERID]),
      username:   String(rows[i][C_USERNAME]),
      
      package:    _normalizePackage(rows[i][C_PACKAGE]),
      expireDate: Utilities.formatDate(expireDate, "Asia/Bangkok", "dd/MM/yyyy")
    };
  }

  return {status:"error", message:"invalid_token"};
}

// ── getPassword ────────────────────────────────────────────
function getPassword(userId) {
  if (!userId) return {status:"error"};
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows  = sheet.getDataRange().getValues();
  var now   = new Date();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_USERID]) !== String(userId)) continue;
    var memberStatus = String(rows[i][C_STATUS] || "").trim().toUpperCase();
    if (memberStatus === "KICKED" || memberStatus === "BANNED" || memberStatus === "EXPIRED") {
      return {status:"error", message:memberStatus.toLowerCase()};
    }
    var rawDate    = rows[i][C_EXPIRE];
    var expireDate = _parseMemberDate(rawDate);
    if (!expireDate || expireDate < now) return {status:"error", message:"expired"};

    var pw = String(rows[i][C_PASSWORD] || "");
    if (!pw) return {status:"error", message:"no_password"};
    return {status:"ok", password: pw, package: _normalizePackage(rows[i][C_PACKAGE])};
  }
  return {status:"error", message:"not_found"};
}

// ── resetPassword ──────────────────────────────────────────
function resetPassword(username, newPassword) {
  if (!username || !newPassword) return {status:"error"};
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName('Members');
  var rows  = sheet.getDataRange().getValues();
  var uname = username.replace("@","").toLowerCase();
  for (var i = 1; i < rows.length; i++) {
    var rowUserId = String(rows[i][C_USERID]   || "").trim();
    var rowUser   = String(rows[i][C_USERNAME] || "").replace("@","").toLowerCase().trim();
    if (rowUser !== uname && rowUserId !== uname) continue;
    sheet.getRange(i+1, C_PASSWORD+1).setValue(newPassword);
    sheet.getRange(i+1, C_TOKEN+1).setValue("");
    writeAuditLog('Admin', 'PASSWORD_RESET', uname, 'SUCCESS');
    return {
      status:   "ok",
      userId:   rowUserId,
      username: String(rows[i][C_USERNAME])
    };
  }
  return {status:"error", message:"not_found"};
}






















// ── updateMemberId ─────────────────────────────────────────
function updateMemberId(username, newId, newPassword) {
  if (!username || !newId) return {status:"error"};
  var ss      = SpreadsheetApp.openById(SS_ID);
  var sheet   = ss.getSheetByName(MEMBERS);
  var rows    = sheet.getDataRange().getValues();
  var uname   = username.replace("@","").toLowerCase();
  var nowStr  = Utilities.formatDate(new Date(), "Asia/Bangkok", "dd/MM/yyyy HH:mm");

  for (var i = 1; i < rows.length; i++) {
    var rowUser = String(rows[i][C_USERNAME] || "").replace("@","").toLowerCase();
    if (rowUser !== uname) continue;

    var oldId = String(rows[i][C_USERID]);

    // Update ID
    sheet.getRange(i+1, C_USERID+1).setValue(String(newId));
    // Update password if provided
    if (newPassword) sheet.getRange(i+1, C_PASSWORD+1).setValue(newPassword);
    // Clear token (force re-login)
    sheet.getRange(i+1, C_TOKEN+1).setValue("");
    // Log the change
    _logIdChange(ss, username, oldId, String(newId), nowStr);

    return {status:"ok", oldId: oldId, username: username};
  }
  return {status:"error", message:"not_found"};
}

function _logIdChange(ss, username, oldId, newId, changeDate) {
  try {
    var logSheet = ss.getSheetByName(LOG_SHEET);
    if (!logSheet) {
      logSheet = ss.insertSheet(LOG_SHEET);
      logSheet.appendRow(["Username", "Old_ID", "New_ID", "Changed_Date", "Changed_By"]);
    }
    logSheet.appendRow([username, oldId, newId, changeDate, "Admin"]);
  } catch(e) {}
}

// ── getBackupCSV ───────────────────────────────────────────
function getBackupCSV() {
  try {
    var ss    = SpreadsheetApp.openById(SS_ID);
    var sheet = ss.getSheetByName(MEMBERS);
    var rows  = sheet.getDataRange().getValues();

    var csv = [];
    // Header (exclude Token column for security)
    csv.push(["UserID","Username","StartDate","ExpireDate","Status","Package"].join(","));
    for (var i = 1; i < rows.length; i++) {
      if (!rows[i][C_USERID]) continue;
      csv.push([
        rows[i][C_USERID],
        rows[i][C_USERNAME],
        rows[i][C_START],
        rows[i][C_EXPIRE],
        rows[i][C_STATUS],
        rows[i][C_PACKAGE] || "CH"
      ].map(function(v){ return '"'+String(v).replace(/"/g,'""')+'"'; }).join(","));
    }

    return {status:"ok", csv: csv.join("\n")};
  } catch(e) {
    return {status:"error", message:e.toString()};
  }
}

// ── setupSheet ─────────────────────────────────────────────
function setupSheet() {
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);

  // Ensure headers exist with new columns
  sheet.getRange(1, 1, 1, 9).setValues([[
    "UserID", "Username", "StartDate", "ExpireDate",
    "Status", "CancelCount", "Password", "Package", "Token"
  ]]);

  // Create Log sheet if needed
  if (!ss.getSheetByName(LOG_SHEET)) {
    var log = ss.insertSheet(LOG_SHEET);
    log.appendRow(["Username","Old_ID","New_ID","Changed_Date","Changed_By"]);
  }

  // Create Payment_History sheet if needed
  if (!ss.getSheetByName(PAY_SHEET)) {
    var pay = ss.insertSheet(PAY_SHEET);
    pay.appendRow(["Date","UserID","Username","Package","Months","Amount","PayType","Reference","Approved"]);
  }
}

// ── Weekly Auto Backup (Sunday 6AM) ───────────────────────
function weeklyBackup() {
  var result = getBackupCSV();
  if (result.status !== "ok") return;

  var filename = "Members_Backup_" + Utilities.formatDate(new Date(), "Asia/Bangkok", "yyyy-MM-dd") + ".csv";
  var folder   = DriveApp.getRootFolder(); // Root folder — change to specific folder if needed
  folder.createFile(filename, result.csv, MimeType.CSV);
  Logger.log("Backup saved: " + filename);
}

// ── Daily Duplicate UserID Check ──────────────────────────
function dailyDuplicateCheck() {
  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName(MEMBERS);
  var rows  = sheet.getDataRange().getValues();
  var seen  = {}, dups = [];
  for (var i = 1; i < rows.length; i++) {
    var uid = String(rows[i][C_USERID] || "");
    if (!uid) continue;
    if (seen[uid]) {
      dups.push(uid + " (rows " + (seen[uid]+1) + " & " + (i+1) + ")");
    } else {
      seen[uid] = i;
    }
  }

  if (dups.length > 0) {
    Logger.log("⚠️ Duplicate UserIDs found: " + dups.join(", "));
    // Note: To send Telegram notification, use UrlFetchApp with bot token
  }
}
function monthlyPasswordReset() {
  var BOT_TOKEN = PropertiesService.getScriptProperties().getProperty("BOT_TOKEN");
  if (!BOT_TOKEN) {
    Logger.log("BOT_TOKEN is not configured in Script Properties.");
    return;
  }

  var ss    = SpreadsheetApp.openById(SS_ID);
  var sheet = ss.getSheetByName("Members");
  var rows  = sheet.getDataRange().getValues();

  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][C_STATUS]).toUpperCase() !== "ACTIVE") continue;
    if (_normalizePackage(rows[i][C_PACKAGE]) !== "WEB") continue;

    var userId   = String(rows[i][C_USERID]);
    var username = rows[i][C_USERNAME] || "Member";

    // Password အသစ် generate
    var chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    var pw = "KMT-";
    for (var j = 0; j < 6; j++) pw += chars[Math.floor(Math.random()*chars.length)];
    pw += "-";
    for (var k = 0; k < 4; k++) pw += chars[Math.floor(Math.random()*chars.length)];

    // Sheet မှာ သိမ်း
    sheet.getRange(i+1, C_PASSWORD+1).setValue(pw);
    sheet.getRange(i+1, C_TOKEN+1).setValue("");

    // Bot က DM ပို့
    var msg = "🔄 *Password အသစ် (Monthly Reset)*\n\n"
            + "🔑 Password: `" + pw + "`\n\n"
            + "🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
            + "⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့\n"
            + "   မျှဝေပါက Membership ပိတ်သိမ်းခံရမည်";

    try {
      var url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage";
      UrlFetchApp.fetch(url, {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify({
          chat_id:    userId,
          text:       msg,
          parse_mode: "Markdown"
        })
      });
    } catch(e) {
      Logger.log("DM failed for " + userId + ": " + e);
    }

    Utilities.sleep(500);
  }
}
// ═══════════════════════════════════════════
// PAYMENT QR HANDLERS (KPay / Wave / CB Bank)
// ═══════════════════════════════════════════

function getOrCreatePaymentConfig_() {
  const ss = SpreadsheetApp.openById(SS_ID);
  let sh = ss.getSheetByName('PaymentConfig');
  if (!sh) {
    sh = ss.insertSheet('PaymentConfig');
    sh.appendRow(['Method', 'FileID', 'UpdatedDate', 'UpdatedBy']);
    sh.getRange(1, 1, 1, 4)
      .setFontWeight('bold')
      .setBackground('#1a73e8')
      .setFontColor('#ffffff');
    sh.setColumnWidth(1, 80);
    sh.setColumnWidth(2, 320);
    sh.setColumnWidth(3, 160);
    sh.setColumnWidth(4, 120);
    sh.setFrozenRows(1);
  }
  return sh;
}

function getPaymentQR_(method) {
  const sh = getOrCreatePaymentConfig_();
  const data = sh.getDataRange().getValues();
  const m = String(method).toLowerCase().trim();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]).toLowerCase().trim() === m) {
      return {
        method: data[i][0],
        fileId: data[i][1],
        updated: data[i][2],
        updatedBy: data[i][3]
      };
    }
  }
  return null;
}

function setPaymentQR_(method, fileId, adminName) {
  const sh = getOrCreatePaymentConfig_();
  const data = sh.getDataRange().getValues();
  const now = new Date();
  const m = String(method).toLowerCase().trim();
  
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]).toLowerCase().trim() === m) {
      sh.getRange(i + 1, 2).setValue(fileId);
      sh.getRange(i + 1, 3).setValue(now);
      sh.getRange(i + 1, 4).setValue(adminName || 'admin');
      return { ok: true, action: 'updated', method: m };
    }
  }
  
  sh.appendRow([m, fileId, now, adminName || 'admin']);
  return { ok: true, action: 'created', method: m };
}

// Manual test (Run > testPaymentQR_)
function testPaymentQR_() {
  const r1 = setPaymentQR_('kpay', 'TEST_FILE_ID', 'tun');
  Logger.log('SET: ' + JSON.stringify(r1));
  const r2 = getPaymentQR_('kpay');
  Logger.log('GET: ' + JSON.stringify(r2));
}






  
















































































































































    



    











      
















      









































































































































































  
