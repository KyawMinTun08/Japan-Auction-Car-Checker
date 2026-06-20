import asyncio
import os
import re
import random
import string
import logging
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram import BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes

try:
    import pytesseract
    from PIL import Image
    from io import BytesIO
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Environment Variables ──────────────────────────────
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL          = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
TOKEN                 = os.environ.get('BOT_TOKEN', '')
SHEET_WEBHOOK         = os.environ.get('SHEET_WEBHOOK', '')
CHANNEL_ID            = os.environ.get('CHANNEL_ID', '-1003749046571')
ADMIN_IDS             = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip().isdigit()]
ADMIN_USERNAME        = os.environ.get('ADMIN_USERNAME', '')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY    = os.environ.get('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')

# ── Membership Plan Pricing (ks) ──────────────────────
PLAN_CH_1M  = int(os.environ.get('PLAN_CH_1M',  '15000'))
PLAN_CH_2M  = int(os.environ.get('PLAN_CH_2M',  '30000'))
PLAN_CH_3M  = int(os.environ.get('PLAN_CH_3M',  '40000'))
PLAN_CH_5M  = int(os.environ.get('PLAN_CH_5M',  '70000'))
PLAN_WEB_1M = int(os.environ.get('PLAN_WEB_1M', '30000'))
PLAN_WEB_2M = int(os.environ.get('PLAN_WEB_2M', '55000'))
PLAN_WEB_3M = int(os.environ.get('PLAN_WEB_3M', '80000'))
PAYMENT_INFO = os.environ.get('PAYMENT_INFO', 'KPay / Wave: ဆက်သွယ်ရန် @' + ADMIN_USERNAME)

# ── Promo Codes: "CODE:days:maxuses,CODE2:days:maxuses" ──
PROMO_CODES_RAW = os.environ.get('PROMO_CODES', '')

LOC_MAESOT   = "MaeSot Freezone"
LOC_KLANG9   = "Klang9 Freezone"
LOC_BORDER44 = "Best Border-44 Gate"

PLAN_PRICES = {
    "CH":  {1: PLAN_CH_1M,  2: PLAN_CH_2M,  3: PLAN_CH_3M,  5: PLAN_CH_5M},
    "WEB": {1: PLAN_WEB_1M, 2: PLAN_WEB_2M, 3: PLAN_WEB_3M},
}
PLAN_NAMES = {
    "CH":  "📱 Standard",
    "WEB": "💎 Web Premium",
}

CHASSIS_PREFIX_MAP = {
    "VZNY12":"ADVAN",
    "GRS200":"CROWN","GRS201":"CROWN","GRS202":"CROWN","GRS204":"CROWN","GRS210":"CROWN",
    "GWS204":"CROWN HYBRID",
    "ZGE20":"WISH","ZGE21":"WISH","ZGE22":"WISH","ZGE25":"WISH",
    "GRX133":"MARK X",
    "GGH25":"ALPHARD","GGH20":"ALPHARD","MNH15":"ALPHARD","MNH10":"ALPHARD",
    "ANH15":"ALPHARD","ANH20":"ALPHARD",
    "ZRR75G":"NOAH","ZRR75W":"VOXY",
    "ZRR70G":"NOAH","ZRR70W":"VOXY",
    "ZWR80G":"NOAH HYBRID","ZWR80W":"VOXY HYBRID","ZWR80S":"ESQUIRE",
    "ZRR75":"NOAH","ZRR70":"NOAH","ZWR80":"NOAH HYBRID",
    "KDH201":"HIACE VAN","KDH200":"HIACE VAN","KDH205":"HIACE VAN","TRH200":"HIACE VAN",
    "NCP165":"SUCCEED VAN","NCP160":"SUCCEED VAN",
    "NCP59":"SUCCEED WAGON","NCP58":"SUCCEED WAGON",
    "UZJ100":"LAND CRUISER","HDJ101":"LAND CRUISER","HZJ105":"LAND CRUISER",
    "KDN185":"HILUX SURF","KZN185":"HILUX SURF","VZN185":"HILUX SURF",
    "KDJ95":"LAND CRUISER PRADO","KZJ95":"LAND CRUISER PRADO","UZJ101":"LAND CRUISER",
    "USF40":"LEXUS LS","USF41":"LEXUS LS",
    "ACU25":"KLUGER","ACU20":"KLUGER","MCU25":"KLUGER",
    "AZE0":"LEAF",
    "XZC610":"DUTRO","XZU548":"DUTRO TRUCK","XZU300":"DUTRO TRUCK",
    "ACA33":"VANGUARD","ACA38":"VANGUARD","CW4YL":"QUON",
    "NT31":"X-TRAIL","NT32":"X-TRAIL","DNT31":"X-TRAIL","T31":"X-TRAIL",
    "YF15":"JUKE","F15":"JUKE","NF15":"JUKE",
    "SK82TN":"VANETTE TRUCK","SK82VN":"VANETTE TRUCK",
    "GP1":"FIT HYBRID","GP5":"FIT HYBRID","GP6":"FIT HYBRID",
    "GP7":"FIT SHUTTLE HYBRID","GP2":"FIT SHUTTLE HYBRID",
    "GK3":"FIT","GK5":"FIT","GE6":"FIT","GE8":"FIT",
    "GB3":"FREED","GB4":"FREED",
    "RE4":"CRV","RE3":"CRV","RD1":"CRV","RD5":"CRV",
    "ZE2":"INSIGHT","ZE3":"INSIGHT",
    "KE2AW":"CX5","KE2FW":"CX5","KE5FW":"CX5",
    "SKP2T":"BONGO TRUCK","SLP2L":"BONGO TRUCK",
    "S210P":"HIJET TRUCK","S211P":"HIJET TRUCK","S510P":"HIJET TRUCK",
    "S500P":"HIJET TRUCK","S501P":"HIJET TRUCK",
    "S321V":"HIJET VAN","S331V":"HIJET VAN",
    "S200P":"HIJET TRUCK","S201P":"HIJET TRUCK",
    "S211U":"PIXIS TRUCK","S500U":"PIXIS TRUCK",
    "S510J":"SAMBAR TRUCK","S201J":"SAMBAR TRUCK",
    "FE74BV":"CANTER","FE82BS":"CANTER","FBA30":"CANTER",
    "FE82D":"CANTER","FE82EE":"CANTER","FE72EE":"CANTER",
    "FE84DV":"CANTER","FE83D":"CANTER","FE70B":"CANTER",
    "FE73EB":"CANTER","FE70EB":"CANTER","FEA20":"CANTER",
    "FB70BB":"CANTER GUTS",
    "FK61FM":"FUSO FIGHTER","FQ62F":"FUSO FIGHTER","FK71F":"FUSO FIGHTER",
    "FEA50":"FUSO TRUCK","FBA20":"FUSO TRUCK",
    "FY54JTY":"SUPER GREAT","FS54JZ":"SUPER GREAT",
    "FV50JJX":"SUPER GREAT","FV50MJX":"SUPER GREAT",
    "FC6JLW":"RANGER","FC7JKY":"RANGER",
    "FW1EXW":"PROFIA","SH1EDX":"PROFIA",
    "CG5ZA":"UD","CG5ZE":"UD","CG4ZA":"UD","CG4YA":"UD",
    "CD5ZA":"UD","CD4ZA":"UD","CD48R":"BIG THUMB",
    "MK35A":"CONDOR","MK38L":"CONDOR","MK36A":"CONDOR",
    "MK36B":"UD","MK38C":"UD",
    "JNCMM60C6GU":"UD","JNCMM60G6GU":"UD","GK6XA":"QUON","JNCLSC":"CONDOR",
    "V98W":"PAJERO","V97W":"PAJERO","V93W":"PAJERO","V75W":"PAJERO","V78W":"PAJERO",
    "WVWZZZ":"NEW BEETLE",
    "WWWZZZ":"NEW BEETLE",
    "WVW":"VW",
    "WAU":"AUDI",
    "WBA":"BMW",
    "WBS":"BMW M",
    "WDB":"MERCEDES-BENZ",
    "WDC":"MERCEDES-BENZ",
    "WDD":"MERCEDES-BENZ",
    "SAJ":"JAGUAR",
    "SAL":"LAND ROVER",
    "SAR":"RANGE ROVER",
    "VF1":"RENAULT",
    "ZFA":"FIAT",
    "ZFF":"FERRARI",
    "ZAR":"ALFA ROMEO",
}

CARS = [
    # ── MaeSot Freezone ──
    {"chassis":"MNH15-0039667","model":"ALPHARD","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"CD48R-30111","model":"BIG THUMB","color":"GREEN","year":2005,"loc":"MaeSot"},
    {"chassis":"FE82EEV500266","model":"CANTER","color":"WHITE","year":2002,"loc":"MaeSot"},
    {"chassis":"FE84DV-550674","model":"CANTER","color":"BLUE","year":2008,"loc":"MaeSot"},
    {"chassis":"FB70BB-512392","model":"CANTER GUTS","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"MK35A-10405","model":"CONDOR","color":"PEARL WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"JNCLSC0A1GU006386","model":"CONDOR","color":"WHITE","year":2016,"loc":"MaeSot"},
    {"chassis":"GRS210-6004548","model":"CROWN","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"GRS200-0001831","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"GRS200-0020080","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"GRS202-0002603","model":"CROWN","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"XZC610-0001005","model":"DUTRO","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GE6-1539486","model":"FIT","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GP5-3032237","model":"FIT HYBRID","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1131390","model":"FIT HYBRID","color":"WHITE","year":2012,"loc":"MaeSot"},
    {"chassis":"GP1-1049821","model":"FIT HYBRID","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GP7-1000970","model":"FIT SHUTTLE HYBRID","color":"PEARL WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"GP2-3106770","model":"FIT SHUTTLE HYBRID","color":"SILVER","year":2013,"loc":"MaeSot"},
    {"chassis":"FK61FM765129","model":"FUSO FIGHTER","color":"WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"KDH201-0140123","model":"HIACE VAN","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"S211P-0217418","model":"HIJET TRUCK","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"S210P-2037788","model":"HIJET TRUCK","color":"WHITE","year":2005,"loc":"MaeSot"},
    {"chassis":"S510P-0173458","model":"HIJET TRUCK","color":"WHITE","year":2017,"loc":"MaeSot"},
    {"chassis":"UZJ100-0151432","model":"LAND CRUISER","color":"SILVER","year":2004,"loc":"MaeSot"},
    {"chassis":"USF40-5006069","model":"LEXUS LS","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"WVWZZZ16ZDM638030","model":"NEW BEETLE","color":"BLACK","year":2013,"loc":"MaeSot"},
    {"chassis":"ZRR75-0068964","model":"VOXY","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"V98W-0300140","model":"PAJERO","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"S211U-0000227","model":"PIXIS TRUCK","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"FC7JKY-14910","model":"RANGER","color":"BLUE","year":2011,"loc":"MaeSot"},
    {"chassis":"NCP165-0001505","model":"SUCCEED VAN","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"NCP59-0012188","model":"SUCCEED WAGON","color":"SILVER","year":2005,"loc":"MaeSot"},
    {"chassis":"FV50JJX-530670","model":"SUPER GREAT","color":"BLACK","year":2004,"loc":"MaeSot"},
    {"chassis":"CG5ZA-30374","model":"UD","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"CD5ZA-30191","model":"UD","color":"SILVER","year":2014,"loc":"MaeSot"},
    {"chassis":"CG4ZA-01338","model":"UD","color":"LIGHT BLUE","year":2006,"loc":"MaeSot"},
    {"chassis":"ZGE22-0005423","model":"WISH","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"ZGE20-0010786","model":"WISH","color":"PEARL WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"ZGE25-0015283","model":"WISH","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"NT32-504837","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"MaeSot"},
    {"chassis":"NT32-531693","model":"X-TRAIL","color":"BLACK","year":2015,"loc":"MaeSot"},
    {"chassis":"NT31-316873","model":"X-TRAIL","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"NT32-508661","model":"X-TRAIL","color":"PEARL WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"SKP2T-108324","model":"BONGO TRUCK","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"FE82D-570692","model":"CANTER","color":"WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"FE82D-530430","model":"CANTER","color":"PEARL WHITE","year":2007,"loc":"MaeSot"},
    {"chassis":"FE72EE-500637","model":"CANTER","color":"WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"GRS201-0006860","model":"CROWN","color":"SILVER","year":2011,"loc":"MaeSot"},
    {"chassis":"GRS200-0061216","model":"CROWN","color":"PEARL WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"GRS200-0063933","model":"CROWN","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"GWS204-0025870","model":"CROWN HYBRID","color":"SILVER","year":2012,"loc":"MaeSot"},
    {"chassis":"GK3-1029686","model":"FIT","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1011906","model":"FIT HYBRID","color":"BLUE","year":2010,"loc":"MaeSot"},
    {"chassis":"GP5-3040254","model":"FIT HYBRID","color":"WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GP1-1096649","model":"FIT HYBRID","color":"BLACK","year":2011,"loc":"MaeSot"},
    {"chassis":"GP1-1014176","model":"FIT HYBRID","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"GB3-1312198","model":"FREED","color":"PEARL WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"FQ62F-520185","model":"FUSO FIGHTER","color":"WHITE","year":2008,"loc":"MaeSot"},
    {"chassis":"FEA50-521744","model":"FUSO TRUCK","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"KDH201-0056284","model":"HIACE VAN","color":"WHITE","year":2010,"loc":"MaeSot"},
    {"chassis":"S211P-0276262","model":"HIJET TRUCK","color":"SILVER","year":2014,"loc":"MaeSot"},
    {"chassis":"S510P-0147424","model":"HIJET TRUCK","color":"WHITE","year":2017,"loc":"MaeSot"},
    {"chassis":"S210P-2060815","model":"HIJET TRUCK","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"S510P-0149349","model":"HIJET TRUCK","color":"SILVER","year":2017,"loc":"MaeSot"},
    {"chassis":"S210P-2006882","model":"HIJET TRUCK","color":"SILVER","year":2005,"loc":"MaeSot"},
    {"chassis":"ZE2-1130682","model":"INSIGHT","color":"WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"YF15-033275","model":"JUKE","color":"WHITE","year":2011,"loc":"MaeSot"},
    {"chassis":"HDJ101-0031030","model":"LAND CRUISER","color":"PEARL WHITE","year":2007,"loc":"MaeSot"},
    {"chassis":"AZE0-062459","model":"LEAF","color":"PEARL WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"GRX133-6003681","model":"MARK X","color":"SILVER","year":2013,"loc":"MaeSot"},
    {"chassis":"WVWZZZ16ZDM685003","model":"NEW BEETLE","color":"BLACK","year":2013,"loc":"MaeSot"},
    {"chassis":"NCP165-0001511","model":"SUCCEED VAN","color":"PEARL WHITE","year":2014,"loc":"MaeSot"},
    {"chassis":"GK6XA-10555","model":"QUON","color":"WHITE","year":2013,"loc":"MaeSot"},
    {"chassis":"FC6JLW-10241","model":"RANGER","color":"PEARL WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"FY54JTY530030","model":"SUPER GREAT","color":"PEARL WHITE","year":2003,"loc":"MaeSot"},
    {"chassis":"FS54JZ-570431","model":"SUPER GREAT","color":"BLACK","year":2010,"loc":"MaeSot"},
    {"chassis":"FV50MJX520729","model":"SUPER GREAT","color":"BLACK","year":2001,"loc":"MaeSot"},
    {"chassis":"CG5ZA-01150","model":"UD","color":"GREEN","year":2011,"loc":"MaeSot"},
    {"chassis":"CG5ZE-30138","model":"UD","color":"WHITE","year":2015,"loc":"MaeSot"},
    {"chassis":"MK38L-30952","model":"UD","color":"YELLOW","year":2014,"loc":"MaeSot"},
    {"chassis":"MK36A-12656","model":"UD","color":"WHITE","year":2006,"loc":"MaeSot"},
    {"chassis":"ZGE20-0041580","model":"WISH","color":"PEARL WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"ZGE20-0004342","model":"WISH","color":"WHITE","year":2009,"loc":"MaeSot"},
    {"chassis":"NT32-024640","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"MaeSot"},
    {"chassis":"NT32-037944","model":"X-TRAIL","color":"BLACK","year":2015,"loc":"MaeSot"},
    {"chassis":"NT31-244285","model":"X-TRAIL","color":"PEARL WHITE","year":2012,"loc":"MaeSot"},
    {"chassis":"DNT31-209100","model":"X-TRAIL","color":"WHITE","year":2011,"loc":"MaeSot"},
    # ── Klang9 Freezone ──
    {"chassis":"VZNY12-070391","model":"ADVAN","color":"WHITE","year":2017,"loc":"Klang9"},
    {"chassis":"GGH20-8002412","model":"ALPHARD","color":"PEARL WHITE","year":2008,"loc":"Klang9"},
    {"chassis":"MNH10-0099576","model":"ALPHARD","color":"PEARL WHITE","year":2007,"loc":"Klang9"},
    {"chassis":"SLP2L-102206","model":"BONGO TRUCK","color":"WHITE","year":2017,"loc":"Klang9"},
    {"chassis":"FEA20-520134","model":"CANTER","color":"SILVER","year":2013,"loc":"Klang9"},
    {"chassis":"FE73EB-501814","model":"CANTER","color":"LIGHT GREEN","year":2003,"loc":"Klang9"},
    {"chassis":"FE70EB-506566","model":"CANTER","color":"WHITE","year":2004,"loc":"Klang9"},
    {"chassis":"GRS204-0014299","model":"CROWN","color":"WHITE","year":2010,"loc":"Klang9"},
    {"chassis":"RE4-1006211","model":"CRV","color":"WHITE","year":2006,"loc":"Klang9"},
    {"chassis":"KE2AW-115142","model":"CX5","color":"WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"GP5-3037138","model":"FIT HYBRID","color":"PEARL WHITE","year":2014,"loc":"Klang9"},
    {"chassis":"GP5-3216073","model":"FIT HYBRID","color":"PEARL WHITE","year":2015,"loc":"Klang9"},
    {"chassis":"GB3-1112824","model":"FREED","color":"PEARL WHITE","year":2009,"loc":"Klang9"},
    {"chassis":"FK71F-701985","model":"FUSO FIGHTER","color":"GREEN","year":2007,"loc":"Klang9"},
    {"chassis":"S211P-0042777","model":"HIJET TRUCK","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"S211P-0138980","model":"HIJET TRUCK","color":"WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"KDN185-0001271","model":"HILUX SURF","color":"SILVER","year":2000,"loc":"Klang9"},
    {"chassis":"ZE2-1128237","model":"INSIGHT","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"NF15-060818","model":"JUKE","color":"WHITE","year":2012,"loc":"Klang9"},
    {"chassis":"ACU25-0032701","model":"KLUGER","color":"WHITE","year":2004,"loc":"Klang9"},
    {"chassis":"USF40-5079528","model":"LEXUS LS","color":"PEARL WHITE","year":2008,"loc":"Klang9"},
    {"chassis":"WVWZZZ16ZDM635922","model":"NEW BEETLE","color":"RED","year":2013,"loc":"Klang9"},
    {"chassis":"GK6XA-10291","model":"QUON","color":"GREEN","year":2012,"loc":"Klang9"},
    {"chassis":"CW4YL-30468","model":"QUON","color":"SILVER","year":2009,"loc":"Klang9"},
    {"chassis":"NCP165-0056792","model":"SUCCEED VAN","color":"WHITE","year":2018,"loc":"Klang9"},
    {"chassis":"NCP59-0024963","model":"SUCCEED WAGON","color":"DARK BLUE","year":2012,"loc":"Klang9"},
    {"chassis":"CG5ZA-12819","model":"UD","color":"PEARL WHITE","year":2014,"loc":"Klang9"},
    {"chassis":"CG5ZA-11731","model":"UD","color":"WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"CG4YA-00054","model":"UD","color":"WHITE","year":2006,"loc":"Klang9"},
    {"chassis":"CD4ZA-31233","model":"UD","color":"GREEN","year":2009,"loc":"Klang9"},
    {"chassis":"SK82TN-319474","model":"VANETTE TRUCK","color":"WHITE","year":2005,"loc":"Klang9"},
    {"chassis":"ZRR75-0083512","model":"VOXY","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"ZGE25-0020690","model":"WISH","color":"PEARL WHITE","year":2012,"loc":"Klang9"},
    {"chassis":"ZGE20-0154748","model":"WISH","color":"PEARL WHITE","year":2013,"loc":"Klang9"},
    {"chassis":"ZGE20-0152288","model":"WISH","color":"BLACK","year":2012,"loc":"Klang9"},
    {"chassis":"NT32-036496","model":"X-TRAIL","color":"BLACK","year":2014,"loc":"Klang9"},
    {"chassis":"NT31-212796","model":"X-TRAIL","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"NT31-049247","model":"X-TRAIL","color":"BLACK","year":2009,"loc":"Klang9"},
    {"chassis":"DNT31-205472","model":"X-TRAIL","color":"PEARL WHITE","year":2011,"loc":"Klang9"},
    {"chassis":"NT32-038921","model":"X-TRAIL","color":"PEARL WHITE","year":2015,"loc":"Klang9"},
]

PRICE_HISTORY  = []
pending_photo  = {}
pending_payment = {}   # user_id -> {package, months, amount, username, name}
pending_updateid = {}  # user_id -> {target_username, old_id, new_id}
pending_edit     = {}  # user_id -> {chassis, field}
pending_broadcast= {}  # user_id -> {pkg_filter, waiting_photo}
pending_request  = {}  # user_id -> {step, data}
proxy_sessions   = {}  # session_id -> {customerId, brokerId, reqId, status}
pending_rating   = {}  # customer_id -> {reqId, brokerId, brokerTgId}
pending_deposit  = {}  # customer_id -> {reqId, brokerTgId, step, slip_info}
active_timers    = {}  # req_id -> asyncio.Task
nodep_pending = {}  # req_id -> {customerId, brokerTgId, brokerId}
warned_3days   = set()
promo_used     = {}
rate_limit     = {}
pending_setqr    = {}  # admin_id -> "kpay" / "wave" / "cb"
payment_qr_cache = {}  # method -> {"file_id": str, "ts": datetime}

# ── NEW: Broker pending target (dual-session routing) ──
pending_broker_target = {}  # broker_tg_id -> {text, is_photo, file_bytes, caption, sessions}

# ── Rate Limiting ──────────────────────────────────────
def check_rate_limit(user_id: int, max_req: int = 10, window: int = 60) -> bool:
    now = datetime.now()
    if user_id not in rate_limit:
        rate_limit[user_id] = []
    rate_limit[user_id] = [t for t in rate_limit[user_id]
                           if (now - t).total_seconds() < window]
    if len(rate_limit[user_id]) >= max_req:
        return False
    rate_limit[user_id].append(now)
    return True

# ── Password Generator ─────────────────────────────────
async def is_active_member(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10)
        members = resp.json().get("members", [])
        for m in members:
            if str(m.get("userId","")) == str(user_id):
                return m.get("status","") == "ACTIVE"
    except:
        pass
    return False

# ── 10 Day Promo Helpers ──────────────────────────────
async def get_cancel_count(str_uid: str) -> int:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getCancelCount", "userId": str_uid,
            }, timeout=10)
        return resp.json().get("cancelCount", 0)
    except:
        return 0

async def check_promo10d_eligibility(str_uid: str) -> dict:
    """Returns {eligible, reason, active, carreq_count}"""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={"action":"getMembers"}, timeout=10)
        members = resp.json().get("members", [])
        for m in members:
            if str(m.get("userId","")) == str_uid:
                pkg    = str(m.get("package","")).upper()
                status = str(m.get("status","")).upper()
                if pkg == "PROMO10D":
                    if status == "ACTIVE":
                        return {"eligible": True, "active": True, "reason": ""}
                    if status in ("KICKED", "EXPIRED"):
                        return {"eligible": False, "active": False,
                                "reason": "10 Day Promo သုံးပြီး Order မတင်ခဲ့သောကြောင့် ထပ်မရနိုင်ပါ"}
    except Exception as e:
        logger.error(f"check_promo10d: {e}")

    # Cancel count check
    cancel_count = await get_cancel_count(str_uid)
    if cancel_count >= 2:
        return {"eligible": False, "active": False,
                "reason": "Cancel ၂ ကြိမ်နှင့်အထက် ရှိသောကြောင့် 10 Day Promo မရနိုင်ပါ"}

    return {"eligible": True, "active": False, "reason": ""}

async def activate_promo10d(context, user_id: int, username: str) -> bool:
    """Save PROMO10D member to sheet"""
    now        = datetime.now()
    start_date = now.strftime("%d/%m/%Y")
    expire_date= (now + timedelta(days=10)).strftime("%d/%m/%Y")
    password   = generate_password()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":     "saveMember",
                "userId":     str(user_id),
                "username":   username,
                "startDate":  start_date,
                "expireDate": expire_date,
                "status":     "ACTIVE",
                "password":   password,
                "package":    "PROMO10D",
            }, timeout=10)
        return resp.json().get("status") == "ok"
    except Exception as e:
        logger.error(f"activate_promo10d: {e}")
        return False

def generate_password() -> str:
    letters = random.choices(string.ascii_uppercase, k=5)
    digits  = random.choices(string.digits, k=5)
    mixed   = [letters[0], digits[0], letters[1], digits[1], letters[2],
               digits[2], letters[3], digits[3], letters[4], digits[4]]
    return "KMT-" + "".join(mixed[:6]) + "-" + "".join(mixed[6:])

# ── Helpers ───────────────────────────────────────────
# ── Tracking Buttons ──────────────────────────────────
TRACKING_LABELS = {
    "A": [
        ("🔍 ကားကြည့်နေဆဲ",      "searching"),
        ("🔎 ကားစစ်ဆေးနေဆဲ",    "checking"),
        ("🚗 ကားရပြီ",            "found"),
        ("🏷️ Auction တင်ပြီ",    "bidding"),
        ("⏳ ရလဒ်စောင့်စားပါ",   "waiting"),
        ("🏆 Auction Win",        "win"),
        ("❌ Auction Loss",        "loss"),
    ],
    "R": [
        ("🔍 ကားရှာနေဆဲ",        "searching"),
        ("🚗 ကားရပြီ",            "found"),
        ("✅ ကားအဆင်ပြေပြီ",     "ok"),
    ],
}

TRACKING_NOTI = {
    "searching": "🔍 Broker သည် ကားရှာနေဆဲ ဖြစ်ပါသည်",
    "checking":  "🔎 Broker သည် ကားစစ်ဆေးနေဆဲ ဖြစ်ပါသည်",
    "found":     "🚗 ကားတွေ့ပြီ — အသေးစိတ် ဆက်လာမည်",
    "bidding":   "🏷️ Auction တင်ပြီ — ရလဒ် စောင့်ပါ",
    "waiting":   "⏳ Auction ရလဒ် စောင့်နေဆဲ ဖြစ်ပါသည်",
    "win":       "🏆 Auction Win! ကားရပြီ — Broker ဆက်သွယ်ပေးမည်",
    "loss":      "❌ Auction Loss — Broker မှ နောက်ထပ် ဆက်သွယ်ပေးမည်",
    "ok":        "✅ ကားအဆင်ပြေပြီ — Broker ဆက်သွယ်ပေးမည်",
}

def get_tracking_keyboard(svc_type: str, req_id: str) -> InlineKeyboardMarkup:
    t = "A" if svc_type == "auction" else "R"
    buttons = []
    row = []
    for label, key in TRACKING_LABELS[t]:
        row.append(InlineKeyboardButton(label, callback_data=f"track_{t}_{key}_{req_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def loc_display(loc_key: str) -> str:
    if loc_key == "Klang9": return LOC_KLANG9
    if loc_key in ("Border44","Best Border","44Gate","44gate"): return LOC_BORDER44
    return LOC_MAESOT

async def get_member_package(user_id: int) -> str | None:
    if user_id in ADMIN_IDS:
        return "WEB"
    try:
        sheet_id = os.environ.get('SHEET_ID', '')
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json&sheet=Members&_={int(datetime.now().timestamp())}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
        text = resp.text
        import json as _json
        raw  = _json.loads(text[text.index('{'):text.rindex('}')+1])
        rows = raw.get('table', {}).get('rows', [])
        now  = datetime.now()
        for row in rows:
            c = row.get('c', [])
            if not c: continue
            uid_cell    = c[0] if len(c) > 0 else None
            expire_cell = c[3] if len(c) > 3 else None
            status_cell = c[4] if len(c) > 4 else None
            pkg_cell    = c[6] if len(c) > 6 else None
            if not uid_cell: continue
            uid_val = uid_cell.get('f') or str(uid_cell.get('v',''))
            uid_val = uid_val.replace('.0','').strip()
            if uid_val != str(user_id): continue
            status = (status_cell.get('v','') if status_cell else '').upper()
            expire_str = (expire_cell.get('f','') if expire_cell else '')
            try:
                ep = expire_str.split('/')
                expire_date = datetime(int(ep[2]), int(ep[1]), int(ep[0]))
            except:
                expire_date = datetime(2000,1,1)
            if status == 'ACTIVE' and expire_date >= now:
                pkg = (pkg_cell.get('v','CH') if pkg_cell else 'CH') or 'CH'
                pkg = str(pkg).upper()
                if pkg == 'CH-PROMO': return 'CH'
                return pkg
            return None
        return None
    except Exception as e:
        logger.error(f"get_member_package: {e}")
        return None

def decode_vin_year(vin: str) -> int:
    VIN_YEAR_MODERN = {
        'A':2010,'B':2011,'C':2012,'D':2013,'E':2014,'F':2015,'G':2016,
        'H':2017,'J':2018,'K':2019,'L':2020,'M':2021,'N':2022,'P':2023,
        'R':2024,'S':2025,'T':2026,
        '1':2001,'2':2002,'3':2003,'4':2004,'5':2005,'6':2006,'7':2007,
        '8':2008,'9':2009,
    }
    try:
        if len(vin) >= 10:
            char = vin[9].upper()
            return VIN_YEAR_MODERN.get(char, 0)
    except:
        pass
    return 0

def is_european_vin(chassis: str) -> bool:
    c = chassis.upper().replace("-","").replace(" ","")
    if len(c) == 17 and c[:1] in ("W","S","V","Z","X","T"):
        return True
    return False

def guess_model_from_chassis(chassis_input: str) -> str:
    cu = chassis_input.upper().strip()
    for prefix in sorted(CHASSIS_PREFIX_MAP.keys(), key=len, reverse=True):
        if cu.startswith(prefix):
            return CHASSIS_PREFIX_MAP[prefix]
    return "UNKNOWN"

async def guess_model_gemini(chassis_input: str) -> str:
    if not GEMINI_API_KEY:
        return "UNKNOWN"
    try:
        if is_european_vin(chassis_input):
            vin_yr = decode_vin_year(chassis_input)
            yr_hint = f" Year hint from VIN: {vin_yr}." if vin_yr else ""
            prompt = f"This is a European VIN: {chassis_input}.{yr_hint} What car brand and model is this? Reply ONLY the model name UPPERCASE (e.g. NEW BEETLE, AUDI A4, BMW 3 SERIES). If unknown reply UNKNOWN."
        else:
            prefix  = chassis_input.split("-")[0] if "-" in chassis_input else chassis_input[:6]
            prompt  = f"What Japanese car model has chassis prefix '{prefix}'? Reply ONLY the model name UPPERCASE. If unknown reply UNKNOWN."
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[{"text":prompt}]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
        data = resp.json()
        if "candidates" in data:
            m = data["candidates"][0]["content"]["parts"][0]["text"].strip().upper().split("\n")[0].strip()
            return m if m and m != "UNKNOWN" else "UNKNOWN"
    except Exception as e:
        logger.error(f"Gemini model: {e}")
    return "UNKNOWN"

def find_by_chassis(chassis_input: str):
    c = chassis_input.upper().strip()
    for car in CARS:
        if car["chassis"].upper() == c:
            return car
    return None

def find_by_model(model_input: str):
    m = model_input.upper().strip()
    return [c for c in CARS if m in c["model"].upper()]

def extract_chassis_from_text(text: str):
    text = text.upper().strip()
    vin_matches = re.findall(r'[A-HJ-NPR-Z0-9]{17}', text)
    for v in vin_matches:
        if v[0] in ("W","S","V","Z","X","T"):
            return v
    for pattern in [
        r'[A-Z]{1,5}\d{1,4}[A-Z]{0,2}\d{0,2}-\d{4,7}',
        r'[A-Z]{2,6}\d{2,4}-\d{4,7}',
        r'[A-Z0-9]{4,20}-\d{4,7}',
    ]:
        matches = re.findall(pattern, text)
        if matches:
            return max(matches, key=len)
    return None

def get_price_history(chassis: str):
    return [p for p in PRICE_HISTORY if p["chassis"] == chassis]

def ys(year) -> str:
    return str(year) if year and year != 0 else "—"

def format_car_info(car, price=None, history=None) -> str:
    txt = (
        f"🚗 *{car['model']}* ({ys(car.get('year',0))})\n"
        f"🔑 `{car['chassis']}`\n"
        f"🎨 {car['color']}\n"
        f"📍 {loc_display(car.get('loc','MaeSot'))}\n"
    )
    if price:
        txt += f"💰 ฿{price:,}\n"
    if history:
        txt += f"\n📈 *မှတ်တမ်း ({len(history)} ကြိမ်):*\n"
        for h in history[-5:]:
            txt += f"  • {h['date']} → ฿{h['price']:,}\n"
    txt += f"\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    return txt

async def upload_to_cloudinary(file_bytes: bytes, chassis: str) -> str:
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        return ""
    try:
        import base64, hashlib, time
        ts        = str(int(time.time()))
        public_id = f"auction/{chassis.replace('-','_')}_{ts}"
        sig_str   = f"public_id={public_id}&timestamp={ts}{CLOUDINARY_API_SECRET}"
        signature = hashlib.sha1(sig_str.encode()).hexdigest()
        img_b64   = base64.b64encode(file_bytes).decode()
        url       = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
        payload   = {"file":f"data:image/jpeg;base64,{img_b64}","public_id":public_id,
                     "timestamp":ts,"api_key":CLOUDINARY_API_KEY,"signature":signature}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=payload, timeout=30)
        return resp.json().get("secure_url","")
    except Exception as e:
        logger.error(f"Cloudinary: {e}")
        return ""

async def save_price(chassis, model, color, year, price, user_name, image_url="", location=LOC_MAESOT):
    now   = datetime.now().strftime("%d/%m/%Y")
    entry = {"chassis":chassis,"model":model,"color":color,"year":year,
             "price":price,"date":now,"location":location,
             "added_by":user_name,"image_url":image_url}
    PRICE_HISTORY.append(entry)
    if SHEET_WEBHOOK:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(SHEET_WEBHOOK, json=entry, timeout=10, follow_redirects=True)
        except Exception as e:
            logger.error(f"save_price: {e}")
    return entry

async def post_to_channel(context, chassis, model, color, year, price, image_url="", location=LOC_MAESOT):
    if not CHANNEL_ID:
        return
    text = (
        f"🚗 *ကားသစ်ဝင်ပြီ!*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔑 Chassis : `{chassis}`\n"
        f"🚘 Model   : *{model}*\n"
        f"🎨 Color   : {color or '—'}\n"
        f"📅 Year    : {ys(year)}\n"
        f"💰 Price   : *฿{int(price):,}*\n"
        f"📍 {location}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌐 [Japan Auction Car Checker](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    )
    try:
        if image_url:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=image_url, caption=text, parse_mode='Markdown')
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Channel post: {e}")

async def notify_admins(context, text: str, reply_markup=None):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=text,
                parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Admin notify {admin_id}: {e}")

async def kick_with_retry(context, user_id: int, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            return True
        except Exception as e:
            logger.error(f"Kick attempt {attempt+1} for {user_id}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    return False

# ── Gemini Slip Reader ────────────────────────────────
async def gemini_read_slip(file_bytes: bytes) -> dict:
    if not GEMINI_API_KEY:
        return {}
    try:
        import base64
        img_b64 = base64.b64encode(file_bytes).decode()
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[
            {"text":"""Identify this Myanmar mobile payment slip and extract fields.

HOW TO IDENTIFY:
- Wave Money slip = YELLOW background, "KS" logo with lightning bolt
    * Shows "Transaction ID" + "Date & Time" + "Total" (top amount)
    * "Receive Money" view: has "Sender" field
    * "Send Money" view: has "Receiver" field

- KPay (KBZPay) slip = BLUE background, "KBZ BANK" red logo at top + "KBZPay" blue logo at bottom
    * Shows "Transaction Time" + "Transaction No." + "Transfer To" + "Amount" (top large number)
    * "Transfer To" = the person who RECEIVED the money (e.g. admin name)
    * Sender name NOT shown on this slip type

- CB Bank slip = GREEN background, "CB Bank" or "CB Pay" logo
    * Shows "Transaction Date" + "Transaction No." + "Receiver" + "Amount"

Extract these fields:
TYPE: (Wave or KPay or CB or Other)
TRANSACTION_NO:
  - Wave: number next to "Transaction ID" (e.g. 894983741)
  - KPay: full number next to "Transaction No." (e.g. 01004089020139330692) — ALL digits
  - CB: number next to "Transaction No." or "Reference No."
AMOUNT: (positive number only, no commas, no Ks, no minus/plus — from top large amount, e.g. 1000000)
DATE: (dd/mm/yyyy — from "Date & Time" for Wave, "Transaction Time" for KPay)
TIME: (HH:MM 24hr — convert PM/AM, e.g. 02:55 PM = 14:55)
TRANSFER_TO: (name next to "Transfer To" for KPay, or "Receiver" for Wave Send view — who received the money)
SENDER: (name next to "Sender" for Wave Receive view only — UNKNOWN for KPay and Wave Send view)

TRANSACTION_NO is most critical — read every digit carefully.

Return EXACTLY in this format with no extra text. Write UNKNOWN if not found."""},
            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
        ]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60)
        data = resp.json()
        if "candidates" not in data:
            return {}
        text   = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip().upper()] = val.strip()
        return result
    except Exception as e:
        logger.error(f"Gemini slip: {e}")
        return {}

# ── Payment QR Helpers ────────────────────────────────
PAYMENT_METHOD_INFO = {
    "kpay": {
        "label":  "🔵 KPay",
        "name":   "KPay",
        "number": "09973625985",
        "owner":  "Kyaw Min Tun",
    },
    "wave": {
        "label":  "🟣 Wave",
        "name":   "Wave",
        "number": "09799959537",
        "owner":  "Kyaw Min Tun",
    },
    "cb": {
        "label":  "🟢 CB Bank",
        "name":   "CB Bank MMQR",
        "number": "(QR Scan)",
        "owner":  "Kyaw Min Tun (Merchant)",
    },
}

async def get_payment_qr(method: str) -> str:
    """Sheet ကနေ file_id ဆွဲ (10 min cache)"""
    method = method.lower().strip()
    cached = payment_qr_cache.get(method)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < 600:  # 10 min
            return cached["file_id"]
    if not SHEET_WEBHOOK:
        return ""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getPaymentQR",
                "method": method,
            }, timeout=10)
        data = resp.json()
        if data.get("ok") and data.get("fileId"):
            file_id = data["fileId"]
            payment_qr_cache[method] = {"file_id": file_id, "ts": datetime.now()}
            return file_id
    except Exception as e:
        logger.error(f"get_payment_qr {method}: {e}")
    return ""

async def set_payment_qr(method: str, file_id: str, admin_name: str) -> bool:
    """Sheet မှာ file_id သိမ်း + cache ဖျက်"""
    method = method.lower().strip()
    if not SHEET_WEBHOOK:
        return False
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":    "setPaymentQR",
                "method":    method,
                "fileId":    file_id,
                "adminName": admin_name,
            }, timeout=10)
        result = resp.json()
        if result.get("ok"):
            payment_qr_cache.pop(method, None)  # cache invalidate
            return True
    except Exception as e:
        logger.error(f"set_payment_qr {method}: {e}")
    return False

# ── Save Member with Password ─────────────────────────
async def save_member_to_sheet(user_id: str, username: str, days: int,
                                password: str = "", package: str = "CH") -> bool:
    if not SHEET_WEBHOOK:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":   "saveMember",
                "userId":   str(user_id),
                "username": username,
                "days":     days,
                "password": password,
                "package":  package,
            }, timeout=10, follow_redirects=True)
        return resp.json().get("status") == "ok"
    except Exception as e:
        logger.error(f"saveMember: {e}")
        return False

async def create_invite_link(context, days: int) -> str:
    try:
        import time
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int(time.time() + 1800)
        )
        return invite.invite_link
    except Exception as e:
        logger.error(f"Invite link: {e}")
        return ""

async def send_approval_dm(context, member_id: int, months: int,
                           password: str, invite_url: str, package: str = "CH"):
    is_web      = package == "WEB"
    expire_date = (datetime.now() + timedelta(days=months * 30)).strftime("%d/%m/%Y")
    cust_kb = []
    if invite_url:
        cust_kb.append([InlineKeyboardButton("📢 Channel ဝင်ရန်", url=invite_url)])
    if is_web:
        cust_kb.append([InlineKeyboardButton("🌐 Web App ဖွင့်",
                        url="https://kyawmintun08.github.io/Japan-Auction-Car-Checker/")])

    if is_web:
        text = (
            f"🎉 *Membership Approved!*\n\n"
            f"📦 Package: 💎 Web Premium\n"
            f"📅 သက်တမ်း: *{months} လ*\n"
            f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
            f"🔑 *Web Password: `{password}`*\n"
            f"🌐 Web: kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
            f"⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့\n"
            f"   မျှဝေပါက Membership ပိတ်သိမ်းခံရမည်\n\n"
            f"သက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"
        )
    else:
        text = (
            f"🎉 *Membership Approved!*\n\n"
            f"📦 Package: 📱 Standard\n"
            f"📅 သက်တမ်း: *{months} လ*\n"
            f"⏰ ကုန်ဆုံးရက်: `{expire_date}`\n\n"
            f"📢 Channel invite link အပေါ်မှ ဝင်ပါ\n\n"
            f"သက်တမ်းတိုးဖို့: /renew\nကျေးဇူးတင်ပါတယ် 🙏"
        )
    try:
        msg = await context.bot.send_message(
            chat_id=member_id, text=text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(cust_kb) if cust_kb else None)
        try:
            await context.bot.pin_chat_message(
                chat_id=member_id,
                message_id=msg.message_id,
                disable_notification=True)
        except Exception as e:
            logger.error(f"Pin message: {e}")
    except Exception as e:
        logger.error(f"Send approval DM: {e}")

# ── Commands ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    is_admin = user_id in ADMIN_IDS

    kb = []
    kb.append([InlineKeyboardButton("🆕 Membership ဝယ်ရန်", callback_data="join_start")])
    if ADMIN_USERNAME:
        kb.append([InlineKeyboardButton("💬 Admin ကို ဆက်သွယ်", url=f"https://t.me/{ADMIN_USERNAME}")])
    kb.append([InlineKeyboardButton("🌐 Web App ကြည့်",
               url="https://kyawmintun08.github.io/Japan-Auction-Car-Checker/")])

    if is_admin:
        cmd_text = (
            "*Member Commands:*\n"
            "🔍 `/find NT32-504837` → Chassis ရှာ\n"
            "🔎 `/model xtrail` → Model ရှာ\n"
            "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
            "📊 `/list` → ကားအားလုံး\n"
            "🌐 `/web` → Web Link\n"
            "🔄 `/renew` → Membership သက်တမ်းတိုး\n"
            "🔑 `/mypassword` → Password ပြန်ယူ\n\n"
            "*Admin Commands:*\n"
            "📸 ကားပုံ တင် → Chassis auto ဖတ်\n"
            "📋 ပုံ + caption `list` → Auction List (Auto detect location)\n"
            "💰 `/price NT32-504837 150000` → ဈေးထည့်\n"
            "✅ `/approve @user 30 WEB` → Member approve\n"
            "👥 `/members` → Member list\n"
            "🔄 `/renew` → Member renew\n"
            "🚫 `/kick @user` → Member kick\n"
            "🔑 `/resetpass @user` → Password reset\n"
            "🆔 `/updateid @user newID` → ID update\n"
            "💳 `/setqr` → Payment QR ထည့်/ပြောင်း\n"
            "💾 `/backup` → CSV backup\n"
        )
    else:
        cmd_text = (
            "*Commands:*\n"
            "🔍 `/find NT32-504837` → Chassis ရှာ\n"
            "🔎 `/model xtrail` → Model ရှာ\n"
            "📋 `/history NT32-504837` → ဈေးမှတ်တမ်း\n"
            "📊 `/list` → ကားအားလုံး\n"
            "🌐 `/web` → Web Link\n"
            "🔄 `/renew` → Membership သက်တမ်းတိုး\n"
            "🔑 `/mypassword` → Password ပြန်ယူ\n"
        )

    await update.message.reply_text(
        f"🚗 *Japan Auction Car Checker*\n"
        f"📍 {LOC_MAESOT} & {LOC_KLANG9} & {LOC_BORDER44}\n\n"
        + cmd_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb))

async def find_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    user_id  = update.effective_user.id
    str_uid  = str(user_id)
    if not await is_active_member(user_id):
        # 10 Day Promo eligibility check
        promo_info = await check_promo10d_eligibility(str_uid)
        if promo_info.get("active"):
            pass  # PROMO10D active — proceed to carrequest
        elif not promo_info.get("eligible"):
            await update.message.reply_text(
                f"❌ *ဝင်ခွင့်မရပါ*\n\n{promo_info['reason']}\n\n"
                f"Membership ရယူရန် /start နှိပ်ပါ",
                parse_mode='Markdown')
            return
        else:
            # Show buying car button
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚗 ကားဝယ်ယူဖို့ လာတာလားး?", callback_data=f"buying_car_{user_id}")
            ]])
            await update.message.reply_text(
                "👋 *Japan Auction Car Checker*\n\n"
                "ကားဝယ်ယူလိုပါက *10 Day Free Promo* ရရှိနိုင်ပါသည်\n\n"
                "⚠️ စည်ကမ်းချက်:\n"
                "• Broker နှင့် ဆက်သွယ်ပြီး Order တင်ရမည်\n"
                "• 10 ရက်အတွင်း Order မတင်ပါက Kick ခံရမည်\n"
                "• Cancel ၂ ကြိမ်နှင့်အထက် ဖြစ်ပါက Promo မရနိုင်\n\n"
                "ဆက်လုပ်မည်ဆိုပါက 👇",
                parse_mode='Markdown',
                reply_markup=kb)
            return
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/find NT32-504837`", parse_mode='Markdown')
        return
    is_admin = user_id in ADMIN_IDS
    chassis  = ' '.join(context.args)
    car      = find_by_chassis(chassis)
    if car:
        history = get_price_history(car['chassis'])
        txt     = format_car_info(car, history[-1]['price'] if history else None, history or None)
        kb = [[
            InlineKeyboardButton("💰 ဈေးထည့်",  callback_data=f"addprice_{car['chassis']}"),
            InlineKeyboardButton("✏️ ပြင်ရန်",   callback_data=f"editcar_{car['chassis']}"),
        ]] if is_admin else []
        await update.message.reply_text(txt, parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    else:
        guessed = guess_model_from_chassis(chassis)
        if guessed == "UNKNOWN":
            guessed = await guess_model_gemini(chassis)
        if is_admin:
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*\n\n`/price {chassis} [ဈေး]`"
                   if guessed != "UNKNOWN"
                   else f"❌ `{chassis}` မတွေ့ပါ\n\n`/price {chassis} [ဈေး]`")
        else:
            msg = (f"⚠️ `{chassis}` Checklist မှာ မပါဘူး\n🚗 ခန့်မှန်း: *{guessed}*"
                   if guessed != "UNKNOWN"
                   else f"❌ `{chassis}` မတွေ့ပါ")
        await update.message.reply_text(msg, parse_mode='Markdown')

async def find_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    user_id  = update.effective_user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Model ထည့်ပါ\nဥပမာ: `/model xtrail`", parse_mode='Markdown')
        return
    is_admin = user_id in ADMIN_IDS
    query    = ' '.join(context.args)
    results  = find_by_model(query)
    if not results:
        if is_admin:
            await update.message.reply_text(
                f"❌ *{query}* မတွေ့ပါ\n\n💡 Admin: ပုံ + caption `list` တင်ပြီး checklist ထည့်နိုင်",
                parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ *{query}* Checklist မှာ မရှိသေးပါ", parse_mode='Markdown')
        return
    txt = f"🔎 *{query.upper()}* ({len(results)} စီး):\n\n"
    for car in results:
        history   = get_price_history(car['chassis'])
        price_str = f"฿{history[-1]['price']:,}" if history else "ဈေးမရသေး"
        txt += f"• `{car['chassis']}` — {car['color']} {ys(car.get('year',0))} [{loc_display(car.get('loc','MaeSot'))}] — *{price_str}*\n"
    txt += f"\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Admin သာ ဈေးထည့်ခွင့်ရှိတယ်")
        return
    if not check_rate_limit(user_id):
        await update.message.reply_text("⚠️ Request များသွားတယ် — ခဏစောင့်ပါ")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format:\n"
            "`/price CHASSIS PRICE` — အခြေခံ\n"
            "`/price CHASSIS PRICE COLOR` — color ပါ\n"
            "`/price CHASSIS PRICE MODEL COLOR` — model+color ပါ\n\n"
            "ဥပမာ:\n"
            "`/price VZN11-042846 74000 WHITE`\n"
            "`/price VZN11-042846 74000 AD VAN WHITE`",
            parse_mode='Markdown')
        return
    chassis = context.args[0].upper()
    try:
        price = int(context.args[1].replace(',',''))
    except:
        await update.message.reply_text("❌ ဈေး ဂဏန်းသာ ထည့်ပါ", parse_mode='Markdown')
        return

    extra_args = context.args[2:]
    car = find_by_chassis(chassis)

    if extra_args:
        if len(extra_args) == 1:
            override_color = extra_args[0].upper()
            override_model = None
        else:
            override_color = extra_args[-1].upper()
            override_model = " ".join(extra_args[:-1]).upper()

        if car:
            for c in CARS:
                if c.get("chassis","").upper() == chassis.upper():
                    if override_color: c["color"] = override_color
                    if override_model: c["model"] = override_model
                    break
        else:
            base_model = override_model or guess_model_from_chassis(chassis)
            car = {"chassis": chassis, "model": base_model,
                   "color": override_color, "year": 0, "loc": "MaeSot"}

        if override_color and car: car = dict(car); car["color"] = override_color
        if override_model and car: car["model"] = override_model

        if SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient() as client:
                    if override_color:
                        await client.post(SHEET_WEBHOOK, json={
                            "action": "updateCar", "chassis": chassis,
                            "field": "color", "value": override_color
                        }, timeout=10, follow_redirects=True)
                    if override_model:
                        await client.post(SHEET_WEBHOOK, json={
                            "action": "updateCar", "chassis": chassis,
                            "field": "model", "value": override_model
                        }, timeout=10, follow_redirects=True)
            except Exception as e:
                logger.error(f"updateCar in price cmd: {e}")
    else:
        if not car:
            car = {"chassis": chassis, "model": guess_model_from_chassis(chassis),
                   "color": "-", "year": 0, "loc": "MaeSot"}

    user_name = update.effective_user.first_name or "Unknown"
    loc       = loc_display(car.get('loc','MaeSot'))
    entry     = await save_price(car['chassis'], car['model'], car['color'], car['year'], price, user_name, location=loc)
    await update.message.reply_text(
        f"✅ *ဈေးထည့်ပြီး!*\n\n🚗 {car['model']} ({ys(car.get('year',0))}) — `{chassis}`\n"
        f"🎨 {car['color']}\n💰 ฿{price:,}\n📍 {loc}\n📅 {entry['date']}\n👤 {user_name}\n\n"
        f"🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)",
        parse_mode='Markdown')

async def price_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🔒 *Admin သာ သုံးနိုင်ပါသည်*", parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Chassis ထည့်ပါ\nဥပမာ: `/history NT32-504837`", parse_mode='Markdown')
        return
    chassis  = ' '.join(context.args).upper()
    history  = get_price_history(chassis)
    if not history:
        await update.message.reply_text(f"❌ `{chassis}` ဈေးမှတ်တမ်း မရှိသေးပါ", parse_mode='Markdown')
        return
    car  = find_by_chassis(chassis)
    txt  = f"📈 *{car['model'] if car else chassis}*\n`{chassis}`\n\n"
    prev = None
    for h in history:
        if prev:
            diff  = h['price'] - prev
            arrow = "📈" if diff > 0 else "📉" if diff < 0 else "➡"
            txt += f"• {h['date']} → *฿{h['price']:,}* ({arrow} {diff:+,})\n"
        else:
            txt += f"• {h['date']} → *฿{h['price']:,}*\n"
        prev = h['price']
    if len(history) >= 2:
        change = history[-1]['price'] - history[0]['price']
        pct    = (change / history[0]['price']) * 100
        txt += f"\n📊 ပြောင်းလဲမှု: *{change:+,}* ({pct:+.1f}%)"
    kb = [[
        InlineKeyboardButton("💰 ဈေးအသစ်ထည့်", callback_data=f"addprice_{chassis}"),
        InlineKeyboardButton("✏️ ပြင်ရန်",      callback_data=f"editcar_{chassis}"),
    ]]
    await update.message.reply_text(txt, parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(kb))

async def list_cars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    priced = {p['chassis'] for p in PRICE_HISTORY}
    txt    = f"🚗 *ကားစာရင်း ({len(CARS)} စီး)*\n\n"
    for car in CARS[:20]:
        status = "💰" if car['chassis'] in priced else "⏳"
        txt += f"{status} `{car['chassis']}` — {car['model']} {ys(car.get('year',0))} [{loc_display(car.get('loc','MaeSot'))}]\n"
    if len(CARS) > 20:
        txt += f"\n... နှင့် {len(CARS)-20} စီး ထပ်ရှိ"
    txt += f"\n\n🌐 [Web မှာကြည့်](https://kyawmintun08.github.io/Japan-Auction-Car-Checker/)"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def web_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pkg     = await get_member_package(user_id)
    if pkg == "WEB":
        await update.message.reply_text(
            f"🌐 *Japan Auction Car Checker — Web App*\n\n"
            f"https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
            f"• {LOC_MAESOT} + {LOC_KLANG9} 🚗\n• ဈေးကြည့်နိုင် 📈\n• Chart ကြည့်နိုင် 📊",
            parse_mode='Markdown')
    elif pkg == "CH":
        await update.message.reply_text(
            "🚫 *Web App access မရှိသေးပါ*\n\n"
            "လက်ရှိ Package: 📱 Standard\n\n"
            "🌐 Web App ကြည့်ဖို့ *Channel+Web Package* သို့ Upgrade လုပ်ပါ\n"
            "👉 /renew နှိပ်ပြီး 💎 Web Premium package ရွေးပါ",
            parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "🚫 *Member များသာ Web App ကြည့်နိုင်ပါသည်*\n\nMembership ဝယ်ရန် 👉 /renew",
            parse_mode='Markdown')

def build_package_keyboard(user_id: int, action: str = "renew"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📱 Standard",      callback_data=f"pkg_CH_{user_id}_{action}"),
         InlineKeyboardButton(f"💎 Web Premium",   callback_data=f"pkg_WEB_{user_id}_{action}")],
        [InlineKeyboardButton("❌ Cancel",          callback_data=f"pkg_cancel_{user_id}")],
    ])

def build_period_keyboard(user_id: int, package: str):
    prices = PLAN_PRICES[package]
    if package == "CH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"1 လ — {prices[1]:,} ks",  callback_data=f"period_{package}_1_{user_id}"),
             InlineKeyboardButton(f"2 လ — {prices[2]:,} ks",  callback_data=f"period_{package}_2_{user_id}")],
            [InlineKeyboardButton(f"3 လ — {prices[3]:,} ks",  callback_data=f"period_{package}_3_{user_id}"),
             InlineKeyboardButton(f"5 လ — {prices[5]:,} ks",  callback_data=f"period_{package}_5_{user_id}")],
            [InlineKeyboardButton("◀️ နောက်သို့",             callback_data=f"pkg_back_{user_id}")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"1 လ — {prices[1]:,} ks",  callback_data=f"period_{package}_1_{user_id}"),
             InlineKeyboardButton(f"2 လ — {prices[2]:,} ks",  callback_data=f"period_{package}_2_{user_id}"),
             InlineKeyboardButton(f"3 လ — {prices[3]:,} ks",  callback_data=f"period_{package}_3_{user_id}")],
            [InlineKeyboardButton("◀️ နောက်သို့",             callback_data=f"pkg_back_{user_id}")],
        ])

def build_paymethod_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 KPay",    callback_data=f"paymethod_kpay_{user_id}"),
         InlineKeyboardButton("🟣 Wave",    callback_data=f"paymethod_wave_{user_id}"),
         InlineKeyboardButton("🟢 CB Bank", callback_data=f"paymethod_cb_{user_id}")],
        [InlineKeyboardButton("❌ Cancel",  callback_data=f"pkg_cancel_{user_id}")],
    ])

async def renew_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    await update.message.reply_text(
        "🔄 *Membership သက်တမ်းတိုး*\n\n"
        "Package ရွေးချယ်ပါ 👇",
        parse_mode='Markdown',
        reply_markup=build_package_keyboard(user_id, "renew"))

async def mypassword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    if not await is_active_member(user_id):
        await update.message.reply_text(
            "🔒 *Member များသာ သုံးနိုင်ပါသည်*\n\nMembership ရယူရန် /start နှိပ်ပါ",
            parse_mode='Markdown')
        return
    pkg = await get_member_package(user_id)
    if pkg != "WEB":
        await update.message.reply_text(
            "🚫 *Web Password မရှိပါ*\n\n"
            "လက်ရှိ Package: 📱 Standard\n\n"
            "🌐 Web App သုံးဖို့ 💎 *Web Premium* သို့ Upgrade လုပ်ပါ\n"
            "👉 /renew နှိပ်ပြီး Web Premium ရွေးပါ",
            parse_mode='Markdown')
        return
    if not SHEET_WEBHOOK:
        await update.message.reply_text("❌ System error — Admin ကို ဆက်သွယ်ပါ")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getPassword",
                "userId": str(user_id),
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok" and data.get("password"):
            await update.message.reply_text(
                f"🔑 *သင်၏ Web Password*\n\n"
                f"`{data['password']}`\n\n"
                f"🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
                f"⚠️ Password ကို မည်သူ့ကိုမျှ မပေးပါနဲ့\n"
                f"   မျှဝေပါက Membership ပိတ်သိမ်းခံရမည်",
                parse_mode='Markdown')
        else:
            admin_link = f"\n💬 [Admin ကို ဆက်သွယ်](https://t.me/{ADMIN_USERNAME})" if ADMIN_USERNAME else ""
            await update.message.reply_text(
                f"❌ Password မတွေ့ပါ\n\nAdmin ကို ဆက်သွယ်ပါ{admin_link}",
                parse_mode='Markdown')
    except Exception as e:
        logger.error(f"mypassword: {e}")
        await update.message.reply_text("❌ Error — Admin ကို ဆက်သွယ်ပါ")

async def resetpass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if not context.args:
        await update.message.reply_text("❌ Format: `/resetpass @username` သို့မဟုတ် `/resetpass 123456789`",
                                        parse_mode='Markdown')
        return
    target = context.args[0].replace('@', '')
    new_pw = generate_password()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action":   "resetPassword",
                "username": target,
                "password": new_pw,
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok":
            member_id = data.get("userId")
            if member_id and str(member_id).isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(member_id),
                        text=f"🔑 *Password Reset လုပ်ပြီ*\n\n"
                             f"New Password: `{new_pw}`\n\n"
                             f"🌐 https://kyawmintun08.github.io/Japan-Auction-Car-Checker/\n\n"
                             f"⚠️ မည်သူ့ကိုမျှ မပေးပါနဲ့",
                        parse_mode='Markdown')
                except Exception as e:
                    logger.error(f"resetpass DM: {e}")
            await update.message.reply_text(
                f"✅ Password Reset ပြီ\n👤 @{target}\n🔑 `{new_pw}`",
                parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ @{target} မတွေ့ပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def updateid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Format: `/updateid @username [oldID] [newID]`\n"
            "ဥပမာ: `/updateid @Steve 123456789 987654321`\n\n"
            "⚠️ Old ID မပါရင် update မလုပ်ဘူး — Security အတွက်",
            parse_mode='Markdown')
        return
    target_username = context.args[0].replace('@', '')
    try:
        old_id = int(context.args[1])
        new_id = int(context.args[2])
    except:
        await update.message.reply_text("❌ ID တွေ ဂဏန်းဖြစ်ရမည်")
        return
    if old_id == new_id:
        await update.message.reply_text("❌ Old ID နဲ့ New ID တူနေတယ်")
        return
    if new_id in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ID ကို Member ID အဖြစ် သုံးမရပါ")
        return
    await update.message.reply_text("🔍 Old ID စစ်ဆေးနေတယ်... ⏳")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "verifyOldId",
                "username": target_username,
                "oldId": str(old_id),
            }, timeout=10, follow_redirects=True)
        data = resp.json()
        if data.get("status") != "ok":
            await update.message.reply_text(
                f"❌ *Old ID မမှန်ဘူး*\n\n"
                f"@{target_username} ရဲ့ Sheet မှာ `{old_id}` မတွေ့ဘူး\n"
                f"Old ID ကို ပြန်စစ်ပြီး ထပ်ကြိုးစားပါ",
                parse_mode='Markdown')
            return
    except Exception as e:
        logger.error(f"verifyOldId: {e}")
        await update.message.reply_text("❌ Sheet စစ်မရ — ထပ်ကြိုးစားပါ")
        return
    pending_updateid[user_id] = {
        "target_username": target_username,
        "old_id": old_id,
        "new_id": new_id,
    }
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ အတည်ပြု",  callback_data=f"uid_ok_{user_id}"),
        InlineKeyboardButton("❌ မလုပ်တော့", callback_data=f"uid_no_{user_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ *ID Update အတည်ပြုချက်*\n\n"
        f"👤 Member: @{target_username}\n"
        f"🔴 ဟောင်း ID: `{old_id}` ✅ စစ်မှန်ပြီ\n"
        f"🟢 အသစ် ID: `{new_id}`\n\n"
        f"အတည်ပြုရန် 👇",
        parse_mode='Markdown',
        reply_markup=kb)

# ── /setqr — Admin Payment QR Setup ──────────────────
async def setqr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return

    # Show current state
    status_lines = []
    for method, info in PAYMENT_METHOD_INFO.items():
        file_id = await get_payment_qr(method)
        mark    = "✅" if file_id else "⚪"
        status_lines.append(f"{mark} {info['label']}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 KPay",    callback_data=f"setqr_kpay_{user_id}"),
         InlineKeyboardButton("🟣 Wave",    callback_data=f"setqr_wave_{user_id}"),
         InlineKeyboardButton("🟢 CB Bank", callback_data=f"setqr_cb_{user_id}")],
        [InlineKeyboardButton("❌ Cancel",  callback_data=f"setqr_cancel_{user_id}")],
    ])
    await update.message.reply_text(
        f"💳 *Payment QR Setup*\n\n"
        f"လက်ရှိ အခြေအနေ:\n"
        + "\n".join(status_lines)
        + "\n\nဘယ် method အတွက် QR ထည့်/ပြောင်းမလဲ? 👇",
        parse_mode='Markdown',
        reply_markup=kb)

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return

    pkg_filter = None
    msg_parts  = context.args if context.args else []
    if msg_parts and msg_parts[0].upper() in ("WEB", "CH"):
        pkg_filter = msg_parts[0].upper()
        msg_parts  = msg_parts[1:]

    message = " ".join(msg_parts)

    if not message:
        pending_broadcast[user_id] = {
            "pkg_filter": pkg_filter,
            "waiting_photo": True
        }
        pkg_label = f" ({pkg_filter} only)" if pkg_filter else " (အားလုံး)"
        await update.message.reply_text(
            f"📢 *Broadcast{pkg_label}*\n\n"
            f"ပုံနဲ့ Caption တွဲပြီး ပို့ပါ\n"
            f"(Caption = Message ဖြစ်မည်)\n\n"
            f"Text သာ ပို့ချင်ရင်:\n"
            f"`/broadcast မက်ဆေ့ပါ`\n\n"
            f"❌ Cancel: /broadcast cancel",
            parse_mode='Markdown')
        return

    if message.lower() == "cancel":
        pending_broadcast.pop(user_id, None)
        await update.message.reply_text("❌ Broadcast ပယ်ဖျက်ပြီ")
        return

    await update.message.reply_text("⏳ Member list ဆွဲနေတယ်...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SHEET_WEBHOOK,
                json={"action": "getMembers"},
                timeout=15,
                follow_redirects=True
            )
        data = resp.json()
        members = data.get("members", [])
    except Exception as e:
        logger.error(f"broadcast getMembers: {e}")
        await update.message.reply_text("❌ Member list ဆွဲမရ")
        return

    targets = []
    for m in members:
        status  = str(m.get("status", "")).upper()
        pkg     = str(m.get("package", "")).upper()
        uid     = m.get("userId") or m.get("userID") or m.get("UserID")
        if status != "ACTIVE":
            continue
        if pkg_filter and pkg != pkg_filter:
            continue
        if uid:
            targets.append(str(uid))

    if not targets:
        await update.message.reply_text("❌ Member မတွေ့ဘူး")
        return

    pkg_label = f" ({pkg_filter} only)" if pkg_filter else ""
    await update.message.reply_text(f"📢 {len(targets)} ယောက်ကို ပို့မည်{pkg_label}...")

    success = 0
    failed  = 0
    for uid in targets:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *Japan Auction Car*\n\n{message}",
                parse_mode='Markdown')
            success += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"broadcast {uid}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ *Broadcast ပြီးပြီ*\n\n"
        f"✅ အောင်မြင်: {success} ယောက်\n"
        f"❌ မရောက်: {failed} ယောက်",
        parse_mode='Markdown')

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_IDS and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin သာ သုံးနိုင်တယ်")
        return
    await update.message.reply_text("⏳ Sheet မှ data ဆွဲနေသည်...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SHEET_WEBHOOK, json={
                "action": "getBackupCSV"
            }, timeout=30, follow_redirects=True)
        data = resp.json()
        if data.get("status") == "ok" and data.get("csv"):
            csv_content = data["csv"]
            filename    = f"Members_backup_{datetime.now().strftime('%Y_%m_%d')}.csv"
            csv_bytes   = csv_content.encode('utf-8-sig')
            from io import BytesIO
            bio = BytesIO(csv_bytes)
            bio.name = filename
            await context.bot.send_document(
                chat_id=user_id,
                document=bio,
                filename=filename,
                caption=f"✅ Members Backup\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        else:
            await update.message.reply_text("❌ Backup မရနိုင်ပါ — Sheet စစ်ဆေးပါ")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def upgrade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    await update.message.reply_text(
        "⬆️ *Package Upgrade*\n\n"
        "📱 Standard → 💎 Web Premium\n\n"
        "Web ဝင်ခွင့် ထပ်ထည့်ချင်ရင် Package ရွေးပါ 👇",
        parse_mode='Markdown',
        reply_markup=build_package_keyboard(user_id, "upgrade"))

# ── NEW: Broker Session Selector ──────────────────────
async def broker_ask_target(msg_obj, context, broker_tg_id: str,
                             broker_sessions: list, text: str = "",
                             is_photo: bool = False, file_bytes: bytes = None,
                             caption: str = ""):
    pending_broker_target[broker_tg_id] = {
        "text": text, "is_photo": is_photo,
        "file_bytes": file_bytes, "caption": caption,
        "sessions": broker_sessions,
    }
    btns = []
    for req_id, sess in broker_sessions:
        svc  = sess.get("serviceType", "search")
        icon = "🏆" if svc == "auction" else "🔍"
        cust = sess.get("customerUsername", "Customer")
        btns.append([InlineKeyboardButton(
            f"{icon} {req_id} — {cust}",
            callback_data=f"bsel_{broker_tg_id}_{req_id}")])
    btns.append([InlineKeyboardButton(
        "❌ မပို့တော့ဘူး",
        callback_data=f"bsel_{broker_tg_id}_cancel")])
    await msg_obj.reply_text(
        "💬 *Session ၂ ခုရှိတယ် — ဘယ် Customer ကို ပို့မလဲ?*",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

# ── OCR ───────────────────────────────────────────────
def tesseract_ocr_chassis(file_bytes: bytes) -> str:
    if not TESSERACT_AVAILABLE:
        return ""
    try:
        img     = Image.open(BytesIO(file_bytes))
        text    = pytesseract.image_to_string(img)
        chassis = extract_chassis_from_text(text)
        return chassis or ""
    except Exception as e:
        logger.error(f"Tesseract: {e}")
        return ""

async def gemini_ocr_auction_list(file_bytes: bytes) -> tuple:
    if not GEMINI_API_KEY:
        return [], None
    try:
        import base64, json
        img_b64 = base64.b64encode(file_bytes).decode()
        url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        payload = {"contents":[{"parts":[
            {"text": (
                "This is a JAN JAPAN auction car list image from Thailand.\n\n"
                "STEP 1 — Read the TITLE/HEADER at the very top of the image:\n"
                "   Look for these EXACT words in the blue/colored header band:\n"
                "   → 'KLANG9' or 'KLANG 9' or '9.2 FREEZONE' = location is Klang9\n"
                "   → 'MAESOT' or 'MAE SOT' = location is MaeSot\n"
                "   → 'BEST BORDER' or '44 GATE' or 'BORDER-44' or 'BORDER 44' = location is Border44\n\n"
                "STEP 2 — Extract every car row from the table.\n\n"
                "Return ONLY valid JSON, no markdown, no explanation:\n"
                "{\"location\":\"Klang9\",\"cars\":[{\"chassis\":\"NT32-024640\",\"model\":\"X-TRAIL\",\"color\":\"BLACK\",\"year\":2014}]}\n\n"
                "Rules:\n"
                "- location MUST be exactly 'Klang9' OR 'MaeSot' OR 'Border44'\n"
                "- If header says KLANG9 → location = 'Klang9'\n"
                "- If header says BEST BORDER or 44 GATE → location = 'Border44'\n"
                "- If header says MAESOT → location = 'MaeSot'\n"
                "- year must be a number (e.g. 2014 not '2014')"
            )},
            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
        ]}]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=60)
        data = resp.json()
        if "candidates" not in data:
            return [], None
        text  = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        start = text.find('{'); end = text.rfind('}') + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
            cars   = parsed.get("cars", [])
            loc    = parsed.get("location", None)
            return cars, loc
        start = text.find('['); end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]), None
    except Exception as e:
        logger.error(f"Gemini list: {e}")
    return [], None

async def gemini_ocr_chassis(file_bytes: bytes) -> dict:
    if GEMINI_API_KEY:
        try:
            import base64
            img_b64 = base64.b64encode(file_bytes).decode()
            url     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents":[{"parts":[
                {"text":"""Japan auction car photo.
1. Find chassis number written on windshield with marker pen (e.g. NT32-024640, GP1-1049821, S510P-0173458)
2. Identify car body COLOR from the paint (WHITE, BLACK, SILVER, PEARL WHITE, DARK BLUE, RED, BLUE, GREEN, YELLOW, BROWN, ORANGE, GREY)
3. Identify car MODEL from the shape/badge
4. Identify manufacturing YEAR if visible

Return EXACTLY in this format (no extra text):
CHASSIS: S510P-0236416
MODEL: HIJET TRUCK
COLOR: WHITE
YEAR: 2017"""},
                {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}
            ]}]}
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=60)
            data = resp.json()
            logger.info(f"Gemini chassis raw: {data}")
            if "candidates" in data and data["candidates"]:
                cand = data["candidates"][0]
                if "content" not in cand:
                    logger.warning(f"Gemini no content: finishReason={cand.get('finishReason','?')}")
                else:
                    text    = cand["content"]["parts"][0]["text"].strip().upper()
                    chassis = ""; model = ""; color = ""; year = 0
                    for line in text.split("\n"):
                        line = line.strip()
                        if line.startswith("CHASSIS:"):
                            raw = line.replace("CHASSIS:","").strip()
                            for pat in [
                                r'[A-Z]{1,5}\d{1,4}[A-Z]{0,2}\d{0,2}[-\s]\d{4,7}',
                                r'[A-Z]{2,6}\d{2,4}[-\s]\d{4,7}',
                                r'[A-Z0-9]{4,20}[-\s]\d{4,7}',
                                r'[A-Z0-9]{6,25}',
                            ]:
                                m = re.search(pat, raw)
                                if m:
                                    chassis = m.group().replace(' ', '-').strip()
                                    break
                        elif line.startswith("MODEL:"): model = line.replace("MODEL:","").strip()
                        elif line.startswith("COLOR:"): color = line.replace("COLOR:","").strip()
                        elif line.startswith("YEAR:"):
                            try: year = int(re.search(r'\d{4}', line).group())
                            except: year = 0
                    if chassis:
                        return {"chassis":chassis,"model":model,"color":color,"year":year}
        except Exception as e:
            logger.error(f"Gemini OCR error: {e}")
    chassis = tesseract_ocr_chassis(file_bytes)
    return {"chassis":chassis,"model":"","color":"","year":0}

# ── Photo Handler ─────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CARS
    user    = update.effective_user
    user_id = user.id
    photo   = update.message.photo[-1]
    caption = (update.message.caption or "").strip().lower()

    if not check_rate_limit(user_id, max_req=5, window=60):
        await update.message.reply_text("⚠️ တစ်မိနစ်အတွင်း ပုံများသွားတယ် — ခဏစောင့်ပါ")
        return

    # ── Admin /setqr Mode ──
    if user_id in ADMIN_IDS and user_id in pending_setqr:
        method     = pending_setqr.pop(user_id)
        file_id    = photo.file_id
        admin_name = update.effective_user.first_name or "admin"
        ok         = await set_payment_qr(method, file_id, admin_name)
        info       = PAYMENT_METHOD_INFO.get(method, {})
        if ok:
            await update.message.reply_text(
                f"✅ *{info.get('label','')} QR Saved!*\n\n"
                f"📋 ID: `{file_id[:20]}...`\n"
                f"👤 By: {admin_name}\n\n"
                f"➡️ နောက် method ထည့်ဖို့ /setqr ထပ်နှိပ်ပါ",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Save မရဘူး — Sheet စစ်ဆေးပါ")
        return

    # ── Broadcast Photo Mode ──
    if user_id in pending_broadcast and pending_broadcast[user_id].get("waiting_photo"):
        bc      = pending_broadcast.pop(user_id)
        pkg_filter = bc.get("pkg_filter")
        caption_text = update.message.caption or ""

        await update.message.reply_text("⏳ Member list ဆွဲနေတယ်...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    SHEET_WEBHOOK,
                    params={"action": "getMembers"},
                    timeout=15, follow_redirects=True)
            data = resp.json()
            members = data.get("members", [])
        except Exception as e:
            logger.error(f"broadcast getMembers: {e}")
            await update.message.reply_text("❌ Member list ဆွဲမရ")
            return

        targets = []
        for m in members:
            status = str(m.get("status","")).upper()
            pkg    = str(m.get("package","")).upper()
            uid    = m.get("userId") or m.get("userID") or m.get("UserID")
            if status != "ACTIVE": continue
            if pkg_filter and pkg != pkg_filter: continue
            if uid: targets.append(str(uid))

        if not targets:
            await update.message.reply_text("❌ Member မတွေ့ဘူး")
            return

        pkg_label = f" ({pkg_filter} only)" if pkg_filter else ""
        await update.message.reply_text(f"📢 {len(targets)} ယောက်ကို ပုံ+စာ ပို့မည်{pkg_label}...")

        file = await photo.get_file()
        file_bytes = bytes(await file.download_as_bytearray())
        from io import BytesIO

        success = 0; failed = 0
        for uid in targets:
            try:
                bio = BytesIO(file_bytes)
                bio.name = "broadcast.jpg"
                cap = f"📢 *Japan Auction Car*\n\n{caption_text}" if caption_text else "📢 *Japan Auction Car*"
                await context.bot.send_photo(
                    chat_id=int(uid),
                    photo=bio,
                    caption=cap,
                    parse_mode="Markdown")
                success += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"broadcast photo {uid}: {e}")
                failed += 1

        await update.message.reply_text(
            f"✅ *Broadcast ပုံ ပြီးပြီ*\n\n✅ အောင်မြင်: {success} ယောက်\n❌ မရောက်: {failed} ယောက်",
            parse_mode="Markdown")
        return

    if str(user_id) in pending_deposit:
        dep_data = pending_deposit[str(user_id)]
        if dep_data.get("step") == "waiting_slip":
            await update.message.reply_text("🔍 Deposit Slip ဖတ်နေတယ်... ⏳")
            try:
                file       = await photo.get_file()
                file_bytes = bytes(await file.download_as_bytearray())
                slip_info  = await gemini_read_slip(file_bytes)
            except Exception as e:
                logger.error(f"deposit slip read: {e}")
                slip_info = {}

            amount   = slip_info.get("AMOUNT", "UNKNOWN")
            pay_type = slip_info.get("TYPE", "UNKNOWN")
            txn_no   = slip_info.get("TRANSACTION_NO", "UNKNOWN")
            date_str = slip_info.get("DATE", "UNKNOWN")

            amount_ok = ""
            if amount != "UNKNOWN":
                try:
                    amt_num = int(re.sub(r'[^\d]', '', amount))
                    if amt_num >= 20000:
                        amount_ok = "✅"
                    else:
                        amount_ok = "⚠️ မပြည့်မီ (฿20,000 လိုသည်)"
                except:
                    amount_ok = "⚠️ စစ်မရ"

            pending_deposit[str(user_id)]["slip_info"] = slip_info

            req_id       = dep_data.get("reqId", "")
            broker_tg_id = dep_data.get("brokerTgId", "")
            name         = update.effective_user.first_name or str(user_id)

            admin_text = (
                f"💰 *Deposit Slip အသစ်*\n\n"
                f"👤 {name} (`{user_id}`)\n"
                f"🆔 Request: `{req_id}`\n\n"
                f"🏦 Type: {pay_type}\n"
                f"🔢 Txn No: `{txn_no}`\n"
                f"💵 Amount: {amount} ฿ {amount_ok}\n"
                f"📅 Date: {date_str}\n\n"
                f"⚠️ စစ်ဆေးပြီးမှ Confirm လုပ်ပါ"
            )
            admin_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💬 {name} ကို Message", url=f"tg://user?id={user_id}")],
                [InlineKeyboardButton("✅ Confirm", callback_data=f"dep_ok_{user_id}"),
                 InlineKeyboardButton("❌ Reject",  callback_data=f"dep_no_{user_id}")],
            ])
            await notify_admins(context, admin_text, reply_markup=admin_kb)
            await update.message.reply_text(
                "✅ *Deposit Slip လက်ခံပြီ!*\n\n"
                "Admin စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏",
                parse_mode='Markdown')
            return

    # ── Photo Relay Mode (Proxy Chat) ──
    str_uid = str(user_id)
    cust_session_photo = next(
        ((sid, s) for sid, s in proxy_sessions.items()
         if str(s.get("customerId","")) == str_uid and s.get("status") == "ACTIVE"),
        None
    )
    # FIXED: collect ALL broker sessions
    broker_sessions_photo = [
        (sid, s) for sid, s in proxy_sessions.items()
        if str(s.get("brokerId","")) == str_uid and s.get("status") == "ACTIVE"
    ]

    if cust_session_photo or broker_sessions_photo:
        if cust_session_photo:
            _sid_chk, _sess_chk = cust_session_photo
            _rid_chk = _sess_chk.get("reqId", "")
            if _rid_chk.startswith("A") and not _sess_chk.get("deposit_paid", False):
                return

        if caption:
            blocked, reason = proxy_filter(caption)
            if blocked:
                await update.message.reply_text(
                    f"⚠️ *Photo Block ဖြစ်သွားတယ်*\n\n"
                    f"❌ Caption မှာ {reason}\n"
                    f"Caption ဖြုတ်ပြီး ပြန်ပို့ပါ",
                    parse_mode='Markdown')
                return

        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
        except Exception as e:
            logger.error(f"photo relay download: {e}")
            await update.message.reply_text("❌ ပုံ download မရဘူး")
            return

        relay_image_url = ""
        if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
            session_id = cust_session_photo[0] if cust_session_photo else broker_sessions_photo[0][0]
            relay_image_url = await upload_to_cloudinary(file_bytes, f"relay_{session_id}_{int(datetime.now().timestamp())}")

        from io import BytesIO

        if cust_session_photo:
            sid, session    = cust_session_photo
            broker_tg_id    = session.get("brokerId")
            req_id          = session.get("reqId", sid)
            cap_text        = f"📷 *Customer #{req_id}:*\n\n{caption}" if caption else f"📷 *Customer #{req_id}*"
            if broker_tg_id:
                try:
                    bio = BytesIO(file_bytes); bio.name = "photo.jpg"
                    await context.bot.send_photo(
                        chat_id=int(broker_tg_id),
                        photo=bio,
                        caption=cap_text,
                        parse_mode='Markdown')
                    await update.message.reply_text("✅ ပုံ ပို့ပြီ")
                except Exception as e:
                    logger.error(f"photo relay C→B: {e}")
                    await update.message.reply_text("❌ Broker ကို မပို့နိုင်ဘူး")
            return

        if broker_sessions_photo:
            if len(broker_sessions_photo) == 1:
                sid, session    = broker_sessions_photo[0]
                customer_id     = session.get("customerId")
                broker_obj      = session.get("brokerObj", {})
                broker_id       = broker_obj.get("brokerId", "B???")
                req_id          = session.get("reqId", sid)
                cap_text        = f"📷 *Broker #{broker_id}:*\n\n{caption}" if caption else f"📷 *Broker #{broker_id}*"
                if customer_id:
                    try:
                        bio = BytesIO(file_bytes); bio.name = "photo.jpg"
                        await context.bot.send_photo(
                            chat_id=int(customer_id), photo=bio,
                            caption=cap_text, parse_mode='Markdown')
                        await update.message.reply_text("✅ ပုံ ပို့ပြီ")
                    except Exception as e:
                        logger.error(f"photo relay B→C: {e}")
                        await update.message.reply_text("❌ Customer ကို မပို့နိုင်ဘူး")
            else:
                await broker_ask_target(
                    update.message, context,
                    broker_tg_id=str_uid,
                    broker_sessions=broker_sessions_photo,
                    text="", is_photo=True,
                    file_bytes=file_bytes, caption=caption)
            return

    # ── Payment Slip Mode ──
    if user_id in pending_payment:
        pay_data = pending_payment[user_id]
        if pay_data.get("waiting_slip"):
            await update.message.reply_text("🔍 Payment Slip ဖတ်နေတယ်... ⏳")
            try:
                file       = await photo.get_file()
                file_bytes = bytes(await file.download_as_bytearray())
                slip_info  = await gemini_read_slip(file_bytes)
            except Exception as e:
                logger.error(f"Slip read: {e}")
                slip_info = {}

            amount      = slip_info.get("AMOUNT", "UNKNOWN")
            date_str    = slip_info.get("DATE", "UNKNOWN")
            time_str    = slip_info.get("TIME", "UNKNOWN")
            pay_type    = slip_info.get("TYPE", "UNKNOWN")
            reference   = slip_info.get("TRANSACTION_NO", slip_info.get("REFERENCE", "UNKNOWN"))
            sender      = slip_info.get("SENDER", "UNKNOWN")
            transfer_to = slip_info.get("TRANSFER_TO", "UNKNOWN")
            ADMIN_REAL_NAME = os.environ.get("ADMIN_REAL_NAME", "Kyaw Min Tun")
            receiver_ok = ""
            if pay_type == "KPay" and transfer_to != "UNKNOWN":
                if ADMIN_REAL_NAME.lower() in transfer_to.lower():
                    receiver_ok = "✅"
                else:
                    receiver_ok = "⚠️ Admin နာမည် မဟုတ်ဘူး!"

            expected  = pay_data.get("amount", 0)
            amount_ok = ""
            if amount != "UNKNOWN":
                try:
                    amt_num = int(re.sub(r'[^\d]', '', amount))
                    if amt_num >= expected:
                        amount_ok = "✅"
                    else:
                        amount_ok = f"⚠️ မပြည့်မီ (လိုအပ်: {expected:,} ks)"
                except:
                    amount_ok = "⚠️ စစ်မရ"
            else:
                amount_ok = "⚠️ ဖတ်မရ"

            pending_payment[user_id]["slip_info"] = slip_info
            pending_payment[user_id]["file_bytes"] = file_bytes

            pkg_name  = PLAN_NAMES.get(pay_data.get("package","CH"), "Unknown")
            months    = pay_data.get("months", 1)
            name      = pay_data.get("name", "Unknown")
            username  = pay_data.get("username", str(user_id))
            chosen_method = pay_data.get("method", "")
            method_label  = PAYMENT_METHOD_INFO.get(chosen_method, {}).get("label", chosen_method.upper() if chosen_method else "—")

            txn_label = "Transaction ID" if pay_type == "Wave" else "Transaction No"
            admin_text = (
                f"💰 *Payment Slip အသစ်*\n\n"
                f"👤 {name} ({username})\n"
                f"🆔 ID: `{user_id}`\n"
                f"📦 Package: {pkg_name} — {months} လ\n"
                f"🎯 ရွေးခဲ့သော method: {method_label}\n"
                f"💵 Expected: {expected:,} ks\n\n"
                f"📋 *Slip အချက်အလက်:*\n"
                f"🏦 Type: {pay_type}\n"
                f"🔢 {txn_label}: `{reference}`\n"
                f"💵 Amount: {amount} ks {amount_ok}\n"
                f"📅 Date: {date_str} {time_str}\n"
                + (f"📨 Transfer To: {transfer_to} {receiver_ok}\n" if pay_type == "KPay" else f"👤 Sender: {sender}\n")
                + f"\n⚠️ {pay_type} app မှာ `{reference}` စစ်ပြီးမှ Confirm လုပ်ပါ"
            )
            admin_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"💬 {name} ကို Message ပို့", url=f"tg://user?id={user_id}")],
                [InlineKeyboardButton("✅ Confirm", callback_data=f"slip_confirm_{user_id}"),
                 InlineKeyboardButton("❌ Reject",  callback_data=f"slip_no_{user_id}")],
            ])
            await notify_admins(context, admin_text, reply_markup=admin_kb)
            await update.message.reply_text(
                "✅ *Slip လက်ခံရပြီ!*\n\n"
                "Admin မှ စစ်ဆေးနေသည် — ခဏစောင့်ပါ 🙏\n"
                "မကြာမီ Password DM ပို့ပေးမည်",
                parse_mode='Markdown')
            return

    # ── Auction List Mode ──
    if "list" in caption:
        cap_lower = caption.lower()
        caption_klang9 = any(k in cap_lower for k in ["klang9","klang 9","klang","9.2"])
        caption_maesot = any(k in cap_lower for k in ["maesot","mae sot","measot"])
        await update.message.reply_text(f"📋 Auction List ဖတ်နေတယ်... ⏳")
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            new_cars, detected_loc = await gemini_ocr_auction_list(file_bytes)
        except Exception as e:
            logger.error(f"Auction list: {e}"); new_cars = []; detected_loc = None

        cap_border44 = any(k in cap_lower for k in ["border44","border 44","44gate","44 gate","best border","border-44"])

        if detected_loc in ("Klang9", "MaeSot", "Border44"):
            import_loc = detected_loc
        elif caption_klang9:
            import_loc = "Klang9"
        elif cap_border44:
            import_loc = "Border44"
        elif caption_maesot:
            import_loc = "MaeSot"
        else:
            await update.message.reply_text(
                "⚠️ *Location မသိပါ!*\n\n"
                "Caption မှာ location ထည့်ပြီး ပြန်တင်ပါ:\n"
                "• `klang9 list` → Klang9 Freezone\n"
                "• `maesot list` → MaeSot Freezone\n"
                "• `border44 list` → Best Border-44 Gate\n\n"
                "💡 List ပုံရဲ့ Header ကိုလည်း Gemini ဖတ်ပေးနိုင်တယ်",
                parse_mode='Markdown')
            return

        if import_loc == "Klang9": loc_name = LOC_KLANG9
        elif import_loc == "Border44": loc_name = LOC_BORDER44
        else: loc_name = LOC_MAESOT
        await update.message.reply_text(f"📍 Location: *{loc_name}*", parse_mode='Markdown')

        if not new_cars:
            await update.message.reply_text("⚠️ List ဖတ်မရပါ\n💡 Gemini API limit ကုန်နိုင်တယ်")
            return

        existing = {c["chassis"].upper() for c in CARS}
        added    = []
        unknown  = []

        for car in new_cars:
            ch    = str(car.get("chassis","")).upper().strip()
            model = str(car.get("model","")).strip()
            color = str(car.get("color","")).strip()
            year  = int(car.get("year",0) or 0)
            if not ch:
                continue
            missing_fields = []
            if not model or model.upper() in ("", "UNKNOWN", "N/A"):
                missing_fields.append("Model")
                model = guess_model_from_chassis(ch)
            if not color or color in ("", "-", "N/A"):
                missing_fields.append("Color")
                color = "-"
            if not year:
                missing_fields.append("Year")
            if ch not in existing:
                CARS.append({"chassis":ch,"model":model,"color":color,"year":year,"loc":import_loc})
                existing.add(ch)
                added.append(ch)
            if missing_fields:
                unknown.append({"chassis":ch,"model":model,"missing":missing_fields})

        txt = f"✅ *{loc_name} List Update ပြီး!*\n\n📊 ဖတ်ရ: {len(new_cars)} စီး\n✨ အသစ်: {len(added)} စီး\n"
        if added:
            txt += "\n🆕 " + "".join(f"`{ch}`\n" for ch in added[:10])
            if len(added) > 10:
                txt += f"... {len(added)-10} စီး ထပ်ရှိ\n"
        if unknown:
            txt += f"\n⚠️ *မသေချာ ({len(unknown)} စီး):*\n"
            for u in unknown[:5]:
                txt += f"• `{u['chassis']}` ({u['model']}) — မရ: *{', '.join(u['missing'])}*\n"
            if len(unknown) > 5:
                txt += f"... {len(unknown)-5} စီး ထပ်ရှိ\n"
        txt += f"\n📋 Database: {await get_sheet_car_count()} စီး"
        await update.message.reply_text(txt, parse_mode='Markdown')
        return

    # ── Car Photo Mode ──
    await update.message.reply_text("🔍 Chassis ရှာနေတယ်... ⏳")

    chassis      = extract_chassis_from_text(caption) if caption else None
    price_match  = re.search(r'(?<![A-Z0-9])(\d{4,6})(?![A-Z0-9])', caption.upper()) if caption else None
    price        = int(price_match.group(1)) if price_match else None
    gemini_model = ""; gemini_color = ""; gemini_year = 0; file_bytes = None

    if caption and chassis:
        cap_work = caption.upper()
        cap_work = re.sub(re.escape(chassis.upper()), '', cap_work)
        if price_match:
            cap_work = re.sub(r'(?<![A-Z0-9])' + re.escape(price_match.group(1)) + r'(?![A-Z0-9])', '', cap_work)
        cap_work = cap_work.strip()
        year_m = re.search(r'\b(19|20)\d{2}\b', cap_work)
        if year_m:
            gemini_year = int(year_m.group())
            cap_work = cap_work.replace(year_m.group(), '').strip()
        KNOWN_COLORS = ["PEARL WHITE","DARK BLUE","LIGHT BLUE","LIGHT GREEN",
                        "WHITE","BLACK","SILVER","RED","BLUE","GREEN","YELLOW",
                        "BROWN","ORANGE","GREY","GRAY","GOLD","PURPLE","MAROON"]
        for col in KNOWN_COLORS:
            if col in cap_work:
                gemini_color = col
                cap_work = cap_work.replace(col, '').strip()
                break
        cap_model = re.sub(r'[^A-Z0-9 ]', '', cap_work).strip()
        if cap_model and len(cap_model) >= 2:
            gemini_model = cap_model

    if not chassis:
        try:
            file       = await photo.get_file()
            file_bytes = bytes(await file.download_as_bytearray())
            result     = await gemini_ocr_chassis(file_bytes)
            chassis      = result.get("chassis","")
            gemini_model = result.get("model","")
            gemini_color = result.get("color","")
            gemini_year  = result.get("year",0)
        except Exception as e:
            logger.error(f"Photo: {e}")

    car       = find_by_chassis(chassis) if chassis else None
    image_url = ""
    if chassis and file_bytes:
        image_url = await upload_to_cloudinary(file_bytes, chassis)

    if car:
        car_loc = loc_display(car.get('loc', 'MaeSot'))
    else:
        sheet_loc = None
        if chassis and SHEET_WEBHOOK:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(
                        f"https://docs.google.com/spreadsheets/d/{os.environ.get('SHEET_ID','')}/gviz/tq?tqx=out:json&sheet=Sheet1",
                        timeout=8)
                raw = resp.text
                import json as _json
                data = _json.loads(raw[raw.index('{'):raw.rindex('}')+1])
                rows = data.get('table',{}).get('rows',[])
                for row in rows:
                    c = row.get('c',[])
                    if len(c) > 1:
                        ch_val = (c[1].get('v','') or '') if c[1] else ''
                        if str(ch_val).upper().strip() == chassis.upper().strip():
                            loc_val = (c[6].get('v','') or '') if len(c) > 6 and c[6] else ''
                            if loc_val:
                                sheet_loc = str(loc_val)
                            break
            except Exception as e:
                logger.error(f"sheet loc lookup: {e}")

        if sheet_loc:
            car_loc = loc_display(sheet_loc)
        else:
            cap_l = (caption or "").lower()
            if any(k in cap_l for k in ["klang9","klang 9","klang","9.2"]):
                car_loc = LOC_KLANG9
            elif any(k in cap_l for k in ["border44","border 44","44gate","44 gate","best border","border-44"]):
                car_loc = LOC_BORDER44
            else:
                car_loc = LOC_MAESOT

    final_model = gemi
