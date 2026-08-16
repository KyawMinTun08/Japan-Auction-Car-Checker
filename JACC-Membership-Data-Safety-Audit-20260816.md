# JACC Membership Data-Safety Audit and Hardening

**ရက်စွဲ:** 16/08/2026  
**ရည်ရွယ်ချက်:** Member အသစ် approve/payment, renewal, Premium password, expiry date, payment history နှင့် recovery ကို data မပျောက်စေရန် စစ်ဆေးပြီး hardening လုပ်ခြင်း။

## 1. လက်ရှိအခြေအနေ

| အပိုင်း | အခြေအနေ | မှတ်ချက် |
|---|---|---|
| Source backup | ပြီး | Local Git bundle နှင့် source archive ဖန်တီးထားသည်။ |
| Live Google Sheet backup | ပြီး | Members, Finance, Payments, နှင့် ရှိပြီးသား Members backup ကို read-only export လုပ်ထားသည်။ |
| Hardening branch | ပြီး | `hardening/membership-data-safety-20260816` |
| Pull Request | Open | [PR #53](https://github.com/KyawMinTun08/Japan-Auction-Car-Checker/pull/53) |
| Latest hardening commit | ပြီး | `22e9cc3` |
| Apps Script source | ပြင်ပြီး | `Code.gs` ထဲရှိသော်လည်း Google Apps Script project ထဲသို့ deploy မလုပ်ရသေးပါ။ |
| Railway bot | မစစ်ဆေးရသေး | Apps Script deploy နှင့် PR merge ပြီးမှ Railway redeploy လုပ်ရမည်။ |
| Automated tests | အောင်မြင် | Focused tests `14 passed`; Python compile, Apps Script syntax, helper harness အောင်မြင်။ |
| PR status | Merge မလုပ်ရသေး | Phase 1 CI အောင်မြင်။ Vercel check တစ်ခု fail ဖြစ်နေပြီး bot hardening နှင့် တိုက်ရိုက်မသက်ဆိုင်သော preview/deployment check ဖြစ်သည်။ |

> **အရေးကြီး:** Code update, Apps Script deployment, Railway deployment, service active, functional test passed ဆိုသည်မှာ အဆင့်ကွဲများ ဖြစ်ပါသည်။ အခုအချိန်တွင် code/branch/test/backup ပြီးသော်လည်း production deployment နှင့် live functional test မပြီးသေးပါ။

## 2. တွေ့ရှိခဲ့သော အဓိက Risk များ

### 2.1 Premium password ကို အလိုအလျောက်ပြောင်းနေခြင်း

`monthlyPasswordReset()` သည် Active Web Premium member အားလုံး၏ Password ကို လစဉ်အသစ်ပြောင်းပြီး Telegram DM ပို့နေပါသည်။ Member အဟောင်းက Password အဟောင်းနှင့် login လုပ်လျှင် error ဖြစ်နိုင်သည့် အဓိကအကြောင်းရင်းဖြစ်ပါသည်။ အခု hardening တွင် function name နှင့် ရှိပြီးသား trigger ကို မဖျက်ဘဲ function ကို safe no-op ပြောင်းထားပါသည်။ Password သည် explicit admin reset သို့မဟုတ် account recovery လုပ်သည့်အခါမှသာ ပြောင်းရမည်။

### 2.2 Payment history source နှစ်ခုရှိခြင်း

Live Google Sheet တွင် `Finance` နှင့် `Payments` ဟူသော payment source နှစ်ခုရှိပါသည်။ လက်ရှိ `/backup` သည် Members ၏ UserID, Username, StartDate, ExpireDate, Status, Package ပဲ export လုပ်ပြီး payment records မပါပါ။ ထို့ကြောင့် payment ဘာဖြစ်သွားသည်ကို နောက်မှပြန်စစ်ရန် မလုံလောက်ပါ။ အခု backup flow သည် Members recovery, `Finance`, `Payments` သုံးခုလုံးကို သီးခြား export လုပ်မည်။

### 2.3 Approve ကို ထပ်နှိပ်လျှင် သက်တမ်းနှစ်ကြိမ်တိုးနိုင်ခြင်း

Sheet write အောင်မြင်ပြီး Telegram reply/DM အဆင့်တွင် error ဖြစ်လျှင် အရင် handler က failed ဟုမြင်ပြီး ထပ် approve လုပ်ခွင့်ပေးနိုင်ပါသည်။ အခု `Membership_Operations` ledger နှင့် stable operation ID ထည့်ထားပြီး payment reference တူသော retry ကို `already_applied` အဖြစ် ပြန်ပေးမည်။ ဒါကြောင့် တူညီသော payment ကို နှစ်ကြိမ် renewal မဖြစ်အောင် ကာကွယ်ထားပါသည်။

### 2.4 Local တွက်ထားသော expiry date ကို admin ထံပြခြင်း

Premium renewal သည် လက်ရှိ expiry date မကုန်သေးလျှင် လက်ရှိ expiry နောက်မှ purchased days ထပ်ပေါင်းပါသည်။ Bot က `now + days` ဖြင့် local date တွက်ပြလျှင် Sheet ထဲက canonical expiry နှင့် မတူနိုင်ပါသည်။ အခု approval confirmation သည် save ပြီးနောက် `getMembers` မှ canonical `expireDate` နှင့် `package` ကို ပြန်ဖတ်ပြီးမှ ပြမည်။

### 2.5 Sheet save failure ကို မစစ်ဘဲ success ပြနိုင်ခြင်း

Manual `/approve` နှင့် Quick Approve လမ်းကြောင်းများသည် Sheet write result ကို မစစ်ဘဲ ဆက်လက် success ပြနိုင်သည့် အန္တရာယ်ရှိပါသည်။ အခု write မအောင်မြင်လျှင် fail closed ဖြစ်ပြီး approve မပြီးသေးကြောင်း ပြမည်။ ထို့အပြင် Admin message ထဲတွင် Premium Password ကို မပြတော့ပါ။

## 3. ထည့်သွင်းထားသော Safeguards

| Safeguard | ရလဒ် |
|---|---|
| `monthlyPasswordReset()` disabled | Premium Password သည် မိမိအလိုလို မပြောင်းတော့ပါ။ |
| Operation ledger | တူညီသော payment retry သည် expiry ကို ထပ်မတိုးတော့ပါ။ |
| Existing WEB password preservation | WEB → WEB renewal တွင် Password အဟောင်းကို ထိန်းထားပါသည်။ |
| Canonical post-save read-back | Admin သည် Sheet ထဲက အမှန်တကယ် expiry/package ကို မြင်ရမည်။ |
| Fail-closed manual/Quick Approve | Sheet save မအောင်မြင်လျှင် false success မပြတော့ပါ။ |
| Idempotent Finance logging | Transaction number တူလျှင် Finance row အသစ်ထပ်မထည့်ဘဲ update လုပ်မည်။ |
| Authenticated recovery endpoints | Full member/password backup, Finance, Payments နှင့် duplicate check သည် `JACC_SERVER_KEY` မရှိလျှင် မဖွင့်ပါ။ |
| Duplicate UserID diagnostics | Duplicate row ရှိလျှင် admin ကို row number နှင့် သတိပေးမည်။ |
| Weekly backup expansion | Drive backup သည် Members recovery, Finance, Payments အားလုံးကို သိမ်းမည်။ |

**Members sheet A–I column အဓိပ္ပါယ်များကို မပြောင်းထားပါ။** UserID, Username, Start, Expire, Status, CancelCount, Password, Package, Token အတိုင်း ဆက်ထားပါသည်။

## 4. Production Deploy လုပ်ရန် အဆင့်များ

### အဆင့် A — Apps Script ပြင်ဆင်ခြင်း

1. Attached `Code.gs` ကို Google Apps Script project ထဲရှိ လက်ရှိ `Code.gs` နှင့် နှိုင်းယှဉ်ပါ။
2. Current live Sheet backup ပြီးထားကြောင်း အတည်ပြုပြီးမှ code ကို update လုပ်ပါ။
3. Apps Script **Project Settings → Script properties** ထဲတွင် `JACC_SERVER_KEY` ရှိ/မရှိ စစ်ပါ။ Value ကို မည်သူ့ထံ မပို့ပါနှင့်။ Railway ရှိ `SHEET_SERVER_KEY` နှင့် တူရမည်။
4. `Deploy → Manage deployments → Web app → Edit → New version → Deploy` လုပ်ပါ။ ရှိပြီးသား Execute as / Who has access setting မပြောင်းပါနှင့်။
5. Apps Script execution မှာ syntax/error မရှိကြောင်း စစ်ပါ။ `monthlyPasswordReset` trigger ရှိနေသေးလည်း အခု function က no-op ဖြစ်သောကြောင့် Premium Password မပြောင်းတော့ပါ။

### အဆင့် B — PR နှင့် Railway

1. Apps Script deploy အောင်မြင်ပြီးမှ PR #53 ကို review လုပ်ပါ။
2. PR merge ပြီးလျှင် Railway ကို redeploy ဖြစ်/မဖြစ် စစ်ပါ။
3. Railway Variables ထဲတွင် `SHEET_WEBHOOK` နှင့် `SHEET_SERVER_KEY` သည် quote, space, newline မပါဘဲ ရှိရမည်။ Secret တန်ဖိုးကို log သို့ screenshot မထည့်ပါနှင့်။
4. Railway Deploy Logs တွင် bot process start အောင်မြင်ပြီး webhook URL error မရှိကြောင်း စစ်ပါ။

## 5. Deployment ပြီးနောက် Functional Test Checklist

| စမ်းသပ်မှု | အောင်မြင်ရမည့်အချက် |
|---|---|
| `/backup` | Admin DM ထဲတွင် Members Recovery, Finance, Payments CSV သုံးခုနှင့် duplicate result ရမည်။ Recovery CSV တွင် Password ပါနိုင်သောကြောင့် private သိမ်းပါ။ |
| New Standard payment | `Confirm → Yes — Approve` ကို တစ်ကြိမ်သာနှိပ်ပြီး Members row တွင် ACTIVE နှင့် CH ဖြစ်ရမည်။ |
| New Premium payment | Members row တွင် ACTIVE, WEB, Password ရှိပြီး member သည် website login လုပ်နိုင်ရမည်။ |
| Premium renewal | UserID row အသစ်မဖန်တီးဘဲ existing row ၏ expiry တိုးရမည်။ Password အဟောင်းမပြောင်းရ။ |
| Same approval retry | တူညီသော payment ကို ထပ်နှိပ်လျှင် expiry နှစ်ကြိမ်မတိုးရ။ |
| Payment record | `Finance` တွင် transaction/reference တစ်ကြောင်းသာရှိရမည်။ `Payments` sheet record မပျောက်ရ။ |
| Website | Premium member login, page load, car data load အောင်မြင်ရမည်။ |
| Telegram channel | Premium နှင့် Standard member နှစ်မျိုးစလုံး၏ channel access ကို စစ်ရမည်။ |

## 6. မလုပ်ရမည့်အချက်များ

`Yes — Approve` ကို တူညီသော payment အတွက် ဆက်တိုက်မနှိပ်ပါနှင့်။ Error ပြလျှင် Members row နှင့် Finance/Payments record ကို အရင်စစ်ပါ။ Members sheet ကို row တိုက်ရိုက်ဖျက်ခြင်း သို့မဟုတ် A–I column များကို ရွှေ့ခြင်း မလုပ်ပါနှင့်။ Premium Password ကို group/channel ထဲ မပို့ပါနှင့်။

## 7. Recovery Evidence

Live read-only backup ကို sandbox ထဲတွင် အောက်ပါ directory သို့ သိမ်းထားပါသည်။

```text
/home/ubuntu/jacc-backups/live-20260816T101511Z/
```

အဲဒီ directory ထဲတွင် `Members.json`, `Finance.json`, `Payments.json`, `Members_Backup_20260716_pre_package_fix.json`, နှင့် `SHA256SUMS.txt` ပါပါသည်။ Password ပါနိုင်သည့် raw backup ကို public repository သို့ မတင်ရ၊ Telegram group ထဲ မပို့ရပါ။

Source backup နှင့် checksum များလည်း `/home/ubuntu/jacc-backups/` ထဲတွင် သိမ်းထားပါသည်။

> **Final gate:** Apps Script version အသစ်ကို deploy မလုပ်မချင်း PR ကို production merge မလုပ်သင့်ပါ။ Apps Script deploy, Railway deploy, နှင့် functional test သုံးခုစလုံးအောင်မြင်ပြီးမှ “fully fixed” ဟု သတ်မှတ်ပါ။
