# JACC Phase 1 Starter

## ရည်ရွယ်ချက်

JACC Broker Service ရဲ့ ပထမဆုံး production foundation ဖြစ်ပါတယ်။ ဒီ Phase မှာ အောက်ပါ flow ကို database-backed အဖြစ်တည်ဆောက်ထားပါတယ်။

1. Customer က `AUCTION` သို့ `OUTSIDE_CAR` Request တင်မယ်။
2. System က Eligible Broker ကို Fair Rotation နဲ့ တစ်ယောက်ချင်း Offer ပို့မယ်။
3. Broker တစ်ယောက်စီမှာ ၁၀ မိနစ် Accept/Decline အချိန်ရှိမယ်။
4. Accept လုပ်တာကို PostgreSQL transaction နဲ့ Lock လုပ်မယ်။
5. Broker တစ်ယောက်မှာ Auction ၁ ခု + Outside Car ၁ ခုသာ Active ဖြစ်နိုင်မယ်။
6. Premium Member က App Channel၊ Standard Member က Telegram Channel သုံးမယ်။ Standard Member အတွက် Supabase Auth login မလိုဘဲ Telegram ID ချိတ်ထားသော Central Profile ကို backend က အသုံးပြုမယ်။
7. Broker နှင့် Admin က Central Database တစ်ခုတည်းကို သုံးမယ်။

## လက်ရှိ Code ထဲက ပြင်ရမည့် အဓိကအချက်များ

လက်ရှိ Telegram Bot မှာ Request ကို Eligible Broker အားလုံးဆီ တစ်ပြိုင်တည်းပို့နေပါတယ်။ Phase 1 မှာ အဲဒီ broadcast loop ကို ဖြုတ်ပြီး `jacc_dispatch_next_offer()` RPC ကို ခေါ်ရမယ်။

လက်ရှိ `proxy_sessions`၊ `active_timers` တွေက Python memory ထဲမှာရှိတာကြောင့် Railway restart ဖြစ်ရင် Active Assignment/Timer ပျောက်နိုင်ပါတယ်။ Phase 1 မှာ Assignment, Offer, Status History ကို PostgreSQL ထဲသိမ်းထားပါတယ်။

လက်ရှိ Timer က ၄ နာရီစောင့်ပြီး နောက်ထပ် ၂၀ နာရီစောင့်တာဖြစ်လို့ စုစုပေါင်း ၂၄ နာရီသာရှိပေမဲ့ Message မှာ ၄၈ နာရီလို့ရေးထားပါတယ်။ Phase 1 မှာ Database timestamp နဲ့ ၄၈ နာရီကို တိတိကျကျတွက်ရမယ်။

## Folder ထဲက Files

- `sql/001_core.sql` မှ `sql/005_rls_and_permissions.sql` — Supabase/PostgreSQL schema, constraints, indexes, RLS helpers, transactional RPC functions
- `phase1_client.py` — Railway Bot/App Backend ကနေ Supabase RPC ခေါ်ရန် Async Python client
- `phase1_worker.py` — Expired 10-minute offers နှင့် 48-hour stale assignments ကို စစ်ဆေးမည့် Railway worker
- `integration_patch_guide.md` — လက်ရှိ Bot code ထဲ ဘယ် function ကို ဘယ်လိုပြောင်းရမလဲ
- `tests/test_phase1_policy.py` — Capacity နှင့် Fair Rotation policy logic tests
- `.env.example` — Railway environment variables sample

## Deployment အစဉ်

1. Supabase project အသစ်ဖွင့်ပါ။
2. SQL Editor မှာ `sql/` folder ထဲက migration files ကို filename အစဉ်အတိုင်း run ပါ။
3. Customer/Broker test accounts ထည့်ပါ။
4. Railway မှာ `.env.example` ထဲက variables ထည့်ပါ။
5. `phase1_worker.py` ကို worker service အဖြစ် run ပါ။
6. Telegram Bot ရဲ့ `submit_request`, Accept/Decline callbacks ကို `phase1_client.py` သုံးအောင်ပြောင်းပါ။
7. Request တစ်ခုနဲ့ Broker ၂–၃ ယောက်ကို Pilot စမ်းပါ။

## ပထမ Coding Milestone

အောက်ပါ flow အလုပ်လုပ်တာကို အရင်အတည်ပြုပါ။

```text
Customer Request Created
        ↓
Request = WAITING_BROKER
        ↓
Broker A Offer (10 minutes)
        ├─ Accept → ASSIGNED
        ├─ Decline → Broker B Offer
        └─ Expire  → Broker B Offer
```

Chat၊ Deposit၊ Price Approval၊ Complaint၊ Commission ကို Assignment Flow တည်ငြိမ်ပြီးမှ ဆက်ထည့်ပါ။

## Security

- Frontend/Flutter/HTML ထဲမှာ Supabase `service_role` key မထည့်ရပါ။
- `service_role` key ကို Railway server/worker မှာပဲသုံးပါ။
- Browser/App မှာ `anon` key + RLS ကိုပဲသုံးပါ။
- Accept operation ကို frontend logic နဲ့မယုံဘဲ `jacc_accept_offer()` transaction ကသာဆုံးဖြတ်မယ်။
