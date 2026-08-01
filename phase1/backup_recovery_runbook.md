# JACC Backup & Recovery Runbook

ဒီစာတမ်းက ဆုံးဖြတ်ချက် (၃၁) ကို လက်တွေ့အသုံးချရန် Operational Runbook ဖြစ်ပါတယ်။ Code ထည့်ထားတာနဲ့ Backup ပြီးမြောက်တယ်လို့ မယူရပါ။ Supabase Project၊ Private Storage နဲ့ Railway Services ကို တကယ်ချိတ်ပြီး Schedule စမ်းသပ်ရပါမယ်။

## Pilot Recovery Targets

- **Database RPO:** အများဆုံး 24 နာရီ data loss window
- **Message Queue RPO:** Database transaction အောင်မြင်ပြီးသော message အတွက် near-zero
- **Critical Service RTO:** 4 နာရီအတွင်း Bot/Worker ပြန်လည်လည်ပတ်နိုင်ရန်
- **Monthly Restore Test:** အနည်းဆုံး တစ်လတစ်ကြိမ်

RPO ဆိုတာ Backup ပြန်ယူရာမှာ ဘယ်လောက်နောက်ဆုံး data ဆုံးရှုံးနိုင်သလဲဆိုတာပါ။ RTO ဆိုတာ Service ကို ပြန်တက်အောင်လုပ်ဖို့ ရည်မှန်းချိန်ပါ။

## 1. မဖြစ်မနေ Backup လုပ်ရမည့် Data

- PostgreSQL database
- Supabase Private Storage ထဲက Vehicle Photo Sets
- Customer identity documents
- Payment slips နှင့် financial evidence
- Price approvals
- Complaints နှင့် dispute evidence
- Environment variable names/configuration checklist (secret values မဟုတ်)

GitHub ကို Customer Data၊ Database Dump၊ Photo Evidence သို့ Secret Backup အဖြစ် မသုံးရပါ။

## 2. Database Backup

1. ရွေးချယ်ထားသော Supabase plan တွင် ရရှိနိုင်သော managed database backup ကို enable လုပ်ပါ။
2. Backup schedule ကို နေ့စဉ်ဖြစ်အောင်ထားပါ။
3. အပတ်စဉ် encrypted database export တစ်ခုကို Supabase project အပြင်ဘက်ရှိ private object storage သို့ သိမ်းပါ။
4. Backup တစ်ခုချင်းစီအတွက် `jacc_backup_runs` တွင် အောက်ပါအချက်များမှတ်ပါ။
   - backup type
   - start/completion time
   - status
   - storage location reference
   - SHA-256 checksum
   - size
   - retention date
5. Database URL၊ service role key နှင့် encryption key ကို GitHub ထဲမတင်ရပါ။

## 3. Storage Backup

Database row ရှိတာနဲ့ Photo File ရှိမယ်လို့ မယူရပါ။ Storage export မှာ—

- Request ID
- Vehicle/Photo Set ID
- Object path
- Object version
- File size
- Checksum

ပါဝင်သော manifest ထုတ်ပါ။ Restore test မှာ manifest နဲ့ object အမှန်တကယ်ရှိမှုကို နှိုင်းယှဉ်ပါ။

## 4. Message Recovery

`006_reliability_and_recovery.sql` က message များကို `jacc_message_outbox` ထဲမှာ အရင်သိမ်းပါတယ်။

Delivery flow:

```text
QUEUED
  ↓ claim with row lock
PROCESSING
  ├─ success → SENT
  └─ failure → 5m → 15m → 1h → 6h retries
                         └─ max attempts → DEAD_LETTER
```

Railway restart ဖြစ်ပြီး `PROCESSING` မှာ message ပိတ်မိရင် `jacc_recover_stuck_outbox()` က ပြန်လွှတ်ပေးပါတယ်။

`DEAD_LETTER` ဖြစ်သွားရင် Admin Alert ပို့ပြီး Message ကို အလိုအလျောက်ဖျက်မထားရပါ။ Error ကိုစစ်၊ configuration ပြင်ပြီးမှ manual retry လုပ်ရပါမယ်။

## 5. Railway Services

Production pilot မှာ Railway Process နှစ်ခုခွဲထားပါ။

1. `phase1_worker.py` — offers, capacity, 48-hour reassignment
2. `recovery_worker.py` — message delivery, retries, stuck-job recovery

Process တစ်ခုကျသွားလို့ အခြား Process မရပ်သင့်ပါ။ Health check နှင့် restart policy enable လုပ်ပါ။

## 6. Monthly Restore Test

Production database ပေါ်မှာ Restore Test မလုပ်ရပါ။ သီးခြား Test Project/Database သုံးပါ။

လစဉ် လုပ်ဆောင်ချက်:

1. နောက်ဆုံး Successful Backup တစ်ခုရွေးပါ။
2. Test database သို့ restore လုပ်ပါ။
3. Sample Request အနည်းဆုံး 3 ခုဖွင့်စစ်ပါ။
4. Assignment, status history, messages, approvals, payments, complaints ကိုစစ်ပါ။
5. Photo Set အနည်းဆုံး 3 စုနှင့် object checksum စစ်ပါ။
6. Audit Log ကို update/delete မလုပ်နိုင်ကြောင်း စစ်ပါ။
7. Railway worker ကို restart လုပ်ပြီး pending queue ဆက်လည်ကြောင်း စစ်ပါ။
8. Result ကို `jacc_restore_tests` table တွင် မှတ်တမ်းတင်ပါ။

Restore မအောင်မြင်ရင် Backup ကို `verified` မလုပ်ရပါ။ ပြဿနာပြင်ပြီး ထပ်စမ်းရပါမယ်။

## 7. Incident Recovery Order

Service ပျက်သွားရင် အောက်ပါအစဉ်သုံးပါ။

1. Customer Payment/Bid လုပ်ဆောင်မှုကို ခဏရပ်ပါ။
2. လက်ရှိ Database ကို read-only snapshot/backup ယူပါ။
3. Incident စတင်ချိန်နှင့် ထိခိုက်သည့် services ကိုမှတ်ပါ။
4. Database health ကိုစစ်ပါ။
5. Railway workers ကိုစစ်ပြီး failed deployment ကို rollback လုပ်ပါ။
6. Message queue တွင် duplicate delivery မဖြစ်စေရန် dedupe keys စစ်ပါ။
7. Restore လိုအပ်ပါက production မဟုတ်သော environment မှာ backup ကိုအရင် verify လုပ်ပါ။
8. Restore ပြီးနောက် request count၊ payment totals၊ approval count နဲ့ photo manifests နှိုင်းယှဉ်ပါ။
9. Service ပြန်ဖွင့်ပြီး affected customers ကို Official JACC Message ပို့ပါ။
10. Incident report နဲ့ corrective action ကို Audit Log/operational record ထဲသိမ်းပါ။

## 8. Retention

- Completed transaction, payment, approval, complaint: 5 years
- Audit logs: minimum 5 years and append-only
- Active dispute: case ပိတ်ပြီးနောက် 5 years
- Rejected vehicle originals: 90 days
- Rejected vehicle compressed images: 1 year
- Incomplete draft uploads: 30 days

Retention job က hard delete မလုပ်ခင် legal/payment/dispute hold ရှိမရှိ မဖြစ်မနေစစ်ရပါမယ်။ Pilot မှာ automatic permanent deletion ကို မဖွင့်သေးဘဲ Admin-reviewed archive နဲ့စတင်ပါ။

## 9. Go-Live Checklist

- [ ] Supabase project created
- [ ] SQL migrations 001–006 run successfully
- [ ] Managed backup enabled
- [ ] External encrypted backup destination configured
- [ ] Storage export/manifest process configured
- [ ] Railway assignment worker running
- [ ] Railway recovery worker running
- [ ] Dead-letter Admin alert tested
- [ ] Railway restart recovery tested
- [ ] Test restore completed and recorded
- [ ] Secrets confirmed absent from GitHub

ဒီ checklist မပြီးမချင်း Backup/Recovery ကို Production Ready လို့မသတ်မှတ်ရပါ။
