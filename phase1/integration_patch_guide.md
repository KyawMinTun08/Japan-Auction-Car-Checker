# JACC Phase 1 Integration Patch Guide

ဒီ Guide က လက်ရှိ `bot (31) (6).py` ကို တန်းဖျက်မပစ်ဘဲ Phase 1 Database System ဆီ တဖြည်းဖြည်းရွှေ့ရန်ဖြစ်ပါတယ်။

## 1. Environment Variables

Railway မှာ ထည့်ရန်—

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
PHASE1_POLL_SECONDS=30
```

`SUPABASE_SERVICE_ROLE_KEY` ကို HTML, GitHub Pages, Flutter App ထဲ မထည့်ရပါ။

## 2. Bot Import

Bot file ရဲ့ import အပိုင်းမှာ—

```python
from phase1_client import JaccPhase1Client, JaccPhase1Error
```

ထည့်ပါ။

Startup အပိုင်းမှာ—

```python
phase1 = JaccPhase1Client(
    supabase_url=os.environ["SUPABASE_URL"],
    service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)
```

## 3. `submit_request()` ကို ပြောင်းရန်

လက်ရှိ code က—

- Google Sheet မှာ Request သိမ်းတယ်
- `get_brokers()` ယူတယ်
- Eligible Broker အားလုံးကို loop ပတ်ပြီး message ပို့တယ်

Phase 1 မှာ—

1. Request ကို Supabase `jacc_service_requests` ထဲသိမ်းပါ။
2. `phase1.dispatch_next_offer(request_uuid)` တစ်ခါပဲခေါ်ပါ။
3. ပြန်လာတဲ့ Broker တစ်ယောက်ကိုပဲ ၁၀ မိနစ် Offer ပို့ပါ။
4. Eligible Broker မရှိရင် Customer ကို Waiting Queue message ပြပါ။

Broadcast loop ကို ဖျက်ရမယ်။

## 4. Accept Callback ကို ပြောင်းရန်

လက်ရှိ `breq_accept_...` callback က—

- Sheet Request ကို `MATCHED` ပြောင်းတယ်
- `proxy_sessions` memory ထဲ session ထည့်တယ်
- Broker status ကို Python logic နဲ့ပြောင်းတယ်

Phase 1 မှာ—

```python
try:
    assignment = await phase1.accept_offer(
        offer_id=offer_id,
        broker_id=broker_user_uuid,
    )
except JaccPhase1Error as exc:
    # OFFER_EXPIRED / REQUEST_ALREADY_ASSIGNED / CAPACITY_FULL
    await query.answer(str(exc), show_alert=True)
    return
```

`jacc_accept_offer()` က transaction lock နဲ့—

- Offer သက်တမ်းစစ်
- Request already assigned စစ်
- Auction/Outside slot capacity စစ်
- Assignment ဖန်တီး
- Request status update

အားလုံးကို တစ်ကြိမ်တည်းလုပ်မယ်။

## 5. Decline Callback ကို ပြောင်းရန်

```python
request_id = await phase1.decline_offer(
    offer_id=offer_id,
    broker_id=broker_user_uuid,
    reason="NOT_AVAILABLE",
)
next_offer = await phase1.dispatch_next_offer(request_id)
```

Decline လုပ်တာနဲ့ နောက် Broker တစ်ယောက်ဆီပို့မယ်။

## 6. `proxy_sessions` ကို Phase-out လုပ်ရန်

ပထမ Milestone မှာ Chat ကို မပြောင်းသေးနိုင်လို့ `proxy_sessions` ကို ခဏသုံးနိုင်တယ်။ ဒါပေမဲ့ Assignment Source of Truth က Supabase ဖြစ်ရမယ်။

- Bot restart ပြီးရင် Active Assignments ကို Supabase ကနေပြန် load လုပ်ပါ။
- `proxy_sessions` ကို cache အဖြစ်သာသုံးပါ။
- နောက် Phase မှာ `conversations/messages` table ဆီပြောင်းပါ။

## 7. 48-Hour Timer ကို ပြောင်းရန်

လက်ရှိ `asyncio.sleep()` timer ကို Source of Truth မလုပ်ရပါ။ Railway restart ဖြစ်ရင် timer ပျောက်နိုင်တယ်။

Phase 1 worker က—

- `last_meaningful_update_at`
- active assignment time

ကို Database မှာစစ်ပြီး ၄၈ နာရီပြည့်မှ Reassign လုပ်မယ်။

Broker က meaningful update ပေးတိုင်း—

```python
await phase1.record_meaningful_update(
    request_id=request_uuid,
    actor_id=broker_user_uuid,
    update_type="BROKER_PROGRESS",
    content={"message": "ကား ၂ စီးစစ်ပြီး condition မကိုက်သေး"},
)
```

ခေါ်ပါ။

## 8. Google Sheets Migration Strategy

Pilot အစမှာ Google Sheets ကို ချက်ချင်းမဖျက်ပါနှင့်။

- Members Sheet → Membership source အဖြစ် ခဏဆက်သုံး
- Brokers/Requests → Supabase ကို Source of Truth ပြောင်း
- Google Sheet ကို Daily Export/Backup အဖြစ်ထား

## 9. Premium vs Standard Routing

- Premium Customer Request → `service_channel = app`
- Standard Customer Request → `service_channel = telegram`

Request/Assignment က Central Database တစ်ခုတည်းထဲမှာရှိမယ်။ Broker အတွက် Channel က Assignment rule ကို မပြောင်းရပါ။

## 10. Pilot Acceptance Tests

1. Broker A အား Auction Active ရှိနေချိန် Auction Offer အသစ်မရ။
2. Broker A မှာ Auction Active ရှိပေမဲ့ Outside Offer ရနိုင်။
3. Offer ၁၀ မိနစ်ကျော်ရင် Accept မရ။
4. Broker A Decline လုပ်ရင် Broker B ဆီသွား။
5. Broker နှစ်ယောက် Accept လုပ်ကြိုးစားရင် တစ်ယောက်ပဲအောင်မြင်။
6. Railway restart လုပ်လည်း Assignment မပျောက်။
7. ၄၈ နာရီ meaningful update မရှိရင် assignment ပြောင်း။
8. Location ကို Assignment filter အဖြစ်မသုံး။
