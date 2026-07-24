# JACC Phase 1 State Flow

## Request States Used in Milestone 1

```text
SUBMITTED
   ↓
WAITING_BROKER
   ↓ dispatch_next_offer
OFFERED
   ├─ Accept  → ASSIGNED
   ├─ Decline → WAITING_BROKER → next broker
   └─ Expire  → WAITING_BROKER → next broker
```

## Assignment Capacity

```text
Broker B001
├─ Auction slot: 0 or 1
└─ Outside slot: 0 or 1
```

Database partial unique index က slot တစ်ခုချင်းစီကို hard-enforce လုပ်မယ်။ UI/Bot က check မလုပ်မိရင်တောင် Database က ဒုတိယ active assignment ကို ပိတ်မယ်။

## Fair Rotation

Broker candidate order—

1. `last_assigned_at IS NULL` — အလုပ်မရဖူးသေးသူဦးစားပေး
2. အရင်ဆုံး assignment ရခဲ့တာ အကြာဆုံး
3. `total_assigned_count` နည်းသူ
4. Stable broker UUID order

Rating ကို Pilot Phase 1 Assignment ထဲ မသုံးသေးပါ။ Data မလုံလောက်သေးတဲ့အချိန် Rating သုံးရင် Broker အသစ်အမြဲနောက်ကျနိုင်ပါတယ်။

## 10-Minute Offer

Offer တစ်ခုမှာ—

- `offered_at`
- `expires_at = offered_at + 10 minutes`
- `status = pending`

ရှိမယ်။ Accept RPC က database clock နဲ့ expiry စစ်မယ်။ ဖုန်းအချိန်ကို မယုံပါ။

## 48-Hour Rule

Meaningful Update ဖြစ်ရမည့်အရာ—

- Customer requirement confirmation
- Car proposal
- Auction sheet/condition result
- Search progress with concrete result
- Next update commitment

Auto-generated “ရှာနေပါတယ်” စာပဲပို့တာကို meaningful update မတွက်သင့်ပါ။ Bot/App က update type ကို structured action အဖြစ်ပို့ရမယ်။
